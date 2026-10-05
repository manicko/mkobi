# Audit Findings — Performance

**Phase:** 11 — Performance
**Date:** 2026-10-05
**Head audited:** `a324875`
**Mode:** `problems_only`

> Scope note: the repository was under active concurrent modification throughout
> this phase (HEAD advanced from `ab76989` through `a324875`). Every citation
> below was re-opened and read at `a324875` immediately before writing. No load
> test, benchmark, or test-suite run was performed; the database is shared with
> concurrent phases.

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 1 |
| HIGH | 3 |
| MEDIUM | 4 |
| LOW | 0 |
| **Total** | **8** |

Static reasoning: 5. Measured: 3 (`PERF-101`, `PERF-102`, `PERF-104` carry the
decisive micro-measurement; `PERF-103` reuses the same measurement).

---

## Findings

### PERF-101 — Every authenticated request materialises the entire aggregate table of every dashboard the caller can read, before the route runs

**Severity:** CRITICAL
**Kind:** `[BEST-PRACTICE]` — the declared mitigation is structurally defeated
**Evidence:** measured (static reasoning + micro-measurement)
**File:** `src/mkobi/db/models/user.py:97-104`, `src/mkobi/db/models/dashboard.py:118-124`
**Files:** `src/mkobi/db/repositories/user_repo.py:41-43`, `src/mkobi/api/deps.py:602-603`, `src/mkobi/config.py:614-617`

Two model-level relationships chain into a single eager load of the whole fact
table:

`src/mkobi/db/models/user.py:97-104`
```python
    # Relationship with dashboards through access table
    dashboards: Mapped[list["Dashboard"]] = relationship(
        "Dashboard",
        secondary="dashboard_access",
        back_populates="users",
        lazy="selectin",
        overlaps="accesses,dashboard",
    )
```

`src/mkobi/db/models/dashboard.py:118-124`
```python
    # Relationship with aggregated data
    aggregated_data: Mapped[list[AggregatedData]] = relationship(
        "AggregatedData",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
```

`lazy="selectin"` is an eager loader: SQLAlchemy issues the extra `SELECT` as
soon as the owning entity is loaded. So loading one `User` row loads every
`Dashboard` the user may read, and each of those loads its **entire**
`aggregated_data` row set — then cascades again through `AggregatedData.dashboard`
and `AggregatedData.graph`, which are also `lazy="selectin"`
(`src/mkobi/db/models/aggregated_data.py:74-85`).

`UserRepository.get` is a bare select with no loader options, so nothing
suppresses the cascade:

`src/mkobi/db/repositories/user_repo.py:41-43`
```python
            result = await db.execute(
                select(user_model.User).where(user_model.User.id == id)
            )
```

and it runs in the authentication dependency of every protected route:

`src/mkobi/api/deps.py:602-603`
```python
        repo = UserRepository()
        user = await repo.get(id=user_id, db=db)
```

**Why it violates the declared contract.** `config.py` states the budget's
purpose explicitly:

`src/mkobi/config.py:614-617`
```python
    # Maximum rows returned for a single graph in one dashboard response.
    max_rows_per_graph: int = Field(default=2_000, ge=0)
    # Maximum rows returned across the whole dashboard response.
    max_rows_total: int = Field(default=20_000, ge=0)
```

`AggregatedDataRepository._response_columns_only()`
(`src/mkobi/db/repositories/aggregated_data_repo.py:67-82`) applies
`load_only` + `noload(AggregatedData.dashboard)` + `noload(AggregatedData.graph)`
— but that suppression is bound to the aggregate repository's own statements
only. It does not apply to rows reached through `User.dashboards` or
`Dashboard.aggregated_data`, which issue their own unconstrained selects. The
row budget is therefore enforced on the aggregate *read* and completely
ineffective on the two reads that precede it.

