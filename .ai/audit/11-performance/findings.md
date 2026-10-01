---
phase: 11-performance
executed: 2026-09-30
executor: auditor
problems-only: true
baseline: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
baseline-dirty: "M src/mkobi/config.py, M tests/test_config.py (+ 20 deleted .ai/ files, + untracked .ai/audit/0*-*/)"
baseline-final: eeb9a5e1ae4df195b9a4fa4f7c19b8834f8307d8
baseline-final-dirty: "M src/mkobi/settings/app.yaml, M tests/test_config.py (concurrent programme, in flight), 20 deleted .ai/ files, + untracked .ai/audit/{01..10,99}-*/"
findings: 10
by-severity:
  CRITICAL: 1
  HIGH: 2
  MEDIUM: 5
  LOW: 2
---

# Phase 11 — Findings

## Summary

The zone examined is what this system costs per request, per aggregate write, and per deferred
unit of work, and what bounds each. The dev stack was started with `.\Makefile.ps1 up` and driven
with real HTTP requests and in-process instrumentation against a synthetic dataset I loaded into
`aggregated_data` and then removed. The single most consequential thing found: the dashboard read
path has no bound of any kind on the number of aggregate rows it materialises, and one page view
of a four-graph dashboard totalling 375,000 rows reached **1,036.2 MB** peak RSS inside a container
whose declared limit is **1,073,741,824 bytes**, and the serving container was OOM-killed and
auto-restarted by `restart: unless-stopped` while that measurement ran. Two hypotheses the phase
invites were tested and came back false, and are reported as corrections rather than findings:
per-row predicate cost is **not** additive under an AND of equalities (PostgreSQL short-circuits),
and the JSONB containment form the index documentation recommends measured **2.6× slower** than
the form the code actually emits.

## Findings

### PERF-001 — One page view of a dashboard materialises every aggregate row in the serving process, and its peak exceeded the container's memory limit

**Severity** — CRITICAL

**Zone** — "4. Per-request materialisation: eagerly loaded collections and unpaginated result sets"

**Observation** — `AggregatedDataRepository.get_by_graph_id` (`src/mkobi/db/repositories/aggregated_data_repo.py:147-171`)
issues `select(AggregatedData)` with no `LIMIT`, no `OFFSET` and no row predicate other than
`graph_id`, `dashboard_id` and the caller's filters. `GET /api/v1/data/aggregated` with `graph_id`
absent (`src/mkobi/api/routes/data.py:162-197`) loops **every graph on the dashboard** and
concatenates the results. `DashboardView` requests exactly that shape:
`frontend/src/features/dashboards/ui/DashboardView.tsx:49` calls
`useAggregatedData(id || '', filters)` with no third argument, so `graph_id` is never sent
(`frontend/src/features/dashboards/api/dashboardApi.ts:62-78`). There is no bound anywhere in the
chain on the number of rows returned, on the number of graphs, or on the response size.

The cost is linear in the row count with a constant per-row factor. Measured on four graphs
(25,000 + 50,000 + 100,000 + 200,000 = 375,000 rows), each row read through the real repository
method in a fresh process:

| rows for one graph | read wall time | peak RSS | growth above the 103 MB post-import baseline | per row |
|---|---|---|---|---|
| 25,000  | 3.03 s  | 173.8 MB | 70.1 MB  | 2,941 B / 121 µs |
| 50,000  | 4.91 s  | 247.5 MB | 143.7 MB | 3,013 B / 98 µs |
| 100,000 | 8.69 s  | 390.0 MB | 286.8 MB | 3,007 B / 87 µs |
| 200,000 | 15.86 s | 679.2 MB | 576.3 MB | 3,021 B / 79 µs |

The whole-dashboard page view — the request the browser actually makes — measured **101.25 s**,
a **30.9 MB** response body, and **1,036.2 MB** peak RSS, i.e. **933.9 MB** above baseline, against
the app container's `memory: 1G` limit (`docker/docker-compose.yml:155`). `docker inspect` reports
`Memory=1073741824`; the peak reached **101.2 %** of it. The container was OOM-killed and
restarted by `restart: unless-stopped` (`docker-compose.yml:137`) during the run — its
`StartedAt` moved to `2026-09-30T17:05:31Z` and `OOMKilled=true` with the serving process gone.

**Evidence** — four in-process runs inside the app container, one per volume, each in a fresh
process so the peak-RSS high-water mark is not reused: 25k → `read_s=3.03 growth_mb=70.1
bytes_per_row=2941`; 50k → `read_s=4.91 growth_mb=143.7 bytes_per_row=3013`; 100k →
`read_s=8.69 growth_mb=286.8 bytes_per_row=3007`; 200k → `read_s=15.86 growth_mb=576.3
bytes_per_row=3021 us_per_row=79.3`. The page-view run reproduced the route's own loop shape
(`GRAPH name=PERF-AUDIT-GRAPH rows=200000 read_s=28.91 pydantic_s=27.20 peak_mb=1036.2` …
`PAGE_VIEW graphs=4 rows_total=375000 wall_s=101.25 resp_mb=30.9 peak_mb=1036.2
growth_mb=933.9`). An end-to-end HTTP call agreed: `GET /api/v1/data/aggregated?dashboard_id=…&graph_id=<200k>`
returned **200** in **53,432 ms** with **17,294,385** response bytes. `docker inspect mkobi-app-1`
→ `OOMKilled=true Memory=1073741824`.

