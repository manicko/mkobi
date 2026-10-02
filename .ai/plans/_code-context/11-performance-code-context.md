# Phase 11 — Performance: code context

**Audit phase:** `11-performance`
**Report under decomposition:** `.ai/audit/99-validation/11-performance-validated-findings.md` (793 lines)
**Upstream provenance:** `.ai/audit/11-performance/findings.md` (10 `PERF-*` findings)
**Finding-ID prefix actually used by the report:** `VAL-11-` (7 findings: `VAL-11-001` … `VAL-11-007`).
The audited namespace `PERF-` (10 findings) is carried inside the disposition record and is preserved.
**Authority:** this document. Where it and the report disagree about *where* something is or *what it does*,
this document wins. Where they disagree about *identity*, the report's identifier set wins.

---

## 1. Scope and method

### 1.1 HEAD-vs-worktree split — the brief's premises were stale in three ways

| Brief said | Reality at inspection | Consequence |
|---|---|---|
| `HEAD` is `cea2d06` | `HEAD` is **`ab76989`** — two commits further | all measurements re-taken here |
| "another agent reported fresh uncommitted edits against `config.py`, `data_worker.py`, `tests/test_data_worker.py`, `docs/06-backend/configuration.md`" | those edits **landed as `ab76989`**. `git diff --stat` against them is **empty**. | treat as committed, not in-flight |
| paths `config.py`, `data_worker.py` … | the config module is **`src/mkobi/config.py`**, *not* `src/mkobi/core/config.py` (`core/` holds `security.py`, `redis_client.py`, `permissions.py`, `task_queue.py`, `logging_config.py`, `reconciler_lease.py`) | anchor drift, see §5 |

| commit | files | phase-11 relevance |
|---|---|---|
| `ab76989` fix(worker): aggregate rebuild declared lock + bounded wait | `src/mkobi/config.py` (+6), `src/mkobi/db/advisory_lock.py` (new, 169), `src/mkobi/workers/data_worker.py` (+20), `tests/test_advisory_lock.py` (new), `tests/test_data_worker.py` (+29), `docs/06-backend/configuration.md` (+1) | **touches the PERF-003 write path** — the chunked writer now runs under a declared advisory lock with a bounded wait. Directly intersects the event-loop-occupancy finding. |

Working tree is otherwise clean of production source: `git status --short` shows only **deletions** of 20
`.ai/**` files plus `frontend/coverage/**`, and **untracked** `.ai/plans/**` (9 plans + `_code-context/`) and
`.ai/tasks/*.yaml`. **No `src/`, `tests/`, `docs/` or `docker/` file is dirty.**

Sibling-plan state: plans `00`–`09` have landed. **`10-production-ops-remediation-execution.md` has NOT landed**,
though its code-context has (`.ai/plans/_code-context/10-production-ops-code-context.md`).

### 1.2 What I measured vs what I only read

**Measured** (read-only; no service started, stopped or reconfigured; app verified healthy afterwards at
`/health` → `{"status":"healthy","database":"connected"}`, `OOMKilled=false`, `RestartCount=0`, `StartedAt`
unchanged at `2026-10-01T08:49:36Z`):

| # | measurement | method |
|---|---|---|
| M1 | Redis client construction + revocation-check cost | ad-hoc `python -c` inside `mkobi-app-1`, N=20 × 3 interleaved rounds |
| M2 | predicate forms `->>` vs `@>`, 2 graph fractions | `EXPLAIN (ANALYZE, BUFFERS)` on a 62,500-row throwaway dataset |
| M3 | which index actually served M2 | `pg_stat_reset_single_table_counters` then `pg_stat_user_indexes` |
| M4 | filter-width curve K = 0…1000 | `EXPLAIN (ANALYZE)` sweep, plan node + planning/execution ms captured |
| M5 | read-path statement count | `before_cursor_execute` listener on the engine, real `DataService.get_aggregated_data` |
| M6 | read-path peak RSS, two shapes | `ru_maxrss` high-water mark, one volume per process |
| M7 | prize of the `selectin` cascade | same read via column projection (`dims`, `metrics`, `dashboard_id` only) |
| M8 | Polars loader + `group_by` memory, CSV and `.csv.gz` | `CSVLoader.load()` on 400,000 synthetic rows, `ru_maxrss` + `estimated_size()` |
| M9 | container resource limits | `docker inspect` (host config, as applied) |

**Only read:** all SQL/TS source anchors; `docs/09-database/indexes.md`; `docs/10-deployment/deployment.md`;
`docker/nginx/nginx.conf`; telemetry-instrument absence (`NO MATCH` over `pyproject.toml` + `src/mkobi/**`).

### 1.3 Measurement conditions — the Planner must re-measure under these

| condition | value |
|---|---|
| dataset | throwaway dashboard `22222222-…`, graphs `bbbbbbbb-…-050` (**50,000 rows, 20 regions**) and `bbbbbbbb-…-012` (**12,500 rows, 5 regions**); `dims` = mixed-radix bijection over region×year×category×sku so every tuple distinct; 4 keys / 2 metrics — mirrors the report's shape at **1/6 the volume**. **62,500 rows total.** |
| row volume vs report | report measured 375,000 rows (200k+100k+50k+25k); the validator deliberately OOM-killed the app. **I did not.** Every read was run in an **isolated short-lived process**, never through the serving process, and capped at 50,000 rows. |
| machine / container | Windows 11 host; `mkobi-app-1` dev service under `docker-compose.override.yml:119` `--reload` ⇒ **single-process timings**, never four-worker contention. |
| applied limits | `app`: `Memory=1073741824` (1 GiB), `MemorySwap=2147483648`, `NanoCpus=1000000000`. `rq-worker`: `Memory=536870912`, `NanoCpus=500000000`. `db`: `Memory=1073741824`, `NanoCpus=1000000000`. |
| cleanup | `DELETE FROM dashboards WHERE id='22222222-…'` cascaded all 62,500 rows. Final: `agg_rows=0, dashboards=9, graphs=2` — matches the state before I started. No `VACUUM FULL` (needs superuser; the table is 12 MB, negligible). |
| Redis timing caveat | the container runs 1.0 CPU shared by the app **and** my measurement process; the first round of any timing set is warm-up-biased. M1 is reported as a **median of 3 interleaved rounds**, not a single reading. |