**Concrete cost (measured).** Against an in-memory SQLite database built from
the project's own mapped metadata, seeded with 20 dashboards / 100 graphs /
20,000 `AggregatedData` rows, counting statements via
`before_cursor_execute` and counting rows by `Session.identity_map`:

```
auth dep: UserRepository.get   stmts=13  agg rows=20000/20000 (100%)  heap=80.4 MB
```

- 13 statements per authenticated request, regardless of endpoint.
- **100%** of the table's rows materialised — before any route logic runs.
- ~80 MB of Python heap at 20,000 rows; a dashboard at 100,000 rows puts a
  single worker near the 1 GiB cgroup limit the `DataSettings` docstring
  (`config.py:600-604`) is written to protect.
- Rows are caller-controlled: an upload's row count sets it. A single accepted
  upload of a large CSV creates the condition for **every** subsequent
  authenticated request by **every** user who can read that dashboard.

The row count at which it bites is not "large": a viewer with access to one
20,000-row dashboard pays the full table on every page view.

**Recommendation (smallest change that removes the effect).** Make the auth
read load only the columns it returns. `UserRead` carries `id, email, role,
is_active, force_password_change, created_at, updated_at` — no relationship.
Adding `noload("*")` / `raiseload("*")` to `UserRepository.get` and to
`UserRepository.get_by_email_with_hash` collapses the 13 statements to 1 and
the materialisation to zero. The same treatment belongs on
`DashboardRepository.get`, `GraphRepository.get`/`get_all`/`get_by_dashboard_id`,
and `ProcessingLogRepository.get_by_id` (see `PERF-102`, `PERF-103`).

---

### PERF-102 — The graph list and graph read paths load every aggregate row through `Graph.dashboard` and `Graph.aggregated_data`

**Severity:** HIGH
**Kind:** `[BEST-PRACTICE]`
**Evidence:** measured
**File:** `src/mkobi/db/models/graphs.py:88-101`
**Files:** `src/mkobi/db/repositories/graph_repo.py:41-43`, `src/mkobi/db/repositories/graph_repo.py:215-218`, `src/mkobi/api/routes/graphs.py:204-211`, `src/mkobi/api/routes/data.py:293`

`src/mkobi/db/models/graphs.py:88-101`
```python
    # Relationship with dashboard
    dashboard: Mapped[Dashboard] = relationship(
        "Dashboard",
        back_populates="graphs",
        lazy="selectin",
    )

    # Relationship with aggregated data
    aggregated_data: Mapped[list[AggregatedData]] = relationship(
        "AggregatedData",
        back_populates="graph",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
```

`src/mkobi/db/repositories/graph_repo.py:215-218`
```python
            query = select(graph_model.Graph)
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
```

`src/mkobi/db/repositories/graph_repo.py:41-43`
```python
            result = await db.execute(
                select(graph_model.Graph).where(graph_model.Graph.id == id)
            )
```

**Scaling factor.** The cost is set by the number of distinct dashboards in the
result, not by `limit`. `selectin` batches by parent key, so `?limit=100`
returning graphs across 20 dashboards loads all 20 dashboards' aggregate rows —
the limit bounds the graph list, not the row set behind it.

**Concrete cost (measured, same seed as `PERF-101`).**

```
GET /graphs?limit=100 -> get_all  stmts=21  agg rows=20000/20000 (100%)  heap=79.8 MB
GET /graphs/{id}      -> get      stmts=21-32  agg rows= 1000/20000 (  5%)  heap= 4.0 MB
```

21 statements for one query, versus 1 for `select(User)`. The 21 (vs 13 for
`select(Dashboard)`) is itself informative: `Graph.dashboard` is a many-to-one
`selectin`, so the `Dashboard` cascade is entered twice — statements 3 and 4 of
the captured sequence are duplicate `FROM dashboards` selects.

This is also the path `GET /data/aggregated` itself takes on the all-graphs
branch:

`src/mkobi/api/routes/data.py:293`
```python
        graphs = await graph_repo.get_by_dashboard_id(dashboard_id, db)
```

so `GET /data/aggregated` pays this cascade before the budgeted read even
begins.

**Recommendation.** Add `noload(Graph.dashboard)` and
`noload(Graph.aggregated_data)` to every graph read that only needs scalar
columns, exactly as `AggregatedDataRepository._response_columns_only()` already
does. `GraphRead` carries no relationship.

---

### PERF-103 — `GET /upload/status/{task_id}` is polled every 2 seconds and re-materialises the dashboard's whole aggregate row set on every poll

**Severity:** HIGH
**Kind:** `[BEST-PRACTICE]`
**Evidence:** measured
**File:** `src/mkobi/db/models/processing_logs.py:83-88`
**Files:** `src/mkobi/db/repositories/processing_log_repo.py:286-290`, `frontend/src/features/upload/api/uploadApi.ts:50-57`

`src/mkobi/db/models/processing_logs.py:83-88`
```python
    # Relationship with dashboard
    dashboard: Mapped["Dashboard"] = relationship(
        "Dashboard",
        back_populates="processing_logs",
        lazy="selectin",
    )
```

`src/mkobi/db/repositories/processing_log_repo.py:286-290`
```python
            result = await db.execute(
                select(processing_log_model.ProcessingLog)
                .options(selectinload(processing_log_model.ProcessingLog.dashboard))
                .where(processing_log_model.ProcessingLog.id == log_id)
            )
```

`.options(selectinload(...dashboard))` here is not a narrowing — the
relationship is already `lazy="selectin"` at the model level, so the option is
redundant and the load happens regardless.

The client polls this endpoint while an upload is in flight:

`frontend/src/features/upload/api/uploadApi.ts:50-57`
```typescript
    refetchInterval: (query) => {
      // Stop polling when processing is complete or failed
      const data = query.state.data
      if (data?.status === ProcessingStatus.COMPLETED || data?.status === ProcessingStatus.FAILED) {
        return false
      }
      return 2000 // Poll every 2 seconds
    },
```

**Scaling factor.** 30 polls per minute per open upload modal, and each poll
loads one dashboard's full aggregate row set (which then cascades to all nine
`Dashboard` relationships).

**Concrete cost (measured, same seed as `PERF-101`).**

```
GET /upload/status/{id} -> get_by_id   stmts=13-23  agg rows=1000/20000 (5%)  heap=4.1 MB
```

At 13-23 statements per poll, a 10-minute upload costs 300 polls ≈ 3,900
statements and ≈ 150,000 aggregate-row materialisations, for a response whose
entire payload is one row's `status` and `message`. This is the only endpoint in
the system whose request rate is driven by a fixed timer rather than by user
action, which is why the same row set is re-read 30× per minute.

**Recommendation.** `ProcessingLogRead` needs only `dashboard_name`. Load the
name with an explicit scalar column (`select(ProcessingLog, Dashboard.name)`),
which serves the same field in 1 statement and materialises 0 rows. Applied to
`get_by_id`, `get_by_dashboard`, `get_filtered` and `get_latest_by_dashboard`,
it also removes the row-set amplification on `GET /processing/logs`
(`limit` ≤ 1000 there, spanning up to 1000 dashboards).

---

### PERF-104 — `check_dashboard_access` re-issues the whole 13-statement auth cascade a second time on the same request

**Severity:** HIGH
**Kind:** `[BEST-PRACTICE]`
**Evidence:** measured
**File:** `src/mkobi/core/permissions.py:171-172`
**Files:** `src/mkobi/api/deps.py:602-603`, `src/mkobi/api/routes/data.py:167-172`

`src/mkobi/core/permissions.py:171-172`
```python
        user_repo = UserRepository()
        user = await user_repo.get(id=user_id, db=db)
```

`src/mkobi/api/deps.py:602-603`
```python
        repo = UserRepository()
        user = await repo.get(id=user_id, db=db)
```