**Consequence** — opening a dashboard is a normally-encountered action on a normally-encountered
path, and on the measured dataset it takes the serving process to the whole of the container's
memory budget and, in the reproduced run, past it. Because `docker/Dockerfile:179` starts
`--workers 4` inside that one container, the 1 GiB is the budget for four interpreters, so two
concurrent page views of this dashboard exceed it without any single request being unusual. The
row count that drives this is not fixed by the code: DP-003 makes `aggregated_data` grow by a
duplicate row set for every value-equal upload in append mode, so the same dashboard gets more
expensive with every upload and nothing reports the growth. After the OOM kill the container
restarts empty, which drops every in-memory session and the deferred work queue with it (TOPO-003).

**Recommendation** — put a bound on the read before anything else: a `LIMIT` with a deterministic
`ORDER BY` in `get_by_graph_id`, and a per-response cap in the `graph_id is None` branch of
`data.py` so one request cannot concatenate every graph on the dashboard. The client already
asks for one graph's worth of chart data per render, so serving a bounded page first and
paging the rest is a shape change the current `GraphDataResponse` already tolerates. Verify with
the same four-graph dataset: peak RSS must stay flat as the row count rises. Note that
`docs/09-database/indexes.md` and `src/mkobi/api/routes/data.py` both assume an unordered
full read, and DP-017 already records that the stored row order is never pinned — an `ORDER BY`
introduced here must be chosen deliberately, not left to the planner.

### PERF-002 — The read loads two eagerly configured relationships the response never reads, at a fixed 16 statements and 3.4 s per request

**Severity** — MEDIUM

**Zone** — "4. Per-request materialisation: eagerly loaded collections and unpaginated result sets"

**Observation** — `AggregatedData.dashboard` and `AggregatedData.graph` are both declared
`lazy="selectin"` (`src/mkobi/db/models/aggregated_data.py:96-107`). The read path therefore
issues the select-in statements after every read of the table, whether or not the caller needs a
dashboard or a graph object. The route needs neither: `data_service.py:213-216` reads
`record.dims`, `record.metrics` and `record.dashboard_id` and nothing else. Loading one
`Dashboard` row is not one statement — the `Dashboard` entity carries its own eager relationship
fan-out, which the measured statement inventory shows as nine further statements, and the
`graph` side repeats the same fan-out under a second alias (`dashboards` and `dashboards_1`).

**Evidence** — same 200,000-row graph, same session, same engine, best of three runs each after a
warm-up pass, statement counts captured with a `before_cursor_execute` listener:

| query shape | statements | min wall time |
|---|---|---|
| `select(id, graph_id, dims, metrics)` — the columns the response needs | 1 | 4.22 s |
| `select(AggregatedData).options(lazyload(dashboard), lazyload(graph))` | 1 | 7.53 s |
| `select(AggregatedData)` — what the repository actually issues | 17 | 10.93 s |

The 16 extra statements captured for the third row are: the entity select, then
`dashboards` + its fan-out (`graphs`, `processing_logs`, `dashboards_1`+`users`,
`dashboard_filter_values`+`filters`, `dashboard_access`, `processing_configs`), then
`graphs` + its fan-out, then the same eight again under the `dashboards_1` alias.

**Consequence** — 3.40 s and 16 round trips added to every single read of this table, in
exchange for two related objects the response discards. The cost is **fixed per request, not per
row**: the two select-in batches are deduplicated by distinct id, so with one dashboard and one
graph the extra work does not grow with the aggregate's size. It is nonetheless paid on every
dashboard render, on a container that has 1.0 CPU shared by four workers, and it scales with the
number of graphs whenever the `graph_id is None` branch runs — seventeen statements per graph.

**Recommendation** — these two relationships are never traversed by the read path; the smallest
change is to select the four needed columns as a Core statement in `get_by_graph_id` and return
rows rather than entities, which removes the 16 statements, the 3.40 s, and the ORM entity layer
in one edit. If the entity shape must stay, `lazy="raise"` on both relationships makes the cost
visible instead of silent. No shipped test asserts the statement count; nothing here is a
remediation blocker.

### PERF-003 — Replacing one aggregate is 202 statements in a single transaction, run inside the serving process's event loop

**Severity** — HIGH

**Zone** — "6. Background and batch work: cost, transaction width, and lock hold"

**Observation** — `StorageManager.save_aggregates(clear_old=True)`
(`src/mkobi/data/storage/manager.py:113-134`) issues a `DELETE` for the whole dashboard and then
re-inserts every aggregate row in chunks of `CHUNK_SIZE = 1000`
(`manager.py:56`, `_bulk_upsert` at `manager.py:311-350`), all inside the one session the worker
was handed. The statement count is therefore `ceil(N/1000) + 2` in the aggregate's row count, and
the whole run is CPU-bound work in the Python process rather than a set operation. That process
is the serving process: the consumer that calls it is a task on the serving process's own event
loop (`src/mkobi/app.py:131-143`), and Polars work is the only part offloaded to a thread.

**Evidence** — `save_aggregates(dashboard_id=…, aggregates=<200,000 rows>, clear_old=True)` invoked
directly on a real session and then rolled back: `WRITE clear_old=True statements=202
(executemany=200) returned=200000 wall_s=41.62 peak_mb=680.0 chunk_size=1000`; a second run with
warm caches took `REBUILD rows=200000 wall_s=19.61`. A 100 ms ticker running on the same event
loop for the duration of the rebuild: `EVENT_LOOP_TICK_100ms samples=183 max_gap_ms=409.7
p50_ms=101.00 p95_ms=123.88 ticks_over_200ms=4 (2.2%)`. `AFTER_ROLLBACK rows_in_graph=200000
(dataset intact=True)` confirms the measurement did not mutate the fixture.