---

## 2. Per-finding context

### VAL-11-001 — PERF-009's containment correction (CRITICAL)

**Verdict: substantiated in its conclusion; both of its numeric supports are refuted or not-reproducible.**

| claim | verdict | measurement / anchor |
|---|---|---|
| the code emits `->>`, never a containment operator | **substantiated** | `src/mkobi/db/repositories/aggregated_data_repo.py` → `AggregatedDataRepository.get_by_graph_id`: predicate is `AggregatedData.dims[key].astext == str(value)`. Anchor **exact**. |
| `docs/09-database/indexes.md:82` describes an operator the backend never issues | **substantiated** | line 82 verbatim: *"the backend queries `dims` using JSONB containment operators"* |
| the GIN index is unused by the application | **substantiated — stronger than the report** | after M2's four `EXPLAIN ANALYZE` runs (two of them containment), `idx_aggregated_data_dims_gin` → **`idx_scan=0`, `idx_tup_read=0`**. **Even `@>` never reaches it.** `pg_indexes` confirms the index exists. |
| "containment is 2.6× slower", sign flips with shape | **refuted** | M2, `->>` vs `@>`: **80 %-of-table graph 41.98 vs 103.55 ms (`->>` 2.5× faster)**; **20 %-of-table graph 6.77 vs 54.98 ms (`->>` 8.1× faster)**. Both plans are `Index Scan using idx_aggregated_data_graph_id` with the predicate as `Filter`. `->>` is faster in **both** shapes; only the magnitude varies. Neither form reaches the GIN, so this is not a GIN-vs-btree comparison at all. |
| restated size "9,872 kB / 5,265 kB per 200,000 rows" | **not-reproducible** | M2: GIN = **4,928 kB for 62,500 rows = 80.7 B/row**. Three published figures now disagree by **3×**: input 49.2, validator 26.3, mine 80.7 B/row. GIN size tracks *distinct keys and distinct values per document*, not row count. **No per-volume write-cost constant exists.** |
| the input's "0 scans" was a vacuous control | **inverted** | the validator's own counter-evidence (`idx_scan=2`, `idx_tup_read=37,500`) is **equally unattributed** — it too cannot be tied to any of the four plans it transcribed. In my run the GIN is scanned zero times. The control is vacuous in *both* directions. |

**Anchor drift:** `aggregated_data.py:50-61` (Index block) → actual **`51-62`**.

**Seams an implementor touches:** `docs/09-database/indexes.md` §4 `idx_aggregated_data_dims_gin` **Purpose** and
**Note** lines only. **Code must not change** — adopting `@>` is the inversion the report warns against. The
`Index(...)` declarations at `AggregatedData.__table_args__` are not wrong.

---

### VAL-11-002 — PERF-001's recommendation asserts a client behaviour its own observation refutes (HIGH)

**Verdict: substantiated — every anchor resolves, and the consequence is confirmed.**

| anchor | at HEAD | verdict |
|---|---|---|
| `DashboardView.tsx:49` — `useAggregatedData(id \|\| '', filters)` | **exact**, two arguments against a three-parameter signature | confirmed |
| `dashboardApi.ts` `getAggregatedData` | params at **64-65**, `graph_id: graphId` at **73**, `queryKey` at **69** (report cites 62-78 / 62-66 — minor drift) | confirmed |
| `data.py` — `graph_id is None` branch loops every graph | **exact**: `graph_id: UUID \| None = Query(default=None)`, then `graphs = await graph_repo.get_by_dashboard_id(...)` and a `for graph_item in graphs:` loop | confirmed |

So `graphId` is `undefined`, `graph_id` is omitted, the route takes the all-graphs branch, and one response
carries every graph. **The client half is a genuine blocker, not a nicety.**

**New seam the report does not name — a trap for the phase-13 half:**

```
dashboardApi.ts:69   queryKey: ['aggregatedData', dashboardId, filters]      ← graphId is NOT in the key
```

Threading `graphId` through `useAggregatedData` without adding it to `queryKey` makes every per-graph fetch
collide on **one** cache entry — the second graph's response overwrites the first, and TanStack Query serves
whichever resolves last. This is a correctness defect introduced *by* the fix.

**The other half** — a server-side `LIMIT` plus a deliberate `ORDER BY` in `get_by_graph_id` — is phase 11's.
**Landing it alone is the silent-truncation case the report's own Rollout Safety warns about**: all four charts
truncate simultaneously on the first page view after deploy, with nothing in the client signalling a shortened
response.

---

### VAL-11-003 — PERF-010 re-graded LOW → MEDIUM (MEDIUM)

**Verdict: the mechanism and the grade are substantiated; every absolute number in the report is wrong, and the
per-request client count is wrong.**

| claim | verdict | measurement (M1, median of 3 interleaved rounds, N=20) |
|---|---|---|
| `get_async_redis_client()` builds a fresh unpooled client per call | **substantiated** | `src/mkobi/core/redis_client.py` → returns a newly constructed `aioredis.Redis`. Dynamically: `distinct_objects=True`, `client_id 3362` then `3363`, `same_underlying_connection=False`. |
| the auth path builds **two** clients per request | **refuted** | `get_current_user_dependency` takes `redis_client: Any = Depends(get_redis_client_dependency)`, and **both** revocation checks (`is_token_revoked`, `is_user_tokens_revoked`) share that one client. **One** construction per protected request. The second call site is `get_temp_password_store`, a different dependency, reached only by flows needing a temp-password store. |
| 15.86 ms — "what the code does" | **wrong form, right magnitude** | that figure is two-fresh-clients + two checks. I measure that at **18.17 ms**. The **actual auth path** (one fresh client + two checks) measures **9.29 ms**. Overstated ≈2×. |
| 8.19 ms — "one shared client" | **refuted** | **1.32 ms**. The report's shared-client baseline is ~6× too high. |
| "~7.7 ms, 48 % of the prefix, attributable to the per-call construction" | **wrong mechanism** | constructing the client *object* costs **1.90 ms** and opens no socket. The cost is the **first-command connection establishment** on a cold client (cold open + ping = **8.12 ms**). The delta is real; the label "construction" is not. |
| the fix — one process-wide shared client, two checks pipelined | **confirmed, and larger than reported** | shared client **1.32 ms**; shared + pipelined **0.79 ms**. Against the true 9.29 ms baseline the saving is **~8.0–8.5 ms per protected request**. |