**Scaling factor.** Two independent `db.execute(select(User))` calls for the same
user id on the same `AsyncSession` within one request. A second `select(User)`
is a fresh statement, so its `selectin` loaders run again — the identity map
deduplicates the ORM *entities*, not the round trips.

**Concrete cost (measured, same seed as `PERF-101`, one request, cumulative
counter):**

```
after UserRepository.get      cumulative stmts = 13
after 2nd UserRepository.get  cumulative stmts = 26
```

Exactly doubled: 13 → 26. On `/data/aggregated` this is the auth dependency plus
`check_dashboard_access`, so the request pays the auth cascade twice before the
budgeted read starts. The session is request-scoped and held for the whole
request, so both loads occur while a pooled connection is checked out.

**Recommendation.** `check_dashboard_access` already receives the
`UserRead` produced by the dependency (`get_dashboard_service`'s route signature
binds `current_user: UserRead = Depends(get_current_user_dependency)` and then
calls `check_dashboard_access(current_user.id, dashboard_id, db)`). Accepting
the already-loaded user — or the `user.role == UserRole.ADMIN` decision the
dependency could compute once — removes the duplicate.

---

### PERF-105 — The reconciler's stale-temp-file sweep runs synchronously on the application's event loop

**Severity:** MEDIUM
**Kind:** `[BEST-PRACTICE]`
**Evidence:** static reasoning
**File:** `src/mkobi/workers/data_worker.py:1562`
**Files:** `src/mkobi/services/file_cleanup.py:92-101`, `src/mkobi/app.py:201-208`, `src/mkobi/config.py:735-737`

`src/mkobi/workers/data_worker.py:1562`
```python
            files = cleanup_stale_temp_files()
```

`src/mkobi/services/file_cleanup.py:92-101`
```python
    csv_files = list(upload_dir.glob("*.csv*"))

    for file_path in csv_files:
        try:
            # Check file modification time
            mtime = file_path.stat().st_mtime
            file_age_seconds = current_time - mtime

            if file_age_seconds > cutoff_seconds:
                file_path.unlink()
```

This task is created in the FastAPI application's own lifespan, so the loop it
blocks is the loop that serves requests:

`src/mkobi/app.py:201-208`
```python
        cleanup_task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=config.stale_processing_cleanup_interval_seconds,
                timeout_minutes=config.stale_processing_timeout_minutes,
                lease=lease,
                status=reconciler_status,
            )
        )
```

`cleanup_stale_temp_files` is a plain synchronous function: one `glob`
materialised into a list, then one `stat()` and possibly one `unlink()` per
file — all blocking syscalls executed inline on the event loop, with no
`await` inside the loop body.

**Scaling factor.** One sweep every `stale_processing_cleanup_interval_seconds`
(default 300 s, `config.py:737`), with a file count that is unbounded by design:
every accepted upload leaves a `<uuid>.csv.gz` in `upload_temp_dir` until its job
reaches a terminal state, and this sweep is the reclaimer for the orphans.
When the lease fails open (Redis unreachable) the sweep runs in **all four**
`--workers 4` processes simultaneously.

**Concrete cost.** At N files, one tick blocks the loop for N × (1 `stat` +
≈1 `unlink`) syscalls. Warm local disk: ~30 µs per file, so 5,000 files ≈ 150 ms
of fully blocked request loop per tick; 4 fail-open replicas ⇒ ~600 ms. Under a
container overlay filesystem or any network-backed volume the per-syscall cost is
one to two orders of magnitude higher.

**Recommendation.** One line, and it matches the file's own established
pattern — every other blocking call in `data_worker.py` is already offloaded
(`asyncio.to_thread` at lines 706, 799, 814, 836, 862 for Polars; at lines
941, 962, 1036, 1058 for file removal). Line 1562 is the one omission:
`files = await asyncio.to_thread(cleanup_stale_temp_files)`.