**Consequence** — a re-upload of a 200,000-row aggregate holds one transaction open for 19.6 to
41.6 s and issues 202 statements inside the process that is also answering requests, and it
stalled that process's event loop by up to **409.7 ms** at a point during the run. A dashboard
with 1,000,000 aggregate rows implies 1,002 statements and roughly 100–200 s of the same. Two
corrections to the obvious reading, both measured: an independent reader is **not** blocked — with
the 200,000-row `DELETE` open and uncommitted on one connection, a reader on the same graph
returned in 0.145 s against a 0.117 s baseline and a reader on an untouched graph in 0.117 s
(MVCC, `READ COMMITTED`), so the cost is not read blocking; and the lock contention itself is
TXN-005's, which measured a 28.0 s wait on the same `DELETE` edge. What is this phase's is the
statement count, the transaction width, and the event-loop occupancy.

**Recommendation** — the per-row Python loop is the cost, not PostgreSQL. Replace the chunked
Python-side upsert with one set-based statement (`INSERT … SELECT FROM unnest` of the aggregate
frame, or a temporary table plus `INSERT … SELECT`) so the write becomes a single statement whose
cost is bounded by the store rather than by a 1,000-iteration Python loop; the existing
`ON CONFLICT … text("((dims)::text)")` target stays valid. Until then, move the whole rebuild off
the serving process's event loop, which is PERF-006's subject and TOPO-002's mechanism. Verify by
re-running the ticker: the max gap must stay near 100 ms. Nothing shipped asserts the statement
count, so nothing here is a remediation blocker.

### PERF-004 — The caller-supplied filter has no bound on key count, key length or value length, and the cost of widening it is the statement rather than the scan

**Severity** — MEDIUM

**Zone** — "3. Query cost under caller-controlled input"

**Observation** — `filters` arrives as a raw `str | None` query parameter
(`src/mkobi/api/routes/data.py:54`), is handed to `json.loads` with no schema behind it
(`data.py:109`), and each key becomes one equality predicate
`AggregatedData.dims[key].astext == str(value)`
(`src/mkobi/db/repositories/aggregated_data_repo.py:158-162`). Nothing in the chain bounds the
number of keys, the length of a key, or the length of a value: there is no Pydantic model, no
`max_length`, and no key-count check. Each predicate reaches the document column through a
**scalar text extraction** (`->>`), not a containment operator.

**The phase's additive-cost hypothesis is false, and the measurement says so.** Under an AND of
equalities PostgreSQL evaluates the most selective predicate first and short-circuits: at every
K ≥ 1 the plan reported `Rows Removed by Filter: 66667`, and execution time stayed flat while the
planner's cost estimate grew 5-fold. The caller-widened cost is the **statement**, not the scan.

**Evidence** — 200,000 rows, one graph, `EXPLAIN (ANALYZE)` on the exact predicate shape the
repository emits:

| filter keys | SQL text | planning time | execution time | plan cost |
|---|---|---|---|---|
| 0   | 143 B    | 1.63 ms | 106.8 ms | 12,501 |
| 1   | 322 B    | 1.62 ms | 231.2 ms | 12,559 |
| 5   | 802 B    | 1.73 ms | 120.4 ms | 14,126 |
| 20  | 2,852 B  | 2.37 ms | 76.6 ms  | 20,376 |
| 100 | 13,052 B | 8.86 ms | 201.0 ms | 53,709 |
| 200 | 26,148 B | 4.78 ms | 104.6 ms | — |
| 500 | 65,148 B | 28.41 ms | 1,445.7 ms | — |
| 1000| 130,148 B| 33.32 ms | 2,569.2 ms | — |

Execution time is dominated by the scan and by the returned row count, not by the key count. The
only bound in force is `docker/nginx/nginx.conf`, which sets `client_max_body_size 100m` and no
`large_client_header_buffers`, so the request line — and therefore the `filters` string — is
bounded by nginx's 8 KB default. That is a proxy artefact, not an application bound, and it does
not exist when the app is reached directly.

A second, smaller caller-controlled cost on the same line: `data.py:80-85` writes the raw
`filters` string into an INFO record on every request, and the project's own `JSONFormatter`
(`src/mkobi/core/logging_config.py:17-69`) has no field cap. Measured with that formatter:
283 characters for a fixed message, 296 at 1 key, 611 at 20, 1,121 at 50, 2,512 at 130.

**Consequence** — a single authenticated GET can force the server to parse, plan and transmit a
statement two orders of magnitude larger than the normal one, and to write a log record whose size
is the caller's, on a container with 1.0 CPU shared by four workers. The realistic width is capped
at roughly 8 KB of query string in the deployed nginx path, which bounds the planning cost at
tens of milliseconds — real but not large. The absent schema is the durable defect: it is the
only place on this read path where nothing in the code constrains what a caller sends. This is
**not** a re-file of EXT-003, which is the request *body* reaching the 413 handler; this is the
query-string parameter on the success path, and it is a different line in a different module.

**Recommendation** — replace the bare `str` with a bounded Pydantic model — a `dict[str, str]`
with a `constr` on both key and value, and a validator capping the number of entries at the
dashboard's own dimension count, which `get_available_dimensions` already computes
(`data_service.py:238-252`). That makes the cost of a widened filter a function of the dashboard's
shape rather than of the caller's query string, and it removes the log amplification when the
capped value is logged instead of the raw input. If a route-level cap is wanted as well, it
belongs on the query parameter, not only in the model.

### PERF-005 — One Pydantic model is constructed per row and its column list is discarded before the response is built

**Severity** — MEDIUM

**Zone** — "4. Per-request materialisation: eagerly loaded collections and unpaginated result sets"