**Anchor drift:** `deps.py:506`/`526` → **`509`/`529`**; `deps.py:128`/`144` → **`131`/`147`**. Cause identified:
`git diff eeb9a5e..HEAD -- src/mkobi/api/deps.py` is **a docstring change only** (`get_db_dependency`, +3 net
lines). `redis_client.py` is byte-identical to the baseline. So the DI structure was identical when the report
measured it — **the "two calls … what the code does" reading was wrong at the baseline too**, not drifted into
wrongness later.

**Grade:** LOW → **MEDIUM stands.** "Materialisation a request pays for without needing it" fits, and a
connection opened per call and never pooled is unbounded by design. Only the arithmetic needs replacing.

---

### VAL-11-004 — PERF-004's short-circuit evidence (MEDIUM)

**Verdict: the primary correction is substantiated; the report's own replacement curve is refuted at this scale.**

| claim | verdict | measurement (M4, 50,000-row graph = 80 % of table) |
|---|---|---|
| `Rows Removed by Filter` is a property of the counter, not evidence of short-circuit ordering | **substantiated — decisively** | constant at **50,000 for every K ≥ 1** (K = 1, 5, 20, 50, 100, 200, 500, 1000). A rejected row is counted once regardless of which qual rejected it. |
| cost moves into execution past K ≈ 100, via `Parallel Bitmap Heap Scan … (loops=3)` | **refuted at this scale** | the plan stays **`Index Scan using idx_aggregated_data_graph_id` at every K up to 1000**. No parallel bitmap scan appears at any K. |
| "execution time rises 24×" (106.9 → 2,553.5 ms) | **refuted at this scale** | execution stays in a **16.4–33.1 ms band with no monotone trend** (K=0 23.28 → K=1000 14.32). Plan cost grows monotonically but only 4.31 → 9.31. |
| what *does* grow | **new measurement** | **planning time: 0.889 ms (K=0) → 37.971 ms (K=500) = 43×.** The original report's "the planner's cost estimate grew 5-fold" is directionally right; the validator's replacement curve is not. |

**The nginx bound — confirmed statically, not measurable here.** `docker/nginx/nginx.conf:18` sets
`client_max_body_size 100m` and **no `large_client_header_buffers` anywhere**, so the 8 KB request-line default
holds. `nginx` is production-profile only and **not running**, so the effective cap could not be measured.

**Anchor drift:** none material. `data.py:54` (`filters: str | None`) and `data.py:109` (bare `json.loads`,
no schema, no size bound) resolve exactly.

**Seams:** `data.py` `filters` parameter + parse; `AggregatedDataRepository.get_by_graph_id` filter loop.
Nothing bounds key count, key length or value length.

---

### VAL-11-005 — PERF-001's OOM reproduces; the recovery narrative does not (MEDIUM)

**Verdict: the container-limit arithmetic is substantiated exactly; the OOM itself is not-reproducible *in this
run* (deliberately not attempted); and the recovery claim is refuted structurally.**

| claim | verdict | evidence |
|---|---|---|
| the limit is 1 GiB at HEAD | **substantiated exactly** | M9: `Memory=1073741824`, `MemorySwap=2147483648`, `NanoCpus=1000000000`. Compose: `app` service declares `memory: 1G` + `cpus: '1.0'`. |
| the OOM reproduces | **not-reproducible in this run** | I did **not** drive the serving process; the report's own reproduction (`OOMKilled=true`, `memory.peak` 100.08 % of `memory.max`) stands on its own evidence. |
| per-process `ru_maxrss` ÷ container limit = "101.2 %" | **refuted as a units error** | different quantities. The cgroup counter is the defensible comparison. |
| `restart: unless-stopped` restarted the container | **refuted structurally** | the container's `StartedAt` is unchanged and `RestartCount=0`. Under `--reload` the reloader respawns on **file change**, not child death — so the container looks healthy to `docker ps` while serving nothing. |
| `--workers 4` in production | **substantiated** | `docker/Dockerfile` final `CMD` → `uvicorn … --port 8000 --workers 4`. Under this the master respawns the dead worker; the loss is the worker's in-memory queue and sessions. |
| dev `--reload` topology | **substantiated** | `docker/docker-compose.override.yml:119` sets `command: [… "--reload", …]`. |
| **anchor drift** | — | `Dockerfile:179` → **`docker/Dockerfile:183`**; `docker-compose.override.yml:109` → **`:119`**; `docker/docker-compose.yml:155-156` → **`:166-167`** (note `db` *also* declares `memory: 1G` + `cpus: '1.0'` at `:44-45`, which the report never distinguishes). |

**Independent memory measurement (M6), which prices the read path without the OOM:**

| read | rows | wall | RSS growth | B/row |
|---|---|---|---|---|
| ORM entity + eager cascade (current code) | 50,000 | 5.29 s | 162.3 MB | **3,402** |
| ORM entity + eager cascade | 12,500 | 1.72 s | 41.8 MB | **3,504** |
| column projection, no ORM entities | 50,000 | 2.20 s | 60.9 MB | **1,277** |