---

### PERF-106 — `GET /upload/result/{task_id}` loads every row of the dashboard's first graph to compute `len()`, while a `COUNT(*)` method sits unused in the same repository

**Severity:** MEDIUM
**Kind:** `[BEST-PRACTICE]`
**Evidence:** static reasoning
**File:** `src/mkobi/services/data_service.py:510-514`
**Files:** `src/mkobi/db/repositories/aggregated_data_repo.py:273-281`, `src/mkobi/db/repositories/aggregated_data_repo.py:369-375`

`src/mkobi/services/data_service.py:510-514`
```python
        graphs = await self.graph_repo.get_by_dashboard_id(log.dashboard_id, db)
        rows_processed = 0
        if graphs:
            agg_data = await self.agg_repo.get_by_graph_id(graphs[0].id, db)
            rows_processed = len(agg_data) if agg_data else 0
```

`src/mkobi/db/repositories/aggregated_data_repo.py:273-281`
```python
            query = (
                select(aggregated_data_model.AggregatedData)
                .where(*self._graph_filter_conditions(graph_id, dashboard_id, filters))
                .order_by(aggregated_data_model.AggregatedData.id)
                .options(*_response_columns_only())
            )

            result = await db.execute(query)
            data = list(result.scalars().all())
```

`get_by_graph_id` has **no** `LIMIT` — unlike `get_by_graph_id_limited`
(`aggregated_data_repo.py:203-223`), it is not bounded by
`max_rows_per_graph`. The result is used only for `len()`.

`src/mkobi/db/repositories/aggregated_data_repo.py:369-375`
```python
            result = await db.execute(
                select(func.count())
                .select_from(aggregated_data_model.AggregatedData)
                .where(*self._graph_filter_conditions(graph_id, dashboard_id, filters))
            )
            return int(result.scalar_one())
```

**Scaling factor.** O(R) where R is the graph's row count, for an integer. The
`COUNT(*)` is index-only on `idx_aggregated_data_graph_id` — it reads no heap
tuples and no JSONB, and transfers no payload.

**Concrete cost.** At R = 20,000 rows: ~20,000 ORM entities constructed and
`dims` + `metrics` JSONB deserialised, for a response field that is the integer
`20000`. Using the `DataSettings` docstring's own figure of 3,402 B/row
(`config.py:601`), that is ~68 MB of allocation and serialisation per call to
compute a value that fits in a `COUNT(*)`. `count_by_graph_id` already exists,
is exercised by the hot path (`data_service.py:283-285`), and is not called
here.

**Recommendation.** `rows_processed = await self.agg_repo.count_by_graph_id(graphs[0].id, db)`.
Same repository, same predicate, one index-only scan. This is the only remaining
caller of the unbounded `get_by_graph_id`, so the row-returning variant can then
be deleted rather than left as a trap.

---

### PERF-107 — The all-graphs branch of `GET /data/aggregated` issues two sequential round trips per graph with no bound on the graph count

**Severity:** MEDIUM
**Kind:** `[BEST-PRACTICE]`
**Evidence:** static reasoning
**File:** `src/mkobi/api/routes/data.py:293-311`
**Files:** `src/mkobi/services/data_service.py:280-285`, `src/mkobi/config.py:614-617`

`src/mkobi/api/routes/data.py:293-311`
```python
        graphs = await graph_repo.get_by_dashboard_id(dashboard_id, db)
        graph_responses: list[GraphDataResponse] = []
        remaining_budget = caps.max_rows_total
        any_truncated = False

        for graph_item in graphs:
            records, total_rows, metric_keys, dimension_keys = (
                await data_service.get_bounded_aggregated_data(
                    dashboard_id=dashboard_id,
                    graph_id=graph_item.id,
                    db=db,
                    max_rows=min(caps.max_rows_per_graph, remaining_budget),
                    filters=parsed_filters,
                )
            )
            data_points = _flatten_points(records)
            returned_rows = len(data_points)
            remaining_budget -= returned_rows
            rows_truncated = total_rows > returned_rows
```