**Observation** — `DataService._get_aggregated_data_with_session`
(`src/mkobi/services/data_service.py:208-219`) wraps **every** aggregate row in a
`ProcessingResultData`, and for each row builds `columns=list(record.dims.keys()) +
list(record.metrics.keys())` — two list allocations per row, one of which the response never
reads. The route then discards the rest of the model and keeps only `preview`
(`src/mkobi/api/routes/data.py:145-148`: `for item in single_result: if item.get("preview"):
single_data_points.extend(...)`). The merged dicts are then validated a second time by
`AggregatedDataResponse` / `GraphDataResponse` on the way out
(`src/mkobi/models/data.py:425-452`).

**Evidence** — 200,000 rows already resident in memory, best of three conversion passes:
`PYDANTIC per-row ProcessingResultData x200000 min_s=2.36`; then `RESPONSE validate+json_serialize
x200000 min_s=1.07 bytes=17294370`. In the page-view run the same conversion cost
`pydantic_s=27.20` for 200,000 rows and `pydantic_s=3.64` for 100,000 rows, and peak RSS rose
from 390.0 MB to 918.5 MB across the conversion in one instrumented run
(`D_service_ProcessingResult rows=200000 stmts=17 elapsed_s=10.27 rss_mb=918.5` against
`C_repo_get_by_graph_id rows=200000 stmts=17 elapsed_s=12.20 rss_mb=702.2`).

**Consequence** — a per-row conversion whose most expensive field is thrown away, followed by a
second full validation of the same data on the way out, on the critical path of every dashboard
render. It is the second-largest single component of the measured 101.25 s page view after the
row fetch itself. This is **not** a re-file of DP-002 or DP-003: those are about *which* aggregate
is computed and stored, and what happens to value-equal inputs. This is the per-request cost of
reading whatever is stored back out, which holds identically for a correct aggregate.

**Recommendation** — the route needs a list of merged dicts, so return that directly. Removing
the intermediate `ProcessingResultData` from the read path deletes 2.36 s per 200,000 rows, the
per-row `columns` lists, and one of the two full validations. `ProcessingResultData` stays in use
by the upload and result endpoints, so the model is not removed — only taken off this path.

### PERF-006 — The single consumer of the deferral queue sleeps half a second after every task, and its bookkeeping dictionaries never shrink

**Severity** — MEDIUM

**Zone** — "7. Work that executes inside the request tier"

**Observation** — the deferral mechanism is an in-process `asyncio.Queue`
(`src/mkobi/core/task_queue.py:28`) constructed with **no `maxsize`**, and its consumer is a
single coroutine on the serving process's own event loop
(`src/mkobi/app.py:131-143`):

```python
async def queue_worker() -> None:
    while True:
        try:
            await queue.process_next()
        except asyncio.CancelledError:
            break
        …
        # Small sleep to prevent busy-waiting when queue is empty
        await asyncio.sleep(0.5)
```

The comment states the intent — sleep only when the queue is empty — but the statement is
unconditional, so it runs after **every** completed task, not only an idle poll. The comment is
also wrong in the other direction: `process_next` awaits `self._queue.get()` (`task_queue.py:84`),
which blocks rather than raising, so the `except asyncio.QueueEmpty` arm at `task_queue.py:102`
is unreachable. The sleep is therefore paid once per task and never for idleness — the exact
opposite of what the line says. Three plain dictionaries alongside the queue —
`_statuses`, `_results`, `_errors` (`task_queue.py:29-31`) — receive one entry per enqueue
(`task_queue.py:45`, `task_queue.py:94`) and are never pruned.

**Evidence** — the exact loop shape from `app.py:131-143` driven against the real `TaskQueue`
class with 10 ms of work per task:

| backlog | work each | last task started at | sleep-imposed minimum |
|---|---|---|---|
| 1  | 10 ms | 0.00 s | 0.00 s |
| 4  | 10 ms | 1.53 s | 1.50 s |
| 20 | 10 ms | 9.72 s | 9.50 s |

Twenty tasks totalling 0.20 s of actual work took 9.72 s — a **48×** amplification, tracking the
`0.5 × (N−1)` minimum to within 0.22 s. Unboundedness: `QUEUE unbounded_maxsize=0`, and
`STATUS_DICT after 50 enqueues: statuses=50` with the same growth in `_results` and `_errors` once
tasks complete. Occupancy: the same loop runs the 200,000-row rebuild of PERF-003 inside the
serving process, which stalled that process's event loop by up to 409.7 ms.

**Consequence** — a backlog of accepted uploads drains at 0.5 s per unit regardless of how little
work each unit is, on a process with one declared CPU shared by four workers. Because
`default_queue` is a module-level global (`task_queue.py:159`), each of the four uvicorn workers
holds its own queue and its own single-consumer loop, so a backlog that lands on the worker that
accepted the upload cannot be drained by the other three. Nothing bounds the wait: the client is
told `status=UPLOADED, message="File uploaded successfully, processing queued"`
(`data_service.py:159-166`) with no queue position, no depth and no estimate, and
`_statuses`/`_results` grow without limit in the serving process, one entry per upload, for the
lifetime of the process.

**Merge vs adjacency** — TOPO-002 owns the mechanism (no `rq.Queue.enqueue` exists in `src/`, so
the deployed worker receives nothing) and TOPO-003 owns work lost on restart. Neither finding
measures the wait or the resident growth; those are this phase's, and they are adjacency, not a
re-file. Phase 10 owns whether the deployed path starts the consumer at all.