Linear in row count (3,402 vs 3,504 B/row across a 4× range). Report: 3,119–3,211 B/row; input: 2,941–3,021.
Same order, mine **6–15 % higher** — the factor is document-width dependent. Wall time 105.8 µs/row, which
**confirms the validator's correction** that the input's ~79 µs/row was optimistic.

**Ceiling headroom, measured:** 50,000 rows peaks at 279.8 MB = **26 %** of the 1 GiB budget. The report's
200,000-row graph peaked at 701.5 MB (65 %). Consistent with a linear curve crossing 1 GiB between 250k and
300k rows. **Any `LIMIT` chosen for safety must be justified against this curve, not the OOM anecdote.**

---

### VAL-11-006 — front-matter severity tally (MEDIUM)

**Verdict: stale-anchor, report-corpus-only. No code seam.**

Every sibling plan states the same scope rule: *"the audit corpus is not an implementation target."* No block
edits `.ai/audit/**`. Recorded here so no Implementor opens the report as a checklist. The per-finding bands
themselves are correct; only the `by-severity` front matter is transposed.

---

### VAL-11-007 — PERF-008's inventory cites `filters.py` (LOW)

**Verdict: substantiated; structural claim reproduces exactly.**

| claim | verdict | evidence |
|---|---|---|
| `src/mkobi/api/routes/filters.py` holds no route | **substantiated** | **6 lines** (report says seven), docstring only: *"Placeholder module for filters routes - CRUD endpoints removed."* No `APIRouter`, no `@router.get`. |
| the live surface is `filter_values.py` | **substantiated** | `router = APIRouter(tags=["dashboards"])`; `@router.get` decorator; endpoint `get_filter_values_endpoint`. Report cites `:38` — that is the **decorator** line; the `def` is later. |
| **"one bounded surface" reproduces exactly** | **substantiated** | a scan for `limit`/`offset`/`page`/`per_page` across `src/mkobi/api/routes/*.py` returns **exactly one** match: `processing_logs.py:62`. Route census: **23 `@router.get` sites**, matching the report. |
| `dashboard_filter_values_repo.get_filter_values` unbounded | **substantiated** | signature confirmed, returns `list[str]`, no bound. |

**Seams:** the seven unbounded collection routes identified in PERF-008; `filter_values.py`; the
`get_dims_values` distinct scan in `AggregatedDataRepository` (no bound either).

---

### PERF-001 … PERF-010 — disposition re-measured at `ab76989`

| ID | band | verdict here | key measurement / anchor |
|---|---|---|---|
| PERF-001 | CRITICAL | **substantiated** | no `LIMIT` in `get_by_graph_id` (exact); `data.py` all-graphs loop (exact); memory linear at **3,402 B/row**; ceiling 1 GiB applied; **202k-row OOM not re-attempted** |
| PERF-002 | MEDIUM | **substantiated, and larger than stated** | M5: **`statements=17`, identical at 12,500 and 50,000 rows** — structural, not per-row. But the 17 are **not** the two `AggregatedData` relationships: 1 data query + 1 `graph` + 2 `graphs` + **14** through `AggregatedData.dashboard` → `Dashboard`'s **nine** `lazy="selectin"` relationships. M7 prices it: **2.66× memory, 2.4× latency**. |
| PERF-003 | HIGH | **substantiated, now intersected by HEAD** | `CHUNK_SIZE = 1000`, `save_aggregates` clear-old branch, `_bulk_insert` / `_bulk_upsert` both chunked identically. **Not re-measured** (a write load risks the 1 GiB container). `ab76989` adds an advisory lock + bounded wait around this path — **read it before designing**. |
| PERF-004 | MEDIUM | **re-typed** — grade stands, both narratives wrong | see VAL-11-004 |
| PERF-005 | MEDIUM | **substantiated** | per-row `ProcessingResultData` with two list allocations; the route keeps only `preview`. Its cost is a **subset** of the M7 delta, not additive to it. |
| PERF-006 | MEDIUM | **already-fixed** | **see §5.1 — the entire subject was deleted** |
| PERF-007 | MEDIUM | **substantiated** | `session.py`: `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True` → **4 × 30 = 120**. All three container limits confirmed applied (M9). The `db` service also carries `memory: 1G`, unreported. |
| PERF-008 | MEDIUM | **substantiated, one row corrected** | see VAL-11-007 |
| PERF-009 | LOW | **substantiated** | telemetry-instrument search returns **NO MATCH**; `indexes.md:82` verbatim; `logging_config.py` `"maxBytes": 10 * 1024 * 1024` at **line 117 exactly** — file-handler rotation, not a field cap. **Anchored doc line drifted:** `deployment.md:377` (the "No premature scaling" capacity sentence) is now **line 468**; the file grew 425 → 516 lines. The sentence's content is unchanged and still names no number. |
| PERF-010 | LOW→MEDIUM | **re-graded; numbers refuted** | see VAL-11-003 |
---

## 3. Cross-cutting architecture and constraints

### 3.1 The request path and its DB round trips

One `GET /api/v1/data/aggregated?dashboard_id=…` triggers, on the all-graphs branch:

1. `check_dashboard_access` — permission check (`core/permissions.py`), own round trip.
2. `graph_repo.get_by_dashboard_id` — one query per dashboard.
3. **`for graph_item in graphs:`** — per graph: `AggregatedDataRepository.get_by_graph_id` (**no `LIMIT`, no `ORDER BY`**) → ORM materialises `AggregatedData` entities → `selectin` cascade fires.
4. `DataService._get_aggregated_data_with_session` — one `ProcessingResultData` **per row**, with `columns=list(dims.keys()) + list(metrics.keys())` and `preview=[{**dims, **metrics}]` — two list allocations per row.
5. The route keeps only `item["preview"]`; `columns` and `rows` are discarded.

**Measured statement shape (M5) — identical at 12,500 and 50,000 rows, so it is structural:**