`src/mkobi/services/data_service.py:280-285`
```python
        records = await self.agg_repo.get_by_graph_id_limited(
            graph_id, db, max_rows, dashboard_id=dashboard_id, filters=filters,
        )
        total_rows = await self.agg_repo.count_by_graph_id(
            graph_id, db, dashboard_id=dashboard_id, filters=filters,
        )
```

**What is correct here, stated so the gap is precise.** The row budget *is*
enforced and *is* deterministic. `max_rows_per_graph = 2_000` bounds each
graph's read, `max_rows_total = 20_000` bounds the response, and
`order_by(AggregatedData.id)` (`aggregated_data_repo.py:203-216`) gives a total
order on a unique indexed column, so a truncated page is stable across
requests. Both previously-unbounded concerns are closed.

**The residual cost.** `remaining_budget` bounds **rows**, not **statements**.
Each iteration issues two sequential round trips against the same predicate: the
bounded row read, then a `COUNT(*)` that re-scans the same graph. With N graphs
the aggregate work on one page view is `2N` statements plus a dashboard-wide
`COUNT(*)` (`data.py:340-342`). `graph_repo.get_by_dashboard_id(dashboard_id, db)`
is called with no `limit`/`skip`.

**Concrete cost.** N graphs ⇒ `2N + 1` sequential round trips. A dashboard with
50 charts costs 101 aggregate round trips per page view on top of the 13-26 from
the auth path (`PERF-101`, `PERF-104`) — the sequential `await` inside the loop
means latency grows linearly with chart count, not the sum. The `COUNT(*)` is
only consumed to compute `rows_truncated` and `total_rows`.

**Recommendation.** Two options, smallest first. (1) Return the count from the
row read itself — `COUNT(*) OVER ()` in the same windowed statement collapses
`2N` to `N` and removes one full predicate scan per graph. (2) If `total_rows`
must stay a separate true count, bound the graph count the same way rows are
bounded and report truncation when the graph list itself is cut.

---

### PERF-108 — `TableChart` renders every served row and `ChartRenderer` is not memoized, so each `DashboardView` render re-derives every chart's trace array

**Severity:** MEDIUM
**Kind:** `[BEST-PRACTICE]`
**Evidence:** static reasoning
**File:** `frontend/src/features/dashboards/ui/charts/TableChart.tsx:69-78`
**Files:** `frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:148-151`, `frontend/src/features/dashboards/ui/DashboardView.tsx:301`, `:330`

`frontend/src/features/dashboards/ui/charts/TableChart.tsx:69-78`
```typescript
        <tbody>
          {data.rows.map((row, idx) => (
            <tr key={idx}>
              {displayColumns.map((col) => (
                <td key={col} style={{ border: '1px solid #ddd', padding: '8px' }}>
                  {getDisplayValue(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
```

`frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:148-151`
```typescript
export function ChartRenderer({ graph }: ChartRendererProps) {
  // Table charts render as native HTML tables (no Plotly conversion)
  if (graph.type === 'table') {
    return <TableChart data={{ rows: graph.data }} />
```

`frontend/src/features/dashboards/ui/DashboardView.tsx:301` and `:330`
```typescript
              {aggregatedData.graphs.map((graph: GraphDataWithConfig) => (
                <Paper key={graph.graph_id} variant="outlined" sx={{ p: 2 }}>
```
```typescript
                    <ChartRenderer graph={graph} />
```

**Scaling factor.** `displayColumns` is derived from the union of keys across
the served rows (`TableChart.tsx:31`), so DOM node count is
`rows × columns`, not `rows`. There is no cap below the server's
`max_rows_per_graph`, and no windowing. `ChartRenderer` is a plain function
component with no `React.memo`, and `DashboardView` re-renders whenever
`useDashboard` or `useAggregatedData` returns a new object identity — so every
`convertToPlotlyData(graph)` call (O(rows), plus a `groupByColor` pass for
colour charts) re-runs on every parent render, for every chart on the page.