**Recommendation** — move the `await asyncio.sleep(0.5)` inside the idle branch, or drop it
entirely: `process_next` already blocks on `get()`, so there is no busy-wait to prevent. That
alone removes 0.5 s from every unit of deferred work. Give the queue a `maxsize` so a burst of
uploads is refused at the door rather than accepted into memory, prune `_statuses`/`_results` on
completion, and put a depth figure in the `UploadResponse` so a client can see the wait it is
being asked to accept. Moving the consumer out of the serving process altogether is the direction
the existing migration guide already describes; this finding is the cost of not having done it.

### PERF-007 — The serving tier can demand 120 connections from a store that admits 97, and four workers share one declared CPU

**Severity** — MEDIUM

**Zone** — "9. The ceiling each tier imposes"

**Observation** — the worker count is a **literal in the image entry point**, not derived from
the declared allocation: `docker/Dockerfile:179` ends in
`CMD ["uvicorn", …, "--workers", "4"]`, and the `app` service in
`docker/docker-compose.yml:88` sets no `command:`, so that literal is what production runs. The
per-process connection ceiling is a second literal, `pool_size=10, max_overflow=20`
(`src/mkobi/db/session.py:44-45`), with `pool_pre_ping=True` adding a round trip on every
checkout (`session.py:43`). Four processes × 30 = **120**. The store's own ceiling is
`max_connections = 100` with `superuser_reserved_connections = 3`, i.e. **97** usable — and it is
configured **nowhere**: neither compose file sets it, the `db` service
(`docker-compose.yml:16`) declares no `command:`, and no migration alters it. The declared
allocation *is* applied by the engine: `docker inspect` reports `NanoCpus=1000000000` for both
`app` and `db`, matching `cpus: '1.0'` at `docker-compose.yml:155-156`.

**Evidence** — `SELECT name, setting FROM pg_settings WHERE name IN ('max_connections',
'superuser_reserved_connections', …)` on the running dev store → `max_connections 100`,
`superuser_reserved_connections 3`, `shared_buffers 16384` (128 MB), `work_mem 4096`.
`docker inspect mkobi-app-1` → `Memory=1073741824 NanoCpus=1000000000`.