| statements | what |
|---|---|
| 1 | the `aggregated_data` select |
| 3 | `graphs` (2 forms) — `AggregatedData.graph` + `AggregatedData.dashboard`'s backref |
| **14** | through `AggregatedData.dashboard` → `Dashboard`'s **nine** `lazy="selectin"` relationships: `accesses`, `users`, `layout`, `graphs`, `aggregated_data`, `filters`, `processing_config`, `processing_logs`, `filter_values` (each ×2) |

**The findable insight:** the read path never touches `.dashboard` or `.graph`. `AggregatedData.dashboard`
being `selectin` is what drags in a nine-relationship cascade. Flipping `lazy` on the two `AggregatedData`
relationships is the entry point, but the *cost being removed* lives on `Dashboard`. M7 prices it: **3,402 →
1,277 B/row (2.66×) and 5.29 s → 2.20 s (2.4×)**. The 1,277 B/row floor is the raw JSONB payload — irreducible
without changing the storage shape or paginating.

### 3.2 Aggregate read path and the JSONB shape

`dims` (JSONB, 4 keys) and `metrics` (JSONB, 2 keys) per row. Four indexes exist on `aggregated_data`
(`pkey`, `dashboard_id`, `dashboard_graph`, `graph_id`, `dims` GIN, `uq_(dashboard,graph,dims::text)`).
**Measured: the GIN index has `idx_scan=0` and is never chosen by either predicate form** — see VAL-11-001.
The filter predicate is a `->>` text extraction, one SQLAlchemy expression per key, built with no string
interpolation (so it is injection-safe; phase 07's `EXT-007` agrees).

`uq_aggregated_data_dashboard_graph_dims` is a **unique** btree on `(dashboard_id, graph_id, dims::text)` and is
**83,480 kB at 375,000 rows** per the report — **an order of magnitude larger than the GIN** (9,872 kB) and
larger than the table's own data. That is the largest single write-amplification object on this table and
neither report mentions it. **Phase 05's `DP-003` (duplicate rows from type-sensitive identity) multiplies it
without bound** — this is the real cost of `DP-003`, and it belongs to phase 05, not phase 11.

### 3.3 Polars memory behaviour on large uploads — **this is the phase-05 hand-over, now measured**

`CSVLoader` picks `_read_csv_lazy` above `lazy_threshold_mb` — but that path is
`pl.scan_csv(file_path, **read_kwargs).collect()`, which **materialises the whole file anyway**. There is no
streaming. Then `df.group_by(...).agg(...)` runs eagerly on the full frame.

**M8, 400,000 rows × 6 columns, measured inside `mkobi-app-1`:**

| quantity | CSV | `.csv.gz` (level 6) |
|---|---|---|
| on-disk | 8.73 MB | 1.41 MB (**6.18× gzip**) |
| `CSVLoader.load()` wall | **0.30 s** | **0.28 s** |
| RSS growth after load | 42.3 MB | 42.1 MB |
| `df.estimated_size()` | 12.6 MB | 12.6 MB |
| **expansion: in-memory ÷ on-disk** | **1.44×** | **8.9×** |
| **peak RSS growth ÷ on-disk** | **11.9×** | **29.8×** |
| `group_by().agg()` wall | 0.20 s | — |
| **RSS growth *during* `group_by`** | **61.1 MB** | — |

Two decision-relevant facts:

1. **The aggregation transient costs more than the load** (61.1 MB vs 42.3 MB) and is ~5× the frame's own
   `estimated_size()`. Phase 05's hand-over question — "the memory cost of the Polars aggregation" — is
   answerable: **it is real and it is the larger of the two.**
2. **A `.csv.gz` that passes the compressed-size check expands ~9× in DataFrame memory and ~30× in peak RSS.**
   This is the number phases 05 `C05-8`, 06 `C06-7` and phase 10 §6.7 are hard-blocked on.

**Premature-optimisation caution, stated explicitly.** The project forbids premature optimisation, and the
measurement says so here: 400,000 rows cost **0.30 s and ~103 MB peak RSS growth against the worker's
512 MiB limit** — comfortable. The load is *not* currently a performance defect. It is a **scaling ceiling**
whose number is now known. Treat `C05-8`/`C06-7` as *discharge-with-a-number*, not as *find-and-fix*.

### 3.4 Background-worker throughput and queue depth

| quantity | measured |
|---|---|
| RQ queue depth (`rq:queue:default`) | **0** |
| registered workers | **1** (`rq:worker:7e8a32ba…`), healthy |
| `WORKER_LIVENESS_TTL_SECONDS` | `DEFAULT_WORKER_TTL + 60` — the liveness threshold `9a77625` corrected |
| `MAX_RETRIES` / `BASE_DELAY_SECONDS` | 3 / 2 (exponential backoff on startup only) |
| `MAX_RATE_LIMITS` | none configured — **no rate limiting, no `worker_timeout`, no burst bound** |

**A new surface no report examined.** PERF-006 measured the *retired* in-process queue. Its RQ replacement has
**one replica, no `--burst`, no job timeout, no result TTL and no queue-depth alert** — a throughput ceiling
nothing in the repository bounds. Phase 05 `C05-8` and phase 06 `C06-7` both name "worker replica count" as
**phase 11's**; it is unmeasured and unpriced. `data_worker.py` is also the file `ab76989` just changed.

### 3.5 Connection-pool settings — **phase 01 owns `src/mkobi/config.py`**

`src/mkobi/db/session.py` → `get_async_engine`: `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`,
`pool_timeout=30`. **4 workers × 30 = 120 connections**, against a store whose `max_connections` is configured
nowhere. Phase 03 ruled this adjacency explicitly, three times: *"Whether `4 × 30` is the right number for the
deployment is phase 11's question and is not settled here."*

Confirmed applied (M9): app 1 GiB / 1.0 CPU; **worker 512 MiB / 0.5 CPU**; **db 1 GiB / 1.0 CPU** — the `db`
service's own 1 GiB is a limit no report states, and it is the store holding the 83 MB unique index.

### 3.6 Pagination and result-set sizes

Exact census: **23 `@router.get` sites**; **one** `limit: int = Query(` — `processing_logs.py:62`. Seven
collection surfaces are unbounded; `get_dims_values` (a `SELECT DISTINCT` over `dims`) is unbounded too. The
`filters` **query-string** parameter is separate: nginx's absent `large_client_header_buffers` caps the request
line at ~8 KB, which is the only thing bounding predicate count today.

### 3.7 Seam ownership across phases

| seam | owner | phase-11 exposure |
|---|---|---|
| **loader memory ceiling cost, `.csv.gz` expansion ratio, worker replica count** | **11** (05 `C05-8`, 06 `C06-7`) | **measured in §3.3 — this discharges it** |
| **pool sizing as a measured cost: is 4 × 30 = 120 right?** | **11** (phase 03, ruled adjacency 3×) | **unmeasured — see DP-3** |
| **EXT-002's 4 workers × ~59 s saturation projection** | **11** (phase 07 hands it over explicitly) | **unmeasured; the 59 s figure's basis is unverified** |
| **artefact volume layout, disk budget, backup, alerts** | **10** (06 `C06-4`, `C06-11`) | phase 06 owns the *ceiling*; phase 10 owns the *budget*. **The brief's phrasing conflates these.** |
| **artefact sweep byte/count ceiling** | 06 (`FAB-5`) / 10 (alert) / 05 (lifetime) | not phase 11's |
| **`processing_logs` retention sweep** | 03 `B10` (`DatabaseStarter.cleanup_old_logs`) | not phase 11's |
| **coverage mask** | 09 `TCO-7` / `DP-7` (+ 01, 08 `CQLT-7` manifest) | not phase 11's — **brief's claim confirmed correct** |
| **`src/mkobi/config.py`** | **01** | `ab76989` added 6 lines there; re-read before any config touch |
| **client half of the read bound** (`graphId` threading) | **13** | see VAL-11-002's `queryKey` trap |
| **`indexes.md:82` justification** | **11** (documentation-only) | VAL-11-001 |

---

## 4. In-flight and already-landed work

| change | state | symbol it touches | phase-11 consequence |
|---|---|---|---|
| `ab76989` — advisory lock + bounded wait around the aggregate rebuild | **landed** (HEAD) | `db/advisory_lock.py` (**new**); `workers/data_worker.py`; `src/mkobi/config.py` (+6 config keys); `tests/test_advisory_lock.py` (**new**); `tests/test_data_worker.py` (+29); `docs/06-backend/configuration.md` (+1) | **intersects PERF-003.** The 202-statement chunked rebuild now runs under a declared lock with a bounded wait. Any PERF-003 block must read the lock's wait budget — it may already have changed the event-loop-occupancy picture the report measured. **Also intersects the `ab76989` "bounded wait" as a *precedent*: a wait ceiling is now the house pattern.** |
| `2174895` + `cea2d06` — user-write unit of work | **landed** | `services/user_service.py`, `services/auth_service.py`, `tests/test_users_api.py` | caused the `deps.py` docstring shift; explains every `deps.py` anchor drift |
| `b646ef1`, `9a77625`, `a92b546`, `3848e7a` — lifespan teardown, RQ liveness, lease re-election, **in-process queue → RQ** | **landed** | `app.py`, `rq_worker_wrapper.py`, `core/reconciler_lease.py`, `core/task_queue.py` | **`3848e7a` deleted PERF-006's entire subject** |
| dirty tree | **no production source dirty** | — | only `.ai/**` deletions, `frontend/coverage/**` deletions, untracked `.ai/plans` + `.ai/tasks` |

**No other in-flight work intersects this phase.** `10-production-ops-remediation-execution.md` has not landed,
so the phase-10 hand-overs that block on phase 11 (the disk budget) have **no plan to coordinate with yet**.

---

## 5. Discrepancies and risks

### 5.1 The single largest drift: PERF-006's subject no longer exists

`3848e7a` replaced the in-process queue with RQ. **Every one of PERF-006's four anchors is gone:**

| anchor in the report | at `ab76989` |
|---|---|
| `task_queue.py:28` `asyncio.Queue()` with no `maxsize` | **deleted.** Module is **79 lines**; no `asyncio.Queue` anywhere |
| `task_queue.py:29-31` three unpruned dicts (`_statuses`, `_results`) | **deleted.** Resident-growth claim has no referent |
| `task_queue.py:84` `await self._queue.get()` blocking | **deleted** |
| `task_queue.py:102` unreachable `except asyncio.QueueEmpty` | **deleted** |
| `app.py:131-143` with `await asyncio.sleep(0.5)` at 141 | **deleted.** No `asyncio.sleep`, no consumer task, no `create_task` for a worker in `app.py` |

What replaced it is *better on every axis the finding complained about*: `get_rq_queue()` is `@functools.cache`d
("created once per process so a request does not open a new Redis connection on every submission"), the
blocking `get()` is gone, and the unbounded dicts are gone.

**And it is actively guarded.** `tests/test_task_queue.py::TestRetiredSymbolsRemoved` parametrises over
`["TaskQueue", "default_queue", "get_task_queue"]` and asserts the module exposes **none** of them.
A block that tried to discharge PERF-006 by reintroducing a bounded in-process queue **fails this test.**

**Verdict: `already-fixed`.** The measured 0.5 s-per-unit wait and the `_statuses`/`_results` resident growth
are not reproducible — the structure is gone. **The successor surface (§3.4: one replica, no burst bound, no job
timeout, no queue-depth alert) is unexamined by every report.** That is the real residue, and it is not
PERF-006.

### 5.2 Refuted recommendations

| # | what the report says | reality | risk if implemented as written |
|---|---|---|---|
| R1 | `indexes.md:82` should be fixed because "containment is 2.6× slower" | refuted (§2 VAL-11-001); the real reason is that **the code emits `->>`** | a maintainer re-tunes the justification to the *wrong sign* and refuses a correct change |
| R2 | "`@>` is 6.9× faster; do not adopt it" (the input's framing) | **the sign is opposite in both shapes I measured** | inverting the doc to `@>` on a performance claim that inverts per shape |
| R3 | PERF-004's acceptance criterion rests on "execution time stayed flat" | refuted — flat at *this* scale, and the report's own 24× rise is scale-dependent | an acceptance test asserts flatness and passes at 50k while failing at 200k |
| R4 | VAL-11-003's "7.7 ms attributable to the per-call construction" | the object costs 1.90 ms; the **first-command connection** costs ~8 ms | a fix that only caches the client object without understanding the cold-connect path measures no improvement and gets reverted |
| R5 | add a server-side `LIMIT` first, client `graphId` later | produces four truncated charts on first deploy | the exact silent-wrong-data outcome the report's Rollout Safety tries to prevent |

### 5.3 Stale anchors (drift table — resolve by symbol, never by line)

| report anchor | at `ab76989` | Δ | cause |
|---|---|---|---|
| `Dockerfile:179` | `docker/Dockerfile:183` | +4 | file path *and* line both wrong |
| `docker-compose.override.yml:109` | `:119` | +10 | compose rewrite |
| `docker-compose.yml:155-156` | `:166-167` (app) | +11 | compose rewrite; `db` also has `1G` at `:44-45`, undistinguished |
| `deps.py:506` / `:526` | `:509` / `:529` | +3 | docstring-only change |
| `deps.py:128` / `:144` | `:131` / `:147` | +3 | same |
| `aggregated_data.py:50-61` | `:51-62` | +1 | — |
| `deployment.md:377` | `:468` (file 425 → 516 lines) | +91 | docs rewritten |
| `filter_values.py:38` (endpoint) | `:38` is the **decorator**; `def` later | — | mislabelled, not stale |
| `filters.py` "seven lines" | **6 lines** | −1 | — |

`indexes.md:82`, `logging_config.py:117`, `manager.py:56`/`:113-134`/`:280-309`/`:311-350`, `data.py:54`/`:109`,
`session.py:43-45`, `redis_client.py:33-52`, `processing_logs.py:62`, `dashboard_filter_values_repo.py:30-32`,
`DashboardView.tsx:49` are all **exact**. `task_queue.py` and `app.py:131-143` are **gone**.

### 5.4 Tests that will break

| proposed change | test that fails | note |
|---|---|---|
| reintroduce any bounded in-process queue (the naive PERF-006 fix) | `test_task_queue.py::TestRetiredSymbolsRemoved` | fails by design; tripwire |
| thread `graphId` through `useAggregatedData` without touching the cache key | **nothing fails** | `dashboardApi.ts:69` `queryKey` omits `graphId` — **no test covers this** |
| flip `lazy` on `AggregatedData.dashboard` / `.graph` | `test_data_service.py::test_get_aggregated_data_uses_repository`, `::test_get_aggregated_data_with_filters`, `test_services_integration.py::test_get_aggregated_data_empty` | these assert the *service contract*, not the load shape — they should **not** break, and their staying green proves nothing about the fix |
| add `LIMIT` to `get_by_graph_id` | no test asserts a bound | **the fix would be unpinned**; a statement-count or bound assertion is the only thing that would catch a regression |

**No test anywhere pins the 17-statement shape or the eager-load behaviour.** A `lazy` change is invisible to
the suite. That is a phase-09 seam, not phase 11's.

### 5.5 Where "optimisation" would be a behavioural change in disguise

| change | what it really is |
|---|---|
| `LIMIT` on the aggregate read | **a behaviour change with a client dependency.** The response shape shrinks; every consumer that assumed completeness breaks. Phase 11 + phase 13, ordered client-first. |
| an `ORDER BY` added alongside the `LIMIT` | **a semantics change.** Today rows come back in whatever order the index scan yields; a deterministic order is a contract the response never made. |
| flattening `dims`/`metrics` into columns | **a schema change** — phase 14, plus a migration and a rewrite of every write path. Not a performance fix. |
| dropping the `uq_aggregated_data_dashboard_graph_dims` unique index | **would silently change `DP-003` behaviour** and break UPSERT conflict detection. It is the largest object on the table and the obvious size optimisation; it is the one change that must not be made for size alone. |
| **anything under §3.3's Polars path** | the measurement says **not a defect**. 0.30 s and ~103 MB against 512 MiB. Acting here is the premature optimisation the project explicitly forbids. |
| **the RQ worker replica count (§3.4)** | adding replicas is a **topology** change with a lease interaction (`reconciler_lease`), not a tuning knob. Phase 01 owns the model. |

### 5.6 Cross-phase propagation risk

Phase 10's code context cites *"PERF-001's 1,036.2 MB peak against the live 1 GiB app limit = 101.2 %"* as
corroboration. **VAL-11-005 already refuted that figure as a per-process-vs-cgroup units error.** A number this
phase's own validation has retracted is currently load-bearing in another phase's plan.

---

## 6. Decision points for the Planner — leave all open

I pick none.

| id | uncertainty | alternatives | chooser |
|---|---|---|---|
| **DP-11-A** | **Can the server bound land at all before phase 13?** | (a) client half first, server bound second; (b) bound + client atomically in one change; (c) bound behind a feature flag with the client opt-in | **Coordinator** — this is a cross-phase sequencing call, and (c) is the only option that avoids both silent truncation and an unbounded interim |
| **DP-11-B** | **What does `LIMIT` mean for chart correctness?** | (a) `LIMIT` + `ORDER BY` (deterministic, still truncates); (b) aggregate server-side (one point per dim-tuple — changes the chart's meaning); (c) per-graph bound + total-count in the response so the client can signal truncation | **Tech Lead + product** — (b) is not a performance fix, it is a semantic change to what a dashboard shows |
| **DP-11-C** | **Is `4 × 30 = 120` right, and what is the store's ceiling?** | (a) keep, document the budget; (b) reduce and make configurable; (c) reduce and set Postgres `max_connections` explicitly | **Tech Lead** — phase 03 ruled it phase 11's question and deliberately left the number open; `max_connections` is configured nowhere today |
| **DP-11-D** | **What is the worker's replica count and is one enough?** | (a) keep 1, document; (b) raise, and settle the `reconciler_lease` interaction; (c) keep 1 and add a queue-depth alert only | **Coordinator + phase 01** — this is topology, and §3.5's lease makes it more than a replica number |
| **DP-11-E** | **Should the unused GIN index be dropped, documented, or kept?** | (a) fix the doc only (the report's recommendation); (b) drop the index and reclaim ~5–80 B/row of write cost; (c) change the code to emit `@>` so the index becomes live | **Tech Lead** — (c) is the inversion VAL-11-001 warns against; (b) is a schema migration, so phase 14 |
| **DP-11-F** | **Which `lazy` change fixes PERF-002 — the two on `AggregatedData`, or all nine on `Dashboard`?** | (a) the two only (removes the cascade trigger, leaves the cascade); (b) all nine (fixes it everywhere, wide blast radius); (c) `noload`/`raiseload` at the query site only | **Tech Lead** — M7 measured the prize for the read path; nobody has priced what (b) does to the dashboard-config and admin paths that legitimately need those relationships |
| **DP-11-G** | **Is `PERF-001`'s grade still CRITICAL now that PERF-002's fix removes 2.66× of the memory?** | (a) yes, unchanged; (b) re-grade after PERF-002 lands | **Planner** — a sequencing artefact, but it changes block priority and should be an explicit choice |
| **DP-11-H** | **What is the disk-budget number phase 10 §6.7 and phase 06 `D-06-E` are hard-blocked on?** | (a) derive from §3.3's measured expansion factors; (b) wait for production observation; (c) set a conservative fixed ceiling | **Coordinator** — phase 10's own context says explicitly this is *not* phase 10's to invent and *not* phase 11's alone |

---

## 7. Coverage ledger

| finding | verdict | measurement / evidence anchor(s) |
|---|---|---|
| **VAL-11-001** | core **substantiated**; 2.6× claim **refuted**; size **not-reproducible**; its counter-evidence inverted | M2 · M3 · 80.7 vs 26.3/49.2 B/row · `get_by_graph_id` predicate · `indexes.md:82` |
| **VAL-11-002** | **substantiated** | `DashboardView.tsx:49` exact · `dashboardApi.ts` 64-65/69/73 · `data.py` loop exact · **new trap: `queryKey` omits `graphId`** |
| **VAL-11-003** | mechanism + grade **substantiated**; both numbers **refuted**; client count **refuted** | M1: 9.29 / 1.32 / 18.17 / 1.90 / 8.12 / 0.79 ms · `client_id 3362≠3363` · `hello` 736 ÷ `exists` 678 = 1.08 · `deps.py:131/147/509/529` |
| **VAL-11-004** | primary **substantiated**; replacement curve **refuted** | M4: `Rows Removed` constant 50,000 for K=1…1000 · `Index Scan` at every K · planning **43×** · `nginx.conf:18` |
| **VAL-11-005** | limits **substantiated exactly**; OOM **not-reproducible here** (not attempted); `restart` **refuted** | M9 · `override:119` · `docker/Dockerfile:183` · M6 3,402 B/row, 26 % of ceiling at 50k |
| **VAL-11-006** | **stale-anchor**, corpus only | no code seam; every sibling plan forbids editing `.ai/audit/**` |
| **VAL-11-007** | **substantiated** | `filters.py` **6 lines** · `filter_values.py` · one `limit` at `processing_logs.py:62` · **23** `@router.get` · `get_dims_values` unbounded |
| **PERF-001** | **substantiated** (OOM not re-attempted) | no `LIMIT` (exact) · 3,402 B/row linear · 1 GiB applied · ceiling crossing 250–300k rows |
| **PERF-002** | **substantiated, larger than stated** | M5 `statements=17` at two row counts · 14 via `Dashboard`'s **nine** `selectin` · M7 **2.66× / 2.4×** |
| **PERF-003** | **substantiated; not re-measured** (write load risks the ceiling) | `CHUNK_SIZE=1000` (exact) · both writers chunked · **`ab76989` wraps this path in a lock + bounded wait** |
| **PERF-004** | **re-typed** — grade stands, both narratives wrong | see VAL-11-004 |
| **PERF-005** | **substantiated** | per-row model, two list allocations · route keeps only `preview` · cost is a **subset** of M7, not additive |
| **PERF-006** | **already-fixed** | 4 anchors deleted by `3848e7a` · 79 lines, cached RQ queue · guarded by `test_task_queue.py::TestRetiredSymbolsRemoved` |
| **PERF-007** | **substantiated** | `session.py` 10/20/pre-ping → **120** · M9 · **`db` also at `memory: 1G`, unreported anywhere** |
| **PERF-008** | **substantiated, one row corrected** | see VAL-11-007 |
| **PERF-009** | **substantiated** | telemetry **NO MATCH** · `indexes.md:82` verbatim · `logging_config.py:117` exact · **`deployment.md:377` → `:468`** |
| **PERF-010** | **re-graded** LOW → MEDIUM (stands); numbers **refuted** | see VAL-11-003 |

**Symbols the report names that do not exist today:** `TaskQueue` · `default_queue` · `get_task_queue` ·
`asyncio.Queue` in `core/task_queue.py` · `_statuses` · `_results` · `except asyncio.QueueEmpty` ·
`await self._queue.get()` · `await asyncio.sleep(0.5)` in `app.py` · the queue-worker `create_task` in
`app.py` · any `large_client_header_buffers` directive · any `max_connections` setting for Postgres.
**Paths the report names that do not exist:** `Dockerfile` (it is `docker/Dockerfile`) ·
`src/mkobi/workers/task_queue.py` (it is `src/mkobi/core/task_queue.py`).