**Concrete cost.** At the declared `max_rows_per_graph = 2_000` with the 6 keys a
real aggregation produces (`region`, `year`, `sku`, `revenue_sum`,
`orders_sum`, plus one grouping key), a single `table`-type chart materialises
~14,000 DOM nodes per render pass, synchronously, on the main thread. Across a
dashboard of 4 charts the re-derivation cost is 4 × O(2,000) per render. The
`rows_truncated` caption (`DashboardView.tsx:306-315`) tells the user the table
is truncated; nothing tells the browser to stop rendering at a screenful.

**Recommendation.** (1) `React.memo` on `ChartRenderer` — the `graph` prop is a
stable object from the query cache, so this removes every redundant
re-derivation with one line. (2) Cap or window `TableChart`'s rendered rows the
same way the server caps the response, and show the same
`returned_rows`/`total_rows` count the chart header already has available.

---

## Areas checked with no findings

### Blocking calls on the event loop — Polars and file I/O
Every CPU-bound Polars operation in the upload pipeline is offloaded:
`data_worker.py:706` (`clean_uploaded_frame`), `799` (`transform_dimensions`),
`814`/`836`/`862` (`enforce_renamed_dims`, `resolve_metrics_semantics`,
`clean_nan_inf`), `941`/`962` (upload dir creation and file replacement),
`1036`/`1058` (terminal-path removal). Upload streaming uses `aiofiles` with an
8 KiB chunk size and a cumulative `Content-Length` + running-bytes cap
(`src/mkobi/api/routes/upload.py:210-230`), so the body is never buffered whole.
No `requests`, no `time.sleep`, no synchronous DB driver on the loop.
`data_service.py:373` calls `asyncio.to_thread(dashboard_repo.get, ...)` — the
one blocking repository read is correctly threaded. The single exception is
`AggregationService.aggregate_for_dashboard` (`aggregation_service.py:115-146`),
which is `async def` and runs `df.group_by(...).agg(...)` inline. Not filed: it
executes on the **RQ worker's** loop, where `rq_worker_wrapper.py:236-238` runs
one job at a time and nothing else competes, so it has no blast radius today.

### `aggregated_data` JSONB read patterns
The budgeted read selects `id, dashboard_id, graph_id, dims, metrics` and
suppresses both relationships (`aggregated_data_repo.py:67-82`); filter
predicates are pushed into the `WHERE` clause, not evaluated in Python
(`_graph_filter_conditions`, `aggregated_data_repo.py:118-170`). The response
payload carries a `rows_truncated` flag and true `total_rows`, so truncation is
never silent. `idx_aggregated_data_dims_gin` (a GIN index on `dims`) is written
on every aggregate insert and never read by any query in the codebase — already
filed as PERF-009, not re-filed.

### Connection pool sizing
`pool_size=10`, `max_overflow=20` against `--workers 4`
(`docker/Dockerfile:242`) is 120 potential connections against PostgreSQL's
default `max_connections=100`, which is not set anywhere in
`docker/docker-compose.yml` or `docker/init-scripts/`. Already filed as PERF-007
(phase 03); not re-filed. Cross-reference: `PERF-101`/`PERF-104` enlarge its
blast radius, because a request now holds its pooled connection for the whole
cascade — 13-26 statements plus a full-table materialisation — instead of only
for the budgeted read.

### Index inventory
Verified from `alembic/versions/` (10 revisions) against the models.
`aggregated_data` has `graph_id`, `dashboard_id`, `(dashboard_id, graph_id)`,
and the GIN `dims`. `processing_logs` has `dashboard_id`,
`(status, finished_at)`, `(status, started_at)`, `started_at` — the startup
retention sweep `DELETE ... WHERE finished_at < ? AND status IN (...)`
(`db/starter.py:598-603`) is served by `(status, finished_at)`. No missing index
with a demonstrated query cost. Phase 14 owns the migration-level inventory;
the only index finding is PERF-009.