**CPU-bound, not I/O-bound** — which is the only answer that responds to worker count. For the
200,000-row read, the same scan cost **0.107 s of server-side execution time**
(`EXPLAIN (ANALYZE)` → `Execution Time: 106.836 ms`) against **4.22 s** to materialise the same
rows in the worker process (PERF-001's table, Core-column row). About 97 % of the request is work
inside the worker, so adding workers does not scale it: four workers are contending for the one
CPU the engine actually granted.

**Consequence** — the serving tier's worst-case connection demand is 120 against a store that
admits 97, so a burst of concurrent requests can have the pool waiting on connections PostgreSQL
will refuse, at which point every request fails together. Nothing today drives the pool to its
ceiling — this is a design-unbounded condition rather than a present large value, which is why it
is not graded higher. The present, measured problem is the CPU: 1.0 CPU for four workers against
a request that is 97 % worker-side CPU, and an event loop that PERF-003 stalls by up to 409.7 ms.

**Merge vs adjacency** — TXN-009 owns the pool parameters being literals in two differently-sized
engines with no setting behind either; TOPO-005 owns the four workers each running their own boot
preconditions and cleanup loop. This finding is neither: it is the multiplication of one process's
ceiling by the process count, compared against the store's ceiling, and the CPU/I/O split that
decides whether the worker count helps at all.

**Recommendation** — make the worker count follow the declared allocation rather than the
`Dockerfile` literal, and reconcile the two ceilings in one place: either set `max_connections` in
the `db` service explicitly to comfortably above `workers × (pool_size + max_overflow)`, or reduce
`pool_size + max_overflow` so the product fits the store's default. Both numbers are currently
invisible to an operator — the compose file declares a CPU limit and a memory limit, and neither
of the two numbers that actually determine whether the tier survives load appears anywhere. Pool
*configuration* semantics stay with phase 03; this is only the ceiling arithmetic.

### PERF-008 — Seven of the eight surfaces that return collections declare no row bound

**Severity** — MEDIUM

**Zone** — "4. Per-request materialisation: eagerly loaded collections and unpaginated result sets"

**Observation** — of the surfaces in `src/mkobi/api/routes/` that return a collection, exactly
one declares a bound. `GET /api/v1/admin/logs` is the only one with a `limit: int = Query(...)`
(`src/mkobi/api/routes/processing_logs.py:62`). The rest declare no `limit`, no `offset` and no
cursor:

| surface | route | bound |
|---|---|---|
| `GET /api/v1/dashboards/` | `dashboards_crud.py:48` | none |
| `GET /api/v1/dashboards/my` | `dashboards_crud.py:165` | none |
| `GET /api/v1/graphs/` | `graphs.py:142` | none |
| `GET /api/v1/users/` | `users.py:91` | none |
| `GET /api/v1/layouts/` | `layouts.py:122` | none |
| `GET /api/v1/filters/` | `filters.py` | none |
| `GET /api/v1/data/aggregated` | `data.py:39` | none |
| `GET /api/v1/admin/logs` | `processing_logs.py:62` | `limit` |

`get_filter_values` for one filter name returns `list[str]` with no bound either
(`src/mkobi/db/repositories/dashboard_filter_values_repo.py:30-59`), and that list is the
dimension's full cardinality: it holds one row per distinct value in the aggregate, so it grows
with the data exactly as the chart data does.

**Evidence** — route-by-route signature inspection of every `@router.get` in
`src/mkobi/api/routes/*.py` for `limit|offset|page|items_per_page`, which returns matches only in
`auth.py` (rate-limit call sites), `processing_logs.py:62` (`limit: int = Query(`), `upload.py`
and `client_errors.py` (limit *messages*, not query bounds). `aggregated_data` row bound: see
PERF-001, where the same unbounded read measured 375,000 rows and 30.9 MB on one request.

**Consequence** — the design has no row bound on any read surface but one. For the small
reference tables this is a negligible cost today and I did not measure a large one — the seeded
`bidb` holds 8 dashboards, 2 graphs and 7 users — and that is why this is not graded higher. The
cost is unbounded by design rather than small by volume, which is the condition the phase names,
and it is realised today on the one surface whose backing table does grow with user data:
`/data/aggregated`, measured in PERF-001. The per-page-view payload on the dashboard surface is
**30.9 MB** for 375,000 elements with no client-side or server-side bound on either.

**Recommendation** — add a `limit` (and an offset or cursor) to the collection routes, starting
with `/data/aggregated` where PERF-001's bound belongs. `/users/`, `/dashboards/` and `/graphs/`
are the next three, since each has a natural sort key already. The `filters` and `layouts`
surfaces are small by construction and can be left alone — bounding them would be ceremony.

### PERF-009 — The declared capacity objective has no instrument, and no instrument of any kind exists

**Severity** — LOW

**Zone** — "2. What the shipped performance instrumentation measures, and where it does not reach"

**Observation** — the deployment guide states a capacity objective:
`docs/10-deployment/deployment.md:377` — "**No premature scaling:** A single FastAPI instance
with 4 workers handles typical BI workloads. Scale horizontally only when metrics justify it."
The instruction is to scale on metrics, and no metric is defined, produced or collected anywhere
in the system. **Instrument verdict: un-reached** — there is no load harness, no profiler and no
telemetry of any kind.

**Evidence** — a search across `src/mkobi/**/*.py`, `pyproject.toml` and `docker/*.yml` for
`prometheus`, `/metrics`, `opentelemetry`, `sentry`, `statsd`, `datadog`, `py-spy`, `cProfile`,
`line_profiler`, `memory_profiler`, `locust`, `k6`, `wrk`, `ab -n`, `pytest-benchmark` and
`pyperf` returns **no match in any of the three trees**. The declared runtime dependencies
(`pyproject.toml`) contain none of them either.

Two documentation claims about the same read path were checked against the code and against the
planner, and both are wrong in ways that matter operationally.

`docs/09-database/indexes.md:82` describes `idx_aggregated_data_dims_gin` as "**Critical for
filter application** — when a user selects filter values, the backend queries `dims` using JSONB
containment operators to find matching data points." The backend emits no containment operator:
the only predicate is `dims[key].astext == str(value)`
(`src/mkobi/db/repositories/aggregated_data_repo.py:161`), which is a `->>` text extraction. The
index is reachable only through `@>`, so the code cannot use it — `pg_stat_user_indexes` reports
**0 scans** on `idx_aggregated_data_dims_gin` after the full measurement sequence, against a cost
of **9,848 kB per 200,000 rows**.

The stronger point is that routing the read through the documented operator would be a
regression, not a repair. Measured on the 375,000-row / four-graph table, filtering the 25,000-row
graph on `region = 'R07'`:

| predicate form | plan | execution time |
|---|---|---|
| `(dims ->> 'region') = 'R07'` — what the code emits | Bitmap Heap Scan on `idx_aggregated_data_graph_id`, 625 heap blocks | **11.14 ms** |
| `dims @> '{"region":"R07"}'` — what the doc describes | BitmapAnd of `idx_aggregated_data_dims_gin` + `idx_aggregated_data_graph_id` | **29.16 ms** |

The GIN scan returns 18,750 of 375,000 rows — 5 % of the table, because `region` has 20 distinct
values — so the extra index is not selective enough to narrow anything the `graph_id` equality
has not already narrowed.

**Consequence** — the capacity objective is unenforceable as written, so the decision it governs
("scale horizontally only when metrics justify it") has no input. And the index documentation
sends the next maintainer to a change that the measurement says would be 2.6× slower while
carrying a real 9.8 MB per 200,000 rows of write and storage cost for nothing. The two
`Index(...)` declarations for that index and for `uq_aggregated_data_dashboard_graph_dims`
(`src/mkobi/db/models/aggregated_data.py:50-61`) are not in themselves wrong; the written
justification is.

**Recommendation** — delete or correct the sentence at `indexes.md:82` so it describes the
operator the code actually emits, and state the index's real role (JSONB containment for
ad-hoc queries) rather than a filter path it does not serve. This is a documentation fix, not an
index removal: the unique expression index is load-bearing for `ON CONFLICT` (SPEC 3.6) and the
GIN index is cheap next to it. Separately, the capacity sentence at `deployment.md:377` should
either name the numbers that would trigger scaling or be marked as an unverified assumption —
and the smallest first instrument is a request-duration histogram on the dashboard read path,
which is where every finding in this phase landed.

### PERF-010 — Every protected request pays two sequential store round trips and opens two new store connections

**Severity** — LOW

**Zone** — "8. What a store-backed decision costs a request, and what an outage does to it"

**Observation** — `get_current_user_dependency` makes two revocation decisions, awaited **one
after the other** rather than overlapped: `is_token_revoked(redis_client, jti)`
(`src/mkobi/api/deps.py:506`) and then `is_user_tokens_revoked(redis_client, user_id)`
(`deps.py:526`), before the user row is even read. Both sit on the auth path of every protected
endpoint, ahead of the handler. Separately, `get_async_redis_client()`
(`src/mkobi/core/redis_client.py:33-52`) returns a **new** `aioredis.Redis` object on every call
rather than a shared, pooled client, and the request path calls it twice — once at
`deps.py:128` for the revocation client and once at `deps.py:144` for the temp-password store.

**Evidence** — `redis-cli info commandstats` sampled immediately before and after a single
`GET /api/v1/data/aggregated` on the running dev stack, delta reported:
`exists 2`, `hello 2`, plus one rate-limiter pipeline (`get 1`, `incrby 1`, `expire 1`,
`multi 1`, `exec 1`). The two `exists` calls are the two revocation decisions; the two `hello`
handshakes are two connection establishments, which is what a per-call client construction costs.

**Consequence** — two extra sequential network round trips on the critical path of every
authenticated request, plus two connection handshakes instead of two checkouts from a warm pool.
I did **not** measure this as a material latency: against a Redis container on the same compose
network, two `EXISTS` on a local socket is sub-millisecond, and no request in this phase showed a
latency attributable to it. That is why the grade is LOW — the count is a fact, the cost is not
yet one. The admitted-versus-refused question is deliberately not claimed here: the limiter's
`fail_closed` setting is CFG-006's and EXT-002's, and the revocation path's behaviour when the
store is absent is AUTH-008's. What remains this phase's is the per-request round-trip and
connection count, and its growth: the count is fixed now, but a client constructed per call cannot
be reused, so the handshake cost scales with request rate rather than with process count.

**Recommendation** — hold one module-level `aioredis.Redis` and let it own its connection pool,
returned by `get_async_redis_client()` instead of constructed there; the redis-py asyncio client
already pools internally, so this is a one-line change with no behaviour change on the store.
The two revocation checks can then be issued as a single pipelined round trip. Neither change
alters what is decided — both are pure transport — so this can land independently of the
outage-behaviour work in phases 04 and 10.

## Distribution

Every finding that carries weight lands on one component: the `aggregated_data` read path
(`aggregated_data_repo.py` → `data_service.py` → `data.py`), reached from the single browser
request a dashboard page makes. PERF-001, PERF-002, PERF-004, PERF-005 and PERF-008 are all
measurements of that path; PERF-003, PERF-006 and PERF-010 are the write, the deferral and the
auth prefix around it. The `app` container carries the most: one declared CPU and one declared
gigabyte, shared by four uvicorn workers, is the budget against which every number in this
report was measured. No finding lands on the store, the proxy or the browser.

## Cross-Finding Analysis

Two causes account for eight of the ten findings.

**No bound on the row count, anywhere in the read path.** `get_by_graph_id` has no `LIMIT`
(PERF-001), seven of eight collection routes have no `limit` (PERF-008), and the read loads two
unrelated relationships plus one Pydantic model per row regardless of what the response uses
(PERF-002, PERF-005). PERF-001 is the effect; the rest is the same absence expressed per layer.

**Deferred work runs in the serving process and is neither bounded nor measured.** The consumer is
a task on the request-serving event loop (PERF-003, PERF-006), the queue it drains is unbounded
and its dictionaries never shrink (PERF-006), and no instrument would have shown either
(PERF-009). PERF-003 and PERF-006 share the loop occupancy; TOPO-002 and TOPO-003 own the
mechanism, and this phase owns only the cost of the wait and of the residency.

PERF-004 and PERF-007 are independent of both, and of each other.

## Roadmap

Ordered by cause. Steps 1 and 2 are prerequisites for measuring anything that follows.

1. **Bound the read.** PERF-001, PERF-002, PERF-005, PERF-008. Add a `LIMIT` with a deliberate
   `ORDER BY` to `get_by_graph_id`, a per-response cap to the `graph_id is None` branch, and
   `limit` parameters to the collection routes. *Before step 2*: re-run the four-volume
   measurement and confirm peak RSS is flat as the row count rises. This is the only step that
   changes what a client receives, and it is the one that must land first — every other
   measurement in this report is taken against an unbounded read.

2. **Stop materialising what the response does not use.** PERF-002, PERF-005. Return rows from
   `get_by_graph_id` rather than entities; return merged dicts from the service rather than
   per-row `ProcessingResultData`. *Before step 3*: confirm the 17-statement read becomes a
   single statement and the response is byte-identical for a fixed fixture.

3. **Get the rebuild off the request path and out of a Python loop.** PERF-003, PERF-006. Replace
   the 1,000-row chunked upsert with one set-based statement, and move the consumer out of the
   serving process. *Before step 4*: the 100 ms event-loop ticker must stay near 100 ms across a
   200,000-row rebuild. Depends on step 1 — until the read is bounded, moving the writer only
   moves the cost.

4. **Bound and instrument the deferral.** PERF-006, PERF-009. Move the `asyncio.sleep(0.5)` into
   the idle branch, give the queue a `maxsize`, prune the per-task dictionaries, and add a
   request-duration histogram plus a queue-depth gauge. *Before step 5*: with telemetry in place,
   the capacity sentence at `deployment.md:377` can be replaced by a number.

5. **Reconcile the ceilings and the filter schema.** PERF-004, PERF-007, PERF-010. Bound the
   `filters` parameter with a Pydantic model, reconcile `workers × (pool_size + max_overflow)`
   against the store's `max_connections`, and return one pooled Redis client. These are
   independent of steps 1–4 and can run in parallel with them.

6. **Correct the index documentation.** PERF-009's second half. Fix `indexes.md:82` to describe
   the operator the code emits. Documentation only; do it last so the measured numbers in step 4
   can be cited alongside it.

## Rollout Safety