### Upload boundary caps
`max_file_size_mb = 100` is enforced cumulatively across chunks with a
`413` on excess (`upload.py:210-230`), MIME type is checked, and nginx's
`client_max_body_size ${NGINX_CLIENT_MAX_BODY_SIZE}` defaults to `512m`,
deliberately above the application ceiling
(`docker/nginx/nginx.conf.template:36-41`). Not re-filed against EXT-101; the
missing-cap direction was checked and there is no unbounded path here.

### Redis client construction and caching
`get_redis_client` and `get_async_redis_client` are both
`@functools.cache`-decorated (`core/redis_client.py:22`, `:54`), so a client is
built once per process rather than per call. `enqueue_job` wraps the RQ enqueue
in `asyncio.to_thread` (`core/task_queue.py:113`). The rate limiter costs 1-2
Redis round trips and is applied only on `/upload` and `/client-errors`, never
on the read path. No unbounded cache exists in the codebase.

### `GET /data/aggregated` row budget and ordering
Both previously-unbounded concerns are closed at HEAD: `max_rows_per_graph` /
`max_rows_total` bound the response, and `order_by(AggregatedData.id)` on a
unique indexed column makes a truncated page deterministic across requests. The
residual cost is statement count, not rows or ordering — filed as `PERF-107`.

## Not examined (scope reduction)

The following were out of scope for this pass and carry no finding either way:

- `services/processing_logs_service.py`, `services/layout_service.py`,
  `services/dashboard_service.py`, `services/graph_service.py` beyond the
  statements quoted above.
- `api/routes/users.py`, `api/routes/admin.py`, `api/routes/auth.py`,
  `api/routes/registration_requests.py` — not opened.
- `db/models/{filters,layout,processing_configs,dashboard_filter_values,registration_request}.py`
  relationship eager-loading — not inspected.
- `db/repositories/{layout_repo,filters_repo,processing_config_repo,registration_request_repo}.py`
  loader options — not inspected.
- `data/processing/`, `data/loaders/`, `data/transform/` beyond the `to_thread`
  call sites quoted above.
- Frontend: `PlotlyChart`/`PlotlyComponent` remount behaviour on data change,
  `UploadModal`, `admin/`, `auth/`, `users/` — not measured.
- Bundle size and dynamic-import boundaries — `vite.config.ts` uses route-level
  `lazy()` (`app/routes.tsx:13-35`) plus a `manualChunks` split for
  react/mui/vendor/plotly; no size measurement was taken and no cost was named,
  so nothing was filed.
- `docs/09-database/indexes.md` prose versus `alembic/versions/` — not compared
  (PERF-009 already covers the GIN-reachability sentence).

---

## ID namespace note

`PERF-101 … PERF-108` are minted here. `PERF-001 … PERF-010` were already
occupied and validated in the prior pass for this phase, as recorded in
`.ai/plans/_code-context/11-performance-code-context.md`; at HEAD `a324875`,
PERF-001 (unbounded `get_by_graph_id`), PERF-002 (17-statement cascade),
PERF-003 (chunked write), PERF-008 (unbounded layout/graph lists) and
PERF-010 (fresh Redis client per call) are all remediated. None of the eight
findings above duplicates PERF-001 … PERF-010: they are a distinct root cause
(the model-level `lazy="selectin"` cascade reached through *other* repositories,
which the `noload()` fix added to `AggregatedDataRepository` does not cover),
plus one blocking call on the app loop, one count-by-materialisation, one
statement-count gap, and one frontend render cost.

`VAL-11-1xx` is left unoccupied: no validation-level finding was raised by this
pass.