Step 1 is the only step that changes observable behaviour, and it is the one to stage. Any client
relying on an unbounded read will start receiving a truncated chart once a `LIMIT` is in place.
The failure is visible rather than silent — a chart renders with fewer points than the aggregate
holds — so it will be reported as "wrong data", not as an outage, which is the worse of the two
outcomes during a rollout. Land it with a limit high enough that the seeded dashboards are
unaffected, watch the histogram from step 4 for truncation frequency, then tighten. Note that
`ORDER BY` interacts with DP-017 (the stored row order is never pinned): an ordering added here
becomes the client-visible order, so it should be chosen to match the chart's axis, not inherited
from whatever the planner returns.

Step 2 is behaviour-preserving and reverts by reverting the commit; the only risk is a field the
response path reads that the Core-column form omits, which the byte-identical check in step 2
catches. Step 3 changes no response and reverts cleanly, but it must not land before step 1 —
moving the writer while the reader is unbounded relocates the cost rather than removing it. Step
4's `maxsize` on the queue is the one place where a bounded change can turn a previously-accepted
upload into a rejection; the rate limiter at `upload.py` already returns `RATE_LIMIT_EXCEEDED` for
a full queue's worth of rejections, so the client sees an error it already handles, but the
threshold should be set above any observed burst first. Steps 5 and 6 do not change behaviour.

## Appendices

### Measurement method

The dev stack was started with `.\Makefile.ps1 up` (services `db`, `migrate`, `app`, `redis`,
`rq-worker`, `frontend`) and reached at `http://localhost:8010`. All SQL ran read-only through
`.\Makefile.ps1 psql-c`. Python instrumentation ran as `docker compose … exec -T app python -`
with the script piped on stdin, so nothing was written into the repository.

**Dataset.** `aggregated_data` was empty at the start (0 rows, 144 kB total). A throwaway
dashboard `11111111-…` and four graphs were created, and 375,000 rows loaded, each row's `dims`
built by `jsonb_build_object` over a mixed-radix decomposition of a series index into a four-key
groupby — `region` (20 values), `year` (5), `category` (40), `sku` (50) — giving 200,000
distinct dimension tuples for the largest graph, so every row is distinct under the unique
expression index `(dashboard_id, graph_id, (dims)::text)`. `metrics` carries two keys,
`revenue numeric(12,2)` and `orders int`. The other three graphs hold 25,000, 50,000 and 100,000
rows of the same shape. The dataset is therefore **four graphs on one dashboard, 375,000 rows,
4 dimension keys and 2 metric keys per row** — a small groupby cardinality, which is the
generous case for row width and the pessimistic case for index selectivity. It is not
representative of a wide table (a 40-column groupby) or of a dashboard with 40 graphs, and both
of those would cost more, not less. Per-row costs of ~3.0 KB and ~79 µs should be read as
constants for this document width, not as universal ones.

**Cleanup.** `DELETE FROM dashboards WHERE id='11111111-…'` cascaded all 375,000 rows away; the
graph count returned to 2 and the dashboard count to 8, matching the pre-measurement state.
`VACUUM FULL aggregated_data` reclaimed the space, leaving 0 rows and 64 kB total. No repository,
staging, commit, revert or stash was performed at any point.

**Peak RSS** is `ru_maxrss` from `getrusage(RUSAGE_SELF)`, a high-water mark, so each volume was
measured in its **own** process; a single process reporting several volumes would report its own
maximum for all of them. The 200,000-row point was measured twice in separate processes
(576.3 MB and 578.1 MB of growth) as a consistency check.

**Timings** are best-of-three after one discarded warm-up pass wherever a variant was compared
against another, because run order and heap warmth moved the first measurement of each variant by
up to 15 s. The single-measurement numbers — the write path, the page view, the queue, the log
records — are marked as such and are not best-of.

### What could not be verified in this environment

- **Production worker model.** The dev `app` service overrides `command:` with `--reload`
  (`docker-compose.override.yml:109`), so all HTTP timings were taken against a **single**
  process. The four-worker figure in PERF-007 is arithmetic over the literal at `Dockerfile:179`
  and the pool literals at `session.py:44-45`, not a measured four-way contention. The per-process
  costs in PERF-001 and PERF-003 are unaffected by worker count and transfer; the CPU contention
  between concurrent requests is not measured and is left as the declared `cpus: '1.0'`.
- **Real upload volume.** No 800,000-row CSV was ingested. PERF-003's 200,000-row figure is
  measured; the 1,000,000-row figure in that finding is linear extrapolation, labelled as such
  and not used to grade it.
- **Concurrent load.** No load generator was run — none exists (PERF-009), and writing one was out
  of scope. Every timing here is a single-request or single-run measurement. No percentile, no
  throughput and no saturation point is claimed anywhere in this report.
- **Store latency and an unreachable store.** The request-path behaviour of the Redis-backed
  decisions with the store slow or absent belongs to EXT-001/EXT-002 and AUTH-008 and was not
  re-measured. PERF-010 claims the round-trip count only.
- **Health and probe materialisation.** Left to phase 10; this phase took no measurement that
  depends on a healthcheck contract.
- **A second baseline.** `baseline` and `baseline-final` in the front matter differ because the
  concurrent remediation programme committed three times during this audit. Every anchor cited
  here was re-pinned at `baseline-final` (`docker-compose.yml:152-158` for the app limits,
  `app.py:131-143` for the consumer loop, `session.py:43-46` for the pool literals,
  `Dockerfile:179` for the worker literal); the three commits changed `config.py`,
  `settings/app.yaml`, and added `UPLOAD__TEMP_DIR` to the `migrate` service plus two
  `FastAPI()` title/version lines, none of which touch a cited claim.
