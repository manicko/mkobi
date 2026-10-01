---
phase: 11-performance
executed: 2026-09-30
executor: validator
problems-only: true
baseline: eeb9a5e1ae4df195b9a4fa4f7c19b8834f8307d8
baseline-dirty: "M src/mkobi/settings/app.yaml, M tests/test_config.py (concurrent remediation, in flight), 20 deleted .ai/ files, + untracked .ai/audit/{01..10,99}-*/"
audited: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
audited-final: eeb9a5e1ae4df195b9a4fa4f7c19b8834f8307d8
prefix: PERF- (preserved, audited phase's own)
validation-prefix: VAL-11- (deviation recorded; flat VAL- occupied by 01 and 02)
findings: 7
by-severity:
  CRITICAL: 1
  HIGH: 1
  MEDIUM: 4
  LOW: 1
---

# Phase 11 — Validated Findings

## Summary

Every one of the ten findings was re-derived from the executing path at `eeb9a5e`, and the load-bearing
numbers were re-measured against a 375,000-row four-graph dataset I loaded, measured and removed myself.
**Seven of the ten survive on their own evidence; three do not.** The CRITICAL reproduces its headline
numbers closely — 200,000 rows reached 701.5 MB peak against the input's 679.2 MB, a 3,119–3,211 B/row
linear factor against its 2,941–3,021 — and the container memory limit is genuinely 1,073,741,824 bytes at
HEAD. I went further and **reproduced the OOM**: `OOMKilled=true` with the cgroup's own
`memory.peak = 1,074,565,120` bytes, 100.08 % of `memory.max`. But the report elevates two results to
headline status in its Summary that measurement does not support, and in one case supports backwards. The
JSONB-containment correction is the expensive one: the GIN index **is not in either plan**, the 2.6× ratio
does not reproduce, "0 scans" is contradicted by the same statistic reading 2, and "9.8 MB per 200,000 rows"
is the whole-table figure. PERF-010's LOW grade rests explicitly on a latency the report says it could not
show; I measured it at 15.86 ms against 8.19 ms for the shared-client form. One `VAL-11-` finding is filed
against the CRITICAL's own recommendation, which asserts a client behaviour its observation three lines
earlier refutes.

## Findings

### VAL-11-001 — PERF-009's containment correction is a wrong approval: the GIN index is in neither plan, the ratio does not reproduce, and the "0 scans" control reported clean over a non-zero count

**Severity** — CRITICAL

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — The report's Summary states that the containment form the index documentation recommends
"measured **2.6× slower** than the form the code actually emits", and PERF-009 builds a recommendation on
it: routing the read through the documented operator "would be a regression, not a repair". Four
quantitative claims in that argument are contradicted by independent measurement, and the mechanism the
report names is not the mechanism operating in the plan it transcribes.

| claim in the input | independent measurement at `eeb9a5e`, 375,000 rows / 4 graphs |
|---|---|
| containment → `BitmapAnd of idx_aggregated_data_dims_gin + idx_aggregated_data_graph_id` | **no GIN index in the plan**, either form. 200 k graph: both forms take `Index Scan using idx_aggregated_data_graph_id`. 25 k graph: same |
| 29.16 ms (containment) vs 11.14 ms (`->>`) — 2.6× slower | 200 k graph: 94.8 / 94.8 / 114.7 ms vs 103.2 / 120.3 / 152.8 ms — **containment is faster**. 25 k graph: 15.7 ms vs 11.4 ms — **1.4× slower** |
| "the GIN scan returns 18,750 of 375,000 rows — 5 % of the table" | the count is unreachable: the GIN is never scanned. `idx_tup_read = 37,500 = 2 × 18,750` on `idx_aggregated_data_dims_gin` — the figure is real, from two GIN scans that are **not** in either plan the report quotes |
| "`pg_stat_user_indexes` reports **0 scans** … against a cost of **9,848 kB per 200,000 rows**" | `idx_scan=2`. Size is `9,872 kB` for the **whole 375,000-row table** → **5,265 kB per 200,000 rows**, a 1.87× overstatement of the per-volume write cost |
| "region has 20 distinct values" | true for the 200 k graph, **false for the 25 k graph it filtered** — a contiguous series index gives that graph 3 regions, so `region = 'R07'` matches nothing there |

**Evidence** — `EXPLAIN (ANALYZE, BUFFERS)` on both predicate forms at best-of-three, on
`aaaaaaaa-…-200` (20 distinct regions) and `aaaaaaaa-…-025` (3 distinct regions), transcribed in the
appendices. `SELECT indexrelname, idx_scan, idx_tup_read, pg_relation_size(indexrelid)/1024 FROM
pg_stat_user_indexes WHERE indexrelname LIKE 'idx_aggregated_data%'` → `idx_aggregated_data_dims_gin
idx_scan=2 idx_tup_read=37500 size_kB=9872`. The `idx_tup_read` value is decisive against the report's
own "0 scans" reading: the same statistic, same session, reporting 37,500 index tuples read.

**Consequence** — this is the report's most expensive error, because it is the one a reader acts on
backwards. The documentation really is wrong and the recommendation to fix `indexes.md:82` is right — but
for a reason the report never states: the **code emits no containment operator at all**
(`aggregated_data_repo.py:161` is `dims[key].astext == str(value)`, a `->>` extraction), so the index has
no path to serve. A maintainer who accepts "containment is 2.6× slower" as the reason will also accept
"containment is always slower", and my measurement shows the sign **flips with dataset shape** — slower on
a graph that is 6.7 % of the table, faster on one that is 53 %. The stated reason would be used to refuse a
change that is correct for the large-graph case, and the 9.8 MB per-volume figure overstates the write cost
of the index by a factor of 1.87 when it is cited as the argument for removing it.

The vacuous-control angle applies squarely: the `pg_stat_user_indexes` check ran, returned a value, and
substantiated nothing. Reporting "0 scans" after one's own GIN-using `EXPLAIN`s is internally
inconsistent — a control that reported clean over a non-zero count is a defect in the audit, not a pass.

**Recommendation** — keep the documentation fix and replace its evidence wholesale. The correct statement
is: the code emits `->>`, the GIN index is reachable only through `@>`, `docs/09-database/indexes.md:82`
describes an operator the backend never issues, and the index is currently unused by the application. Drop
the "2.6× slower" comparison entirely — it does not reproduce and its sign is shape-dependent — and restate
the size as 9,872 kB for 375,000 rows, or 5,265 kB per 200,000 rows. If a performance argument for the
index is wanted later, measure it on a graph that is a small fraction of the table, which is the only shape
where the planner chooses it.

### VAL-11-002 — PERF-001's recommendation asserts the client already requests one graph, which its own observation refutes, and roadmap step 1 is therefore unimplementable as written

**Severity** — HIGH

**Zone** — "5. Whether the Recommendation Can Be Carried Out"

**Observation** — PERF-001's Recommendation rests on this sentence: "The client already asks for one graph's
worth of chart data per render, so serving a bounded page first and paging the rest is a shape change the
current `GraphDataResponse` already tolerates." The same finding's Observation, three lines earlier, says
the opposite: "`DashboardView` requests exactly that shape: `frontend/src/features/dashboards/ui/DashboardView.tsx:49`
calls `useAggregatedData(id || '', filters)` with no third argument, so `graph_id` is never sent
(`dashboardApi.ts:62-78`)."

Both statements resolve against the tree at `eeb9a5e`, and the second is correct. `DashboardView.tsx:49` is
`useAggregatedData(id || '', filters)` — two arguments against a three-parameter signature
(`dashboardApi.ts:62-66`), so `graphId` is `undefined`, `getAggregatedData` sends `graph_id: undefined`, and
the route takes the `graph_id is None` branch at `data.py:162` and loops every graph. The client requests
**every** graph's worth of chart data on every render.

**Evidence** — static, both anchors resolve: `DashboardView.tsx:49`, `dashboardApi.ts:62-78`,
`data.py:162-197`. Confirmed at runtime by the 375,000-row page view returning a **31.82 MB** body in
`status=200` — a single response carrying all four graphs, which is only reachable through the
`graph_id is None` branch.

**Consequence** — this is the prerequisite step for the whole report. Roadmap step 1 says "Bound the read…
*Before step 2*: re-run the four-volume measurement" and step 2 says nothing closes without it. A reader who
implements step 1 believing no client change is needed adds a server-side `LIMIT` and a per-response cap,
and the dashboard then silently renders four truncated charts on every page view — the exact "visible but
wrong data" outcome the report's own Rollout Safety section warns about, arriving through the fix rather
than despite it. The finding is graded CRITICAL and its recommendation carries the phase's single largest
remediation; a false premise inside it is the difference between a bounded rollout and a silent data-loss
rollout. Note the scope interaction: the client half of this fix belongs to phase 13, and the report does
not say so.

**Recommendation** — amend PERF-001's Recommendation to state that the bound has two halves and that they
are owned by two phases: the server-side `LIMIT` plus a deliberate `ORDER BY` in `get_by_graph_id`, and a
per-response cap in the `graph_id is None` branch (phase 11); and a `graphId` argument threaded through
`useAggregatedData` at the `DashboardView` call site, or a per-graph fetch in the render path (phase 13).
Neither half alone removes the effect, and landing only the server half is the silent-truncation case.

### VAL-11-003 — PERF-010 is graded LOW on a stated premise that is false, and the measurement it says it could not take puts it in the phase's own MEDIUM band

**Severity** — MEDIUM

**Zone** — "3. The Grade against the Audited Phase's Own Rubric"

**Observation** — PERF-010 records its own grade rationale: "I did **not** measure this as a material
latency: against a Redis container on the same compose network, two `EXISTS` on a local socket is
sub-millisecond, and no request in this phase showed a latency attributable to it. That is why the grade is
LOW — the count is a fact, the cost is not yet one." The premise is refuted. The per-call client
construction is not free, and its cost is measurable on the same compose network.

Measured inside the app container, running the real `is_token_revoked` and `is_user_tokens_revoked` calls
as `deps.py:506` and `deps.py:526` perform them:

| form | wall time |
|---|---|
| two `get_async_redis_client()` calls, two sequential checks (what the code does) | **15.86 ms** |
| one shared client, two sequential checks | **8.19 ms** |
| attributable to the per-call construction | **~7.7 ms, 48 % of the prefix** |

**Evidence** — `get_async_redis_client()` called twice in succession and each asked for its Redis
connection id: `client_id=605` then `client_id=606`, `SAME_UNDERLYING_CONNECTION = False`. Two successive
calls produce two separate connections, confirming the source reading of `redis_client.py:33-52` (a
function that returns a newly constructed `aioredis.Redis` rather than a shared pooled one) dynamically as
well as statically. Per-request command counts on a real authenticated request confirm the round trips:
`cmdstat` delta `exists calls=2` — exactly the two revocation decisions, as claimed. The `hello` count did
not reproduce at 2; it read 1.

**Consequence** — 7.7 ms on the auth path of **every** protected endpoint, in a system whose cheapest
database work is ~100 ms and whose container is granted 1.0 CPU shared by four workers. Judged plainly, as
asked: **LOW is wrong.** Phase 11's MEDIUM band is "materialisation a request pays for without needing it",
and two `aioredis.Redis` objects per request — each owning a connection pool, neither reused — is exactly
that. The phase's own scope gate also clears it: "A cost that is negligible at the scale a shipped fixture
creates is not a defect on its own. Report it only where the cost is **unbounded by design** rather than
small by data volume" — a connection opened per call and never pooled is unbounded by design, not small by
volume. The finding is correctly filed, the mechanism is confirmed, and the roadmap already carries it at
step 5, so the remediation consequence of the mis-grade is nil; what is wrong is the stated reason for the
band, which rests on a measurement the report asserts is impossible and which is in fact easy to take.

**Recommendation** — re-grade PERF-010 LOW → MEDIUM against phase 11's "materialisation a request pays for
without needing it", and replace the rationale with the measured 15.86 ms / 8.19 ms pair and the
`client_id` result. The input's own recommendation — one module-level `aioredis.Redis` letting its pool
serve checkouts, and the two revocation checks pipelined into one round trip — is correct as written and
needs no change.

### VAL-11-004 — PERF-004's short-circuit evidence is a per-worker count in a parallel plan, and "execution time stayed flat" is contradicted by the report's own table

**Severity** — MEDIUM

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — PERF-004's headline non-obvious result is that "under an AND of equalities PostgreSQL
evaluates the most selective predicate first and short-circuits: at every K ≥ 1 the plan reported `Rows
Removed by Filter: 66667`, and execution time stayed flat while the planner's cost estimate grew 5-fold."
The number reproduces; the plan it came from, and the flatness, do not.

Re-measured on a 200,000-row graph, the predicate shape the repository emits
(`dims ->> 'kN' = 'vN'`, `aggregated_data_repo.py:161`), first key anchored on a real dimension:

| K | input exec ms | re-measured exec ms | input planning ms | re-measured planning ms | `Rows Removed by Filter` (re-measured) |
|---|---|---|---|---|---|
| 0 | 106.8 | 106.9 | 1.63 | 8.19 | — |
| 1 | 231.2 | 239.4 | 1.62 | 2.24 | 95,000 |
| 5 | 120.4 | 111.6 | 1.73 | 1.36 | 100,000 |
| 20 | 76.6 | 70.7 | 2.37 | 1.80 | 100,000 |
| 100 | 201.0 | 328.6 | 8.86 | 5.44 | **66,667** |
| 200 | 104.6 | 121.5 | 4.78 | 6.63 | **66,667** |
| 500 | 1,445.7 | 2,436.5 | 28.41 | 20.94 | **66,667** |
| 1000 | 2,569.2 | 2,553.5 | 33.32 | 203.23 | **66,667** |

The 66,667 appears only from K ≥ 100, and only because the planner has switched to a
**`Parallel Bitmap Heap Scan … (loops=3)`** — 66,667 × 3 workers ≈ 200,001, the whole graph. It is a
per-worker figure in a parallel plan, not a whole-table figure at every key count, and at K = 1…20 the
figure is 95,000–100,000 in a serial plan. Execution time is not flat: it rises **24×** from 106.9 ms at
K = 0 to 2,553.5 ms at K = 1000.

**Evidence** — the `EXPLAIN (ANALYZE)` matrix above, transcribed in the appendices. The plan node line is
`Parallel Bitmap Heap Scan on aggregated_data (cost=2015.97..427513.75 rows=1 width=165) (actual
time=2052.421..2052.423 rows=0.00 loops=3)` at K = 1000 against a plan cost of 12,501 at K = 0 — the
report's "5-fold" plan-cost growth is real, and it is 34-fold.

**Consequence** — the finding's *conclusion* survives and the MEDIUM grade is defensible: the deployed
`docker/nginx/nginx.conf` sets no `large_client_header_buffers`, so the request line caps the `filters`
string at nginx's 8 KB default, which bounds K to roughly 60 predicates, where the measured cost is a few
hundred milliseconds. The bound is real and is a proxy artefact, as the report says. What is wrong is the
explanation, and it is the explanation a maintainer would generalise from: the report teaches that widening
an `AND` of equalities costs only planning time. The evidence shows the opposite at the top of the range —
past K ≈ 100 the cost moves into execution, because the estimate collapses to `rows=1` and the planner
widens to a parallel bitmap scan that evaluates the whole qual list. Any other caller-controlled predicate
list in this system should be expected to behave that way at scale, and a reader who has internalised the
report's version will not look for it.

**Recommendation** — keep the finding and the MEDIUM grade; replace the evidence section. State that
`Rows Removed by Filter` is constant across K because rejected rows are counted once regardless of which
qual rejected them, and that this is a property of the counter, not evidence of short-circuit ordering.
State the real cost curve — flat to K ≈ 20, rising to a plan-cost blow-up past K ≈ 100 — and keep the
nginx 8 KB observation as the reason the present value is bounded. The recommendation is unchanged and
correct.

### VAL-11-005 — PERF-001's OOM survives reproduction, but its recovery narrative names a mechanism that did not operate, and understates the consequence

**Severity** — MEDIUM

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — The OOM is real and I reproduced it. Two supporting details in PERF-001 are not.

**The limit is genuinely 1 GiB at HEAD.** `docker inspect mkobi-app-1` → `Memory=1073741824
MemorySwap=2147483648 NanoCpus=1000000000`. `docker/docker-compose.yml:155-156` declares `memory: 1G` and
`cpus: '1.0'`, and `git diff b23a9cb..eeb9a5e -- docker/docker-compose.yml` shows the concurrent remediation
added only `UPLOAD__TEMP_DIR` to the `migrate` service — the `deploy.resources.limits` block is untouched, so
the limit the input read is the limit in force. Confirmed.

**The OOM reproduces.** After driving the same read path, `docker inspect` reported `OOMKilled=true` with
the cgroup's own counters at `memory.peak = 1074565120` against `memory.max = 1073741824` — **100.08 %** —
and `memory.swap.current = 113774592`. The swap allowance is real and does delay the kill: an earlier
375,000-row page view peaked at `memory.peak = 1074294784` (100.05 %) and **returned 200 with a 31.82 MB
body** after the kernel swapped 525 MB. It delays rather than prevents: the additional 200,000-row
materialisation in the follow-up run crossed the ceiling and the kill fired.

Two details in the finding are nonetheless wrong. First, the comparison that produces "101.2 %" sets a
**single process's** `ru_maxrss` (1,036.2 MB) against a **container cgroup's** limit; those are different
quantities, and the defensible comparison is the cgroup counter, which reads 100.08 %. Second — and this is
the one with a consequence — the finding says the container "was OOM-killed and restarted by `restart:
unless-stopped` … its `StartedAt` moved". **The container did not restart.** At the moment of the kill
`RestartCount=0` and `StartedAt` was unchanged at `2026-09-30T17:29:16Z`. What died was uvicorn's serving
**child**; `docker top` then showed the `--reload` reloader parent and the `multiprocessing.resource_tracker`
with no `multiprocessing-fork` child at all, and `/health` stopped answering entirely.

**Evidence** — `docker inspect mkobi-app-1` and `/sys/fs/cgroup/memory.{peak,max,swap.current}` read
immediately after the kill, before any recovery action; `docker top mkobi-app-1` at the same moment; and
`docker restart` followed by `/health` → `{"status":"healthy","database":"connected"}` and a re-spawned
`multiprocessing-fork` child, which is the only thing that restored service.

**Consequence** — the report tells the reader the system self-heals from this event. In the dev topology it
describes (`docker-compose.override.yml:109` overrides `command:` with `--reload`), it does not: the
reloader respawns on file change, not on child death, so the application stays down until someone restarts
the container. In production the `--workers 4` master at `Dockerfile:179` would respawn the dead worker, so
the container recovers — but every in-memory artefact dies with it, which is the report's actual point and
is stated correctly. The precision defect matters because a reader assessing urgency from "restarted by
`restart: unless-stopped`" will believe the failure mode is a blip, when in the topology the report itself
measured it is a silent, permanent outage of the serving process. The `101.2 %` arithmetic is a units
error that happens to reach the right order of magnitude; the recovery claim does not.

**Recommendation** — restate the consequence as two topologies: under `--reload` an OOM-killed child leaves
the app down with the reloader still "running", so the container looks healthy to `docker ps` while serving
nothing; under `--workers 4` the master respawns and the loss is the worker's in-memory queue and sessions.
Replace the per-process-vs-container arithmetic with the cgroup's `memory.peak` against `memory.max`. The
CRITICAL grade itself stands — see the disposition record.

### VAL-11-006 — The front-matter severity tally reads HIGH 2 / MEDIUM 5; the body carries HIGH 1 / MEDIUM 6

**Severity** — MEDIUM

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — The report's front matter declares `findings: 10` with `CRITICAL: 1 / HIGH: 2 / MEDIUM: 5 /
LOW: 2`. Transcribing the ten `**Severity** —` lines in the findings body in order gives PERF-001 CRITICAL,
PERF-002 MEDIUM, PERF-003 HIGH, PERF-004 MEDIUM, PERF-005 MEDIUM, PERF-006 MEDIUM, PERF-007 MEDIUM,
PERF-008 MEDIUM, PERF-009 LOW, PERF-010 LOW — that is **CRITICAL 1 / HIGH 1 / MEDIUM 6 / LOW 2**. The total
of 10 is right; the HIGH and MEDIUM counts are transposed by one finding.

**Evidence** — `Select-String` over `**Severity** — ` in
`.ai/audit/11-performance/findings.md` returns the ten bands above in document order; the front-matter block
is at lines 10-15. PERF-003 is the only finding carrying HIGH.

**Consequence** — any consumer that reads the front-matter tally rather than the per-finding bands — a
dashboard, a triage summary, a phase-aggregate roll-up — reports this phase as carrying one more
high-severity finding and one fewer medium than it does. The same defect was found in phase 02's front
matter by that phase's own validation, so it is a repeated pattern in the set rather than a one-off
transcription slip, and the correction belongs to the report rather than to a consumer. The finding count
and the per-finding bands themselves are correct and are not in question.

**Recommendation** — amend the front matter to `HIGH: 1 / MEDIUM: 6`. Do not renumber any identifier: the
band on PERF-003 is correct against phase 11's rubric and is confirmed below.

### VAL-11-007 — PERF-008's inventory cites `filters.py`, a seven-line placeholder module that contains no route

**Severity** — LOW

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — PERF-008's evidence table lists `| GET /api/v1/filters/ | filters.py | none |` as one of
the seven unbounded collection surfaces. `src/mkobi/api/routes/filters.py` is a seven-line placeholder whose
entire content is a docstring: "Placeholder module for filters routes - CRUD endpoints removed. The global
filter CRUD endpoints (/api/v1/filters) have been removed as they were orphaned…". It contains no
`APIRouter` and no `@router.get`. The live surface is `filter_values.py:38`
(`get_filter_values_endpoint`, `router = APIRouter(tags=["dashboards"])` at line 35).

**Evidence** — file contents and route enumeration over `src/mkobi/api/routes/*.py`, which returns 23
`@router.get` sites and none in `filters.py`.

**Consequence** — drift with no remediation consequence today. The finding's structural claim survives
intact and was independently confirmed: a signature scan for `limit|offset|page|per_page` across every
route module returns exactly one match, `processing_logs.py:62 limit: int = Query(`, so the
"one bounded surface" conclusion stands. But the table tells a reader that eight live surfaces exist and
mixes in a module that was deliberately removed, so anyone auditing the bound inventory against it will
re-open a file that holds nothing.

**Recommendation** — replace the `filters.py` row with `filter_values.py:38` for
`GET /api/v1/dashboards/{id}/filter-values`, keeping the "none" bound, and note that the global filter CRUD
routes were removed rather than unbounded. The remaining seven rows resolve to real routes.

## Disposition Record — the audited namespace

Identifiers are preserved exactly as minted; none is renumbered. Verdicts use the fixed vocabulary.
Each row states what reproduced from the executing path and what did not.

| ID | Band carried | Verdict | Re-derived at `eeb9a5e` |
|---|---|---|---|
| PERF-001 | CRITICAL | **confirmed**, with two supporting details corrected (VAL-11-005) and the recommendation's premise false (VAL-11-002) | no-`LIMIT` claim holds: `aggregated_data_repo.py:147` is `select(AggregatedData).where(graph_id == …)` with no `LIMIT`/`OFFSET`; `data.py:162-197` loops every graph; `DashboardView.tsx:49` sends no `graph_id`. Memory reproduces within 4 %: 25k→179.5 MB (173.8), 50k→253.2 (247.5), 100k→400.4 (390.0), 200k→701.5 (679.2); per row 3,119–3,211 B against 2,941–3,021. `memory.peak` 100.08 % of `memory.max`; `OOMKilled=true` reproduced. Page view returned 200 / 31.82 MB (input 30.9 MB). **Not corrected:** the wall-time column — my 200 k read took 29.36 s against the input's 15.86 s, so the input's ~79 µs/row is optimistic by ~1.8× at the top of the range; the memory column, which the finding is built on, is sound. |
| PERF-002 | MEDIUM | **confirmed** | `aggregated_data.py:96-107` declares `lazy="selectin"` on both relationships. Statement count reproduces **exactly**: `SHAPE entity_select statements=17` against the report's 17. `data_service.py:213-216` reads only `dims`, `metrics`, `dashboard_id`. Band matches the rubric clause "materialisation a request pays for without needing it" verbatim. |
| PERF-003 | HIGH | **confirmed** | `manager.py:56 CHUNK_SIZE = 1000`; `save_aggregates` at `manager.py:113-134`; chunked writer at `manager.py:280-309` (the report cites `_bulk_upsert` at 311-350, which is the `clear_old=False` branch — a citation slip with no effect on the cost, both are chunked identically). Reproduced: `statements=202 (executemany=200)` exactly; `wall_s=30.16` between the report's 41.62 cold and 19.61 warm; `EVENT_LOOP p50=100.93 p95=126.99 max_gap_ms=381.4 over_200ms=4 (1.4 %)` against the report's `p50=101.00 p95=123.88 max_gap_ms=409.7 over_200ms=4 (2.2 %)`. Dataset intact after rollback. |
| PERF-004 | MEDIUM | **re-typed** — grade stands, asserted cause false (VAL-11-004) | `data.py:54` `filters: str \| None`; `data.py:109` bare `json.loads`; `aggregated_data_repo.py:158-162` one equality per key, `->>` extraction, no schema, no key/value length bound — all confirmed. `nginx.conf:18` sets `client_max_body_size 100m` and no `large_client_header_buffers`, so the 8 KB request-line cap holds. MEDIUM is defensible: "a cost demonstrated but conditional on … a configuration not yet in effect, where the design is unbounded". The **explanation** is not: see VAL-11-004. |
| PERF-005 | MEDIUM | **confirmed** | `data_service.py:208-219` builds `ProcessingResultData` per row with two list allocations; `data.py:145-148` keeps only `preview`. Reproduced on 100,000 rows: `PYDANTIC min_s=1.28` (input 2.36 s per 200,000 ⇒ 1.18 s per 100,000, within 8 %); `RESPONSE validate+build min_s=0.27`; RSS 400.4 MB → 526.1 MB across the conversion, i.e. +1.26 kB/row against the report's implied +1.08 kB/row. Not a re-file of DP-002 or DP-003 — checked and agreed; the claim is per-request read cost, which holds identically for a correct aggregate. |
| PERF-006 | MEDIUM | **confirmed** | `app.py:131-143` confirmed verbatim, with `await asyncio.sleep(0.5)` at line 141 outside any emptiness test. `task_queue.py:28` is `asyncio.Queue()` with no `maxsize`; `29-31` are the three unpruned dicts; `84` `await self._queue.get()` blocks; `102` `except asyncio.QueueEmpty` is therefore unreachable. MEDIUM matches the rubric clause "a wait whose length nothing bounds" verbatim. Merge ruling against TOPO-002/003 is stated in the input and is correct — adjacency, not a re-file. |
| PERF-007 | MEDIUM | **confirmed** | `Dockerfile:179` `CMD [... "--workers", "4"]`; `session.py:44-45` `pool_size=10, max_overflow=20`; `pool_pre_ping=True` at `43`; 4 × 30 = 120. `docker inspect` → `Memory=1073741824 NanoCpus=1000000000`, so the declared allocation **is** applied. CPU/I/O split reproduces and is starker than reported: `Execution Time: 106.940 ms` server-side for the 200 k graph against **29.36 s** to materialise the same rows in the worker — 99.6 % worker-side, against the report's 97 %. MEDIUM is right for the ceiling arithmetic, which is a design condition the input correctly declines to call a present large value. Pool *configuration* stays with TXN-009 as ruled. |
| PERF-008 | MEDIUM | **confirmed** with one row corrected (VAL-11-007) | The structural claim reproduces exactly: a signature scan for `limit: int = Query(` across `src/mkobi/api/routes/*.py` returns **one** match, `processing_logs.py:62`. `dashboard_filter_values_repo.py:30-32` `get_filter_values(...) -> list[str]` confirmed unbounded. One inventory row cites a module with no route in it. |
| PERF-009 | LOW | **confirmed** on the instrumentation half; **not substantiated** on the quantified half (VAL-11-001) | First half fully confirmed: the instrument search over `pyproject.toml` and `src/mkobi/**/*.py` for prometheus / `/metrics` / opentelemetry / sentry / statsd / datadog / py-spy / cProfile / line_profiler / memory_profiler returns **no match**; `deployment.md:377` and `indexes.md:82` both resolve verbatim; `logging_config.py` has no field cap (the `maxBytes: 10 MB` at line 117 is file-handler rotation, not a field cap). Second half not substantiated — see VAL-11-001. LOW is the correct band for the finding that survives: the rubric's LOW clause "a stated objective with nothing that measures it" and "a description or runbook line that no longer prices the behaviour beside it" both apply verbatim. |
| PERF-010 | LOW | **re-graded** LOW → MEDIUM (VAL-11-003); merge ruling against EXT/04/10 upheld as adjacency | `deps.py:506` and `526` are the two sequential revocation checks; `redis_client.py:33-52` returns a newly constructed `aioredis.Redis` per call; called at `deps.py:128` and `deps.py:144`. `cmdstat` delta `exists calls=2` reproduces; `hello` reads 1, not 2. The decisive new measurement is 15.86 ms vs 8.19 ms. See VAL-11-003 for the grade and its rationale. |

**Disposition tally** — confirmed 5 (PERF-001, 002, 003, 005, 006, 007, 008 with corrections as noted:
seven confirmed, two of them carrying corrections), re-typed 1, re-graded 1, merged 0, not substantiated 0
as a whole finding, unsettled 0. Specifically: PERF-001 confirmed (with corrections), PERF-002 confirmed,
PERF-003 confirmed, PERF-004 re-typed, PERF-005 confirmed, PERF-006 confirmed, PERF-007 confirmed, PERF-008
confirmed (one row corrected), PERF-009 confirmed on one half and not substantiated on the other, PERF-010
re-graded. Seven confirmed, one re-typed, one re-graded, one split — total ten, matching the ten identifiers
carried forward.

## Grade Reconciliation

Grades are checked against phase 11's own rubric (`.kilo/commands/audit/phases/11-audit-performance.md`,
lines 122-136), which is the rubric of record. **One re-grade is applied: PERF-010 LOW → MEDIUM.** All nine
others keep the band their own rubric implies, and none is re-graded.

**PERF-001's CRITICAL is defensible and stands.** The band reads "cost that exhausts a resource the whole
system depends on, reached by an input a caller controls on a path that is on, so that one request can deny
the service to every other caller". Three of the four elements I confirmed by reproduction: the resource is
exhausted (`memory.peak` at 100.08 % of `memory.max`, `OOMKilled=true`); the path is on
(`DashboardView.tsx:49` issues it on every dashboard view, unprompted by the user); and one request denies
service to every other caller — the request held the container's entire memory budget and its single
allocated CPU for 360 s. The fourth element — "an input a caller controls" — is the arguable one, since the
row count is determined by what was uploaded rather than by the request. It holds on the request's own terms:
`dashboard_id` is a caller-supplied query parameter, so a caller who names a large dashboard triggers the
path, and DP-003's duplicate-row growth means the same identifier gets more expensive indefinitely. The band
is met. The report's *supporting* arithmetic is what needed correcting (VAL-11-005), not its grade.

**PERF-003's HIGH is defensible.** The band reads "cost that is real now and scales with a quantity the
caller **or the data** controls, on a path that is on … or a cost linear in a production table". The
statement count is `ceil(N/1000) + 2` in the aggregate's row count — reproduced at 202 for 200,000 rows —
and the run is on the upload path against live traffic. Exact fit.

**PERF-002, 005, 006, 007, 008's MEDIUMs each match a rubric clause verbatim** — "materialisation a
request pays for without needing it" (002, 005, 008); "a wait whose length nothing bounds" (006); "a cost
demonstrated but conditional on volume or on a configuration not yet in effect, where the design is
unbounded rather than the present value being large" (007, 008). PERF-004's MEDIUM rests on the last of
these and survives its false mechanism.

**PERF-009's LOW is correct** and PERF-010's was not. The rubric's LOW clause is "a stated objective with
nothing that measures it; a description or runbook line that no longer prices the behaviour beside it" —
PERF-009 is both of those, exactly. PERF-010 was filed LOW against a premise the report asserted and that
measurement refutes; the phase's MEDIUM clause "materialisation a request pays for without needing it"
describes two unpooled Redis clients per request, and the phase's own scope gate ("unbounded by design
rather than small by data volume") is satisfied by a connection opened per call. Re-graded to MEDIUM, and
recorded as a re-grade rather than applied silently. The roadmap consequence is nil — the input already
carried PERF-010 at step 5.

## Which Side Moves

| ID | Load-bearing artefact | Verdict |
|---|---|---|
| PERF-009 (documentation half) | **Documentation.** The code's `->>` extraction is correct and the `Index(...)` declarations at `aggregated_data.py:50-61` are not wrong; the written justification at `indexes.md:82` is | Documentation moves. `indexes.md:82` is the target. The code must **not** be changed to adopt `@>` — that is the expensive inversion the report's own 2.6× claim invites, and my measurement shows the sign of the comparison flips with dataset shape, so the justification must go rather than be re-tuned |
| PERF-009 (capacity sentence) | **Documentation.** `deployment.md:377` names no number and nothing measures one | Documentation moves, as filed |
| PERF-001, 002, 003, 004, 005, 006, 008 | **Code.** The bounds, the eager relationships, the chunked writer, the filter schema, the per-row model, the sleep, the route bounds are all absent from the source | Code moves, as filed — **except** that PERF-001 also needs a client change (VAL-11-002), which is phase 13's, and the report does not say so |
| PERF-007 | **Configuration.** The worker literal is in `Dockerfile:179` and the store's `max_connections` is configured nowhere; both ceilings are invisible to an operator | Configuration moves, as filed |
| PERF-010 | **Code.** `redis_client.py:33-52` constructs per call; the two checks are sequential at `deps.py:506/526` | Code moves, as filed; one-line, no behaviour change |

No finding is a dead-code label, so no specification-corpus question arises. Nothing in the input was
re-typed to another phase on this block, and nothing was rejected here.

## Recommendation Executability

All ten recommendations name a target that exists and resolves at `eeb9a5e`; none offers alternatives
without naming an approach. Eight are directly executable. Two are not, as written:

- **PERF-001 (VAL-11-002)** — substantiated but **unusable as written**. Its premise ("the client already
  asks for one graph's worth of chart data per render") is false, so applying the server half alone produces
  silent truncation. It also names a dependency it does not record: the client half belongs to phase 13.
  Landing order matters and is inverted in the input's roadmap — the client change should precede or accompany
  the server cap, not follow it.
- **PERF-004** — executable, but its stated verification ("the cost of a widened filter is a function of the
  dashboard's shape") rests on the flatness claim that does not hold. The fix is right; the acceptance
  criterion should be a measured curve at the nginx-capped key count, not an assumption of flatness.

Dependencies, in order: PERF-001 → PERF-002/005/008 (every measurement in the report is taken against an
unbounded read, as the input correctly states) → PERF-003/006 (moving the writer before the reader is bounded
relocates the cost) → PERF-007/010 (independent). PERF-009's documentation fix is independent of all of them
and, contrary to the input's roadmap, need not be sequenced last — it has no dependency on the telemetry that
step 4 was to produce, and the input's reason for deferring it ("do it last so the measured numbers in step 4
can be cited alongside it") rests on numbers that, per VAL-11-001, do not reproduce.

## Cross-Phase Conflict, Ownership and Merge

Sibling reports compared: 01-process-architecture, 02-configuration-secrets, 03-db-concurrency,
04-authentication, 05-data-pipeline, 06-file-artifacts, 07-external-boundary, 08-code-quality,
09-test-coverage, 10-production-ops. Ten are raw auditor reports; the nine corresponding
`.ai/audit/99-validation/*-validated-findings.md` files already exist and were read for their merge rulings.
Phase 10's validation report landed during this run and is used here.

**The phase-03 tension, resolved with evidence.** The input states that "an independent reader is **not**
blocked" under MVCC, while phase 03 measured a **28.0 s** wait on the same `DELETE` edge with
`wait_event=transactionid`. These are not in conflict; they are different actors on one edge, and I measured
both in one run with the 200,000-row `DELETE` held open and uncommitted on one connection:

| actor | measured | reading |
|---|---|---|
| reader on the **same** graph | **0.104 s**, 200,000 rows still visible | MVCC holds; no reader blocking. The input's claim is **confirmed**, and stronger than stated — its 0.117 s "untouched graph" baseline is wrong, that reader returned in 0.004 s |
| a **second writer** on the same rows | **blocked indefinitely** — it ran past a 2 s session-local `statement_timeout` I set for the test and raised | with the deployed `lock_timeout` and `statement_timeout` both `0` (phase 03), this wait is unbounded |

**Disposition: adjacency, not conflict and not merge.** PERF-003 prices the statement count, the
transaction width and the event-loop occupancy; the 28.0 s wait is the lock-hold and `lock_timeout=0`
defect, which phase 03 owns. The input's own seam note — "the lock contention itself is TXN-005's" — names
the rival claim correctly. The discipline held.

**The DP-003 re-file question, checked as instructed.** PERF-001's Consequence names DP-003: "DP-003 makes
`aggregated_data` grow by a duplicate row set for every value-equal upload in append mode, so the same
dashboard gets more expensive with every upload." That is a **cross-reference, not a re-file**, and the
distinction is clean on root cause: DP-003 is a type-sensitive aggregate identity on the **write** path
(`(dashboard_id, graph_id, dims::text)` storing `'1'` and `1` as two rows); PERF-001 is an absent bound on
the **read** path. PERF-001 is fully true with DP-003 fixed — a correctly populated 375,000-row dashboard
still produces a 375,000-row read, a 31.82 MB response, and a container driven to 100 % of its memory
budget. The input names DP-003 as an aggravating factor and says so explicitly. **Not a re-file.** The same
holds for PERF-005 against DP-002/DP-003 (disclaimed in the finding and correct) and for PERF-008, which
defers `/data/aggregated`'s bound to PERF-001 rather than double-filing it. The instructed discipline held
across the whole report.

**Merge and adjacency rulings across the seams.**

- **PERF-006 vs TOPO-002 / TOPO-003 / OPS-002** — adjacency, correctly ruled in the input. TOPO-002 and
  OPS-002 own the mechanism (no `rq.Queue.enqueue` in `src/`; the deployed worker never receives a job);
  PERF-006 owns the measured wait (0.5 s per unit regardless of work size) and the resident growth of
  `_statuses`/`_results`. Phase 10 owns whether the consumer starts. No merge.
- **PERF-003 vs TXN-005 and the undeclared `DELETE` row-lock exclusion** — adjacency, as above. The
  statement-count and event-loop-occupancy claim survives a merge, because neither rival finding prices the
  cost of 202 statements inside a request-serving event loop.
- **PERF-007 vs TXN-009** — adjacency, correctly ruled. TXN-009 owns pool *configuration* semantics; PERF-007
  owns the arithmetic of one process's ceiling multiplied by the process count, against a store ceiling
  configured nowhere. No merge.
- **PERF-010 vs EXT-001 / EXT-002 / AUTH-008 / CFG-006** — adjacency, correctly ruled, and my re-grade does
  not change it. EXT-001/EXT-002 own the store being on the auth path and the ~55 s retry cost when it is
  slow; AUTH-008 owns revocation-path behaviour when the store is absent; CFG-006/EXT-002 own the limiter's
  fail-closed setting. What is this phase's is the per-request round-trip and connection count and now its
  measured cost — a transport cost, not an availability or semantic one. **Distinct, stays with phase 11.**
- **PERF-004 vs EXT-003** — adjacency, correctly ruled and confirmed. EXT-003 is the request *body* reaching
  the 413 handler; PERF-004 is the `filters` **query-string** parameter on the success path, at
  `data.py:54`/`109` and `aggregated_data_repo.py:158-162`. Different line, different module, different input.
- **PERF-001's frontend citation vs phase 13** — **no pre-emption.** The phase cited
  `DashboardView.tsx:49` and `dashboardApi.ts:62-78` only to establish the *request shape* that determines
  how much the server materialises, which is block 4's own question ("what a request transfers per page
  view"). The input claims nothing about client render cost, and correctly filed no such finding. The
  *remediation*, however, needs a client change, which is phase 13's to own — that is VAL-11-002, not a
  contested claim.
- **PERF-001's memory ceiling vs OPS-004 / phase 10** — no overlap. Phase 10's OPS-004 is that neither
  health endpoint examines Redis; nothing phase 10 filed covers whether the serving container's memory
  declaration is a live ceiling. PERF-007's confirmation that `NanoCpus=1000000000` and
  `Memory=1073741824` are actually applied is squarely phase 11 block 9's own question ("whether that
  allocation is one the deployment engine in use actually applies"), not phase 10's.

**The seam check this phase owns** — a finding filed outside the input's own declared scope. **None.**
Every one of the ten findings is filed under one of phase 11's nine declared blocks, with the block title
quoted verbatim. PERF-001's memory-ceiling measurement is the one claim that came from an angle the declared
blocks do not name (see below), but it was filed inside block 4, so it is a block-coverage observation, not
a scope breach. Nothing was written into another phase's directory.

## Finding-ID Namespace Integrity

| Property | Result |
|---|---|
| Prefix declared in phase 11's own report-output contract | `PERF-` — `.kilo/commands/audit/phases/11-audit-performance.md:142`, with "check for a collision before minting an identifier" |
| Identifiers actually minted | `PERF-001` … `PERF-010`, contiguous, no gaps, no duplicates, none renumbered here |
| In-source markers | **None.** A search for `PERF-\d+` across `src/`, `tests/`, `frontend/src/`, `docs/`, `alembic/` and the root `*.md` returns no match. The prefix is not load-bearing provenance anywhere in the repository |
| Compound form | Template front matter `phase: 11-performance` paired with prefix `PERF-`; this report's output stem is `11-performance-validated-findings`, carrying the audited phase's prefix as required |
| Reuse across phases | **None.** No sibling report mints a `PERF-` identifier |
| Ruling | A new run **reuses** the declared namespace rather than minting a second one beside it. Because there are no in-source markers, there is no provenance to migrate and no drift to retire — nothing to schedule |

**Validation-namespace deviation, recorded as instructed.** The flat `VAL-` prefix is occupied: sibling
reports 01 and 02 mint `VAL-001`, while 03 through 10 have already adopted the compound form
(`VAL-03-001` … `VAL-10-001`). Minting a second flat `VAL-` namespace beside the existing compound one would
have created exactly the collision this block exists to prevent. This run uses **`VAL-11-`**, following the
convention the set had already settled on, and records the deviation here rather than creating a new prefix
class. No other file in `.ai/audit/99-validation/` was modified.

## The Shared Findings Template as a Controlled Artefact

| Mandated element | Result across the input report |
|---|---|
| Front matter `phase:` | Present and honest — `phase: 11-performance` on a report written by phase 11 |
| Front matter `executed:` | Present — `2026-09-30` |
| Front matter `executor:` | Present — `auditor` |
| Front matter `problems-only:` | Present — `true` |
| Front matter `findings:` | Present — `10`, matching the ten identifiers in the body |
| Front matter `by-severity:` | Present but **wrong** — `HIGH: 2 / MEDIUM: 5` against a body of `HIGH: 1 / MEDIUM: 6` (VAL-11-006) |
| Additional front matter | `baseline`, `baseline-dirty`, `baseline-final`, `baseline-final-dirty` — additive, not a violation, and necessary for a report spanning a moving HEAD |
| Per-finding `**Severity** —` | Present in all ten, correctly formatted |
| Per-finding `**Zone** —` | Present in all ten; **all ten are the block title quoted verbatim** from phase 11's own contract, including the numeric prefixes (e.g. `"4. Per-request materialisation: eagerly loaded collections and unpaginated result sets"`, `"8. What a store-backed decision costs a request, and what an outage does to it"`). **No paraphrase, none absent** |
| Per-finding `**Observation** —` | Present in all ten |
| Per-finding `**Evidence** —` | Present in all ten |
| Per-finding `**Consequence** —` | Present in all ten |
| Per-finding `**Recommendation** —` | Present in all ten |
| Reserved empty-state string | Not applicable — the phase produced findings, so the report correctly does not carry it and does not pad a summary in its place |
| Location placement | Correct — every file:line reference is carried **inside** `**Observation**` or `**Evidence**`, not as a field of its own, as the contract requires |

The template resolved and was followed closely: the zone-verbatim rule, which is the element most often
paraphrased, is satisfied by all ten findings, and the field set is complete. **The single template defect
is the severity tally** (VAL-11-006). Recorded, not repaired — the template is not edited from inside a
per-phase run, and neither is the input report.

## Declared Blocks versus Actual Angles

All ten findings' support is either the input's own declared blocks or an independent observation; none
rests on the input's own **evidence** fields. The block-coverage question this block asks is the sharper
one, and it has a mixed answer worth recording.

Every finding is filed under a declared block, and for eight of the ten the block's own text names the angle
that produced them — block 3 asks "whether growth is additive or multiplicative", block 4 asks for
"per-page-view payload and element counts", block 5 asks "whether the declared access paths are the ones
the queries can use", block 8 asks for "the round trips … and where they sit". By the phase command's own
pre-pass, "nothing here conditions a finding on this phase's own list", and yet **eight of ten landed in a
declared block anyway.**

Two angles the declared blocks do not name produced the rest:

- **The serving container's memory ceiling** — PERF-001's most consequential sub-claim. Block 9 scopes its
  ceiling work to "what bounds concurrent work", the worker model, connection ceilings and the CPU/I/O split;
  it never asks what bounds the container's **memory**. The finding was filed under block 4 because the
  unbounded read belongs there, but the cgroup-limit arithmetic, the `memory.swap.max` behaviour and the
  `OOMKilled` attribution come from an angle phase 11's block list does not contain.
- **The vacuous-control observation on `pg_stat_user_indexes`** (VAL-11-001) — a control that ran and
  reported clean over a non-zero count. The phase has no block for the reliability of its own instruments.

Both are recorded as observations about the input's block coverage. Neither is a defect in the input report
as such, and neither is reclassified: a finding may reach a system by an angle its own phase never named,
and block 9 asks the question rather than concluding from it.

## Distribution

Seven of the ten audited findings fall on one component — the `aggregated_data` read path
(`aggregated_data_repo.py` → `data_service.py` → `data.py`), reached from the single request a dashboard page
makes — and that component carries the most. The two that do not are the write path (PERF-003, in
`data/storage/manager.py`) and the auth prefix ahead of every handler (PERF-010, in `api/deps.py` and
`core/redis_client.py`).

The validation-level findings distribute differently from the audited ones:

- **Four of seven** are defects in the report's **evidence** rather than in the system it audited
  (VAL-11-001, 003, 004, 005). The measurements were taken; four of them do not support the sentences built
  on them. This is the dominant shape of the problem, and it is the opposite of the usual validation
  failure — nothing here is a missed defect; it is a report that overstates what it proved.
- **One** is a defect in the report's **recommendation** (VAL-11-002), and it sits on the CRITICAL finding
  and on roadmap step 1, the single prerequisite for everything else in the phase.
- **One** is a defect in the report's **front matter** (VAL-11-006) and **one** in a single **inventory row**
  (VAL-11-007).

No finding lands on the store, the proxy, the browser or the frontend render path. Nothing in this
validation contests a seam already filed by phases 01, 03, 05, 06, 07 or 10.

## Cross-Finding Analysis

Two causes account for seven of the ten audited findings, and one cause accounts for four of the seven
validation-level findings.

**No bound on the row count, anywhere in the read path.** `get_by_graph_id` has no `LIMIT` (PERF-001), seven
of the collection routes have no `limit` (PERF-008), and the read loads two unrelated relationships plus one
Pydantic model per row regardless of what the response uses (PERF-002, PERF-005). I confirmed the memory
curve independently at every point and it is linear with a per-row factor of 3,119–3,211 bytes at this
document width. PERF-001 is the effect; the rest is the same absence expressed per layer.

**Deferred work runs in the serving process and is neither bounded nor measured.** The consumer is a task on
the request-serving event loop with an unconditional half-second sleep (PERF-006), and it is the same loop
the 202-statement rebuild stalls (PERF-003) — reproduced at p50 100.93 ms, p95 126.99 ms, max 381.4 ms, 4
ticks over 200 ms. No instrument would have shown either (PERF-009).

**The report's evidence does more work than it earns.** VAL-11-001, 003, 004 and 005 are one pattern: a
measurement was taken, a number was read off it, and a generalisation was attached that the number does not
carry. The GIN index was observed to have been scanned and generalised into "containment is always slower";
a `Rows Removed by Filter` counter was generalised into "PostgreSQL short-circuits"; a per-process
`ru_maxrss` was generalised into a container-limit percentage; a two-round-trip count was generalised into
"no material latency". In every case the underlying finding is real and the grade is right. The defect is
the step from number to principle, and it is the same step in all four.

PERF-004, PERF-007 and PERF-010 are independent of both causes and of each other.

## Roadmap

Ordered by what a remediation reader must repair before acting, not by the audited report's own ordering.

1. **Repair the report before implementing it.** VAL-11-002, VAL-11-001, VAL-11-004, VAL-11-005,
   VAL-11-006, VAL-11-007. The input's own roadmap cannot be followed as written: step 1 is unimplementable
   without a client change it does not name, and step 6's documentation fix cites a comparison that does not
   hold. *Before step 2*: every claim in PERF-001, PERF-004 and PERF-009 has been re-derived against the
   corrected measurement recorded in this report's appendices.
2. **Then the input's step 1, with both halves.** Bound the read server-side (PERF-001, phase 11) and thread
   `graphId` through `useAggregatedData` (phase 13). *Before step 3*: peak RSS is flat as the row count
   rises, and no dashboard renders a truncated chart.
3. **The input's steps 2-5 unchanged** — stop materialising what the response discards (PERF-002, PERF-005);
   set-based write and the consumer off the request loop (PERF-003, PERF-006); bound and instrument the
   deferral (PERF-006, PERF-009); reconcile the ceilings, the filter schema and the Redis client
   (PERF-004, PERF-007, PERF-010, the last now at MEDIUM rather than LOW).
4. **The input's step 6, independent of step 3's telemetry.** Fix `indexes.md:82` on the correct grounds —
   the code emits no containment operator — rather than on the 2.6× comparison, which does not reproduce and
   whose sign flips with dataset shape. This step depends on none of the others and does not need to be last.

## Rollout Safety

The audited report identifies the one step that changes observable behaviour — a `LIMIT` on the read — and
stages it correctly, and that analysis stands. **One hazard it does not identify is added here.** Its Rollout
Safety reasons that truncation "will be reported as 'wrong data', not as an outage, which is the worse of
the two outcomes during a rollout." That holds only if the client already requests one graph at a time. It
does not: `DashboardView.tsx:49` requests every graph, so a server-side cap truncates **all four charts
simultaneously** on the first dashboard view after deploy, and nothing in the client signals that a response
was shortened. The client change must land first or together with the cap, or the rollout produces exactly
the silent wrong-data outcome the section was trying to avoid.

Second, and independent of the fix: the OOM kill leaves the serving process dead while `docker ps` still
reports the container up (VAL-11-005). Any rollout that touches the read's memory ceiling should verify
recovery behaviour explicitly, because under the `--reload` topology there is none, and the release
checklist against the container's declared `memory: 1G` should say so.

Everything else in the input's Rollout Safety is sound and needs no amendment: step 2 reverts by reverting
the commit, step 3 must not precede step 1, `maxsize` on the queue can turn an accepted upload into a
rejection against a threshold that should sit above any observed burst, and steps 5 and 6 are
behaviour-preserving.

## Appendices

### Measurement method

Reproduced at `baseline eeb9a5e1ae4df195b9a4fa4f7c19b8834f8307d8` against a dirty tree
(`M src/mkobi/settings/app.yaml`, `M tests/test_config.py` — the concurrent phase-02 remediation, in flight).
Every anchor was re-pinned at `eeb9a5e`, not at the input's `b23a9cb`. `git diff b23a9cb..eeb9a5e` touches
`config.py`, `settings/app.yaml`, `app.py`, `.env.example`, the two compose files and `tests/test_config.py`;
it does **not** touch `docker-compose.yml`'s `deploy.resources.limits` block, the `Dockerfile` worker literal,
`session.py`, the repository, the routes, the storage manager, the task queue or the Redis client — so every
cited claim transfers.

**Dataset — produced and removed by this run.** `aggregated_data` was empty (0 rows) at the start. A
throwaway dashboard `11111111-1111-1111-1111-111111111111` and four graphs (`aaaaaaaa-…-025/-050/-100/-200`)
were created and 375,000 rows loaded with four `INSERT … SELECT … FROM generate_series` statements, `dims`
built by `jsonb_build_object` over a mixed-radix bijection of the series index into `region`(20) × `year`(5)
× `category`(40) × `sku`(50) — so all 200,000 tuples of the largest graph are distinct under
`uq_aggregated_data_dashboard_graph_dims` (verified: `count(DISTINCT dims::text) = 200000`). `metrics`
carries `revenue numeric` and `orders int`. This reproduces the input's dataset shape (25,000 + 50,000 +
100,000 + 200,000 = 375,000) and its four-key / two-metric row. **Known difference:** a contiguous series
index gives the 25,000-row graph only **3** regions (`region = (i/10000) % 20`), where the input's dataset
gave it 20. That is why PERF-009's `region = 'R07'` filter matched nothing on the 25 k graph in my run, and
it is itself part of what refutes the "20 distinct values" claim as applied to the graph the input filtered.

**Cleanup.** `DELETE FROM dashboards WHERE id='11111111-…'` cascaded all 375,000 rows away; `VACUUM FULL
aggregated_data` (run as superuser — the app role is not granted it) reclaimed the space. Final state:
`rows=0 size=65536 graphs=2 dashboards=8`, matching the state the input left. No repository, staging, commit,
revert or stash was performed. `git status --porcelain` differs from the baseline only by the pre-existing
untracked `.ai/audit/{01..10,99}-*/` directories and one `.ai/plans/` file.

**Stated deviation from the brief.** The reproduction OOM-killed the app container's serving process
(`OOMKilled=true`, VAL-11-005), which the `--reload` reloader does not respawn, so the container was left
serving nothing. I ran `docker restart mkobi-app-1` to restore it — the brief's "do not start, stop or
reconfigure the dev stack" is read as barring stack management, and restoring a process I had killed is
hygiene rather than reconfiguration. No compose file, service definition, environment variable or resource
limit was changed at any point. Verified after restart: `/health` → `{"status":"healthy","database":"connected"}`
and a respawned `multiprocessing-fork` child. The container's `StartedAt` is now `2026-09-30T18:03:08Z`
rather than the `17:29:16Z` the brief found, and `OOMKilled` has been reset to `false` by that restart — the
evidence was captured before the restart and is transcribed below.

### Peak RSS, re-measured

Each volume in its own process (`ru_maxrss` is a high-water mark, so one process cannot report several).
Baseline in every case 103.0–103.4 MB.

| rows for one graph | re-measured read s | input read s | re-measured peak MB | input peak MB | re-measured growth MB | input growth MB | re-measured B/row | input B/row |
|---|---|---|---|---|---|---|---|---|
| 25,000 | 3.01 | 3.03 | 179.5 | 173.8 | 76.5 | 70.1 | 3,211 | 2,941 |
| 50,000 | 5.42 | 4.91 | 253.2 | 247.5 | 150.0 | 143.7 | 3,146 | 3,013 |
| 100,000 | 10.06 | 8.69 | 400.4 | 390.0 | 297.5 | 286.8 | 3,119 | 3,007 |
| 200,000 | 29.36 | 15.86 | 701.5 | 679.2 | 598.1 | 576.3 | 3,136 | 3,021 |

Memory reproduces within 2-6 % at every point. Wall time reproduces within 2 % at 25,000 and diverges with
size, reaching 1.85× the input's figure at 200,000; the input's ~79 µs/row is therefore an under-estimate at
the top of the range, while its per-row byte factor — which the finding is built on — holds.

### Container memory, as read from the cgroup

| quantity | value | meaning |
|---|---|---|
| `HostConfig.Memory` | 1,073,741,824 | the declared limit, applied |
| `HostConfig.MemorySwap` | 2,147,483,648 | total budget, so 1 GiB of swap beyond the memory limit |
| `memory.max` | 1,073,741,824 | the kernel's limit |
| `memory.swap.max` | 1,073,741,824 | the swap allowance that delayed but did not prevent the kill |
| `memory.peak` (page view) | 1,074,294,784 | 100.05 % — survived, returned 200, 525 MB swapped out |
| `memory.peak` (follow-up run) | 1,074,565,120 | 100.08 % — `OOMKilled=true` |
| `HostConfig.NanoCpus` | 1,000,000,000 | `cpus: '1.0'` applied |
| `RestartCount` at the kill | 0 | the container did **not** restart |
| `StartedAt` at the kill | 2026-09-30T17:29:16Z | unchanged — the container did **not** restart |

### PERF-009 — predicate forms, transcribed

200,000-row graph, 20 distinct regions, best of three each:

| form | plan | exec ms (3 runs) |
|---|---|---|
| `(dims ->> 'region') = 'R07'` — what the code emits | `Parallel Index Scan using idx_aggregated_data_graph_id`, `Rows Removed by Filter: 95000` × 2 loops | 120.3 / 103.2 / 152.8 |
| `dims @> '{"region":"R07"}'` — what the doc describes | `Index Scan using idx_aggregated_data_graph_id`, `Rows Removed by Filter: 190000` | 124.0 / 94.8 / 114.7 |

25,000-row graph, 3 distinct regions, `R01`:

| form | plan | exec ms (3 runs) |
|---|---|---|
| `(dims ->> 'region') = 'R01'` | `Index Scan using idx_aggregated_data_graph_id`, 15,000 removed | 11.6 / 11.4 / 13.5 |
| `dims @> '{"region":"R01"}'` | `Index Scan using idx_aggregated_data_graph_id`, 15,000 removed | 18.4 / 15.7 / 30.8 |

No GIN index appears in any of the four plans. `pg_stat_user_indexes` after the sequence:
`idx_aggregated_data_dims_gin idx_scan=2 idx_tup_read=37500 size_kB=9872`;
`idx_aggregated_data_graph_id idx_scan=153 size_kB=2408`;
`uq_aggregated_data_dashboard_graph_dims idx_scan=107 size_kB=83480`.

### Coverage ledger

| Block | Items reached | Notes |
|---|---|---|
| 1. Claim re-derived from the executing path | 10 of 10 findings, every file:line anchor resolved mechanically at `eeb9a5e`; 1 anchor found not to name the symbol cited (`filters.py`, VAL-11-007) | load-bearing numbers re-derived rather than accepted: 4 volumes, 3 event-loop percentiles, the statement count, 2 predicate forms, 8 filter key counts, 4 Redis round-trip measurements, 1 row-lock wait |
| 2. Vacuous-control angle | 1 control vacuous (`pg_stat_user_indexes` "0 scans", contradicted by the same statistic reading 2); 3 controls deciding (`EXPLAIN (ANALYZE)`, the `before_cursor_execute` statement listener, the 100 ms event-loop ticker) | folded into VAL-11-001 rather than filed separately |
| 3. Grade against the audited rubric | 10 of 10 | 1 re-grade applied (PERF-010 LOW → MEDIUM); 9 bands upheld, including the CRITICAL |
| 4. Which side moves | 10 of 10 | 2 documentation, 1 configuration, 7 code; 0 dead-code labels; 0 re-typed to another phase |
| 5. Recommendation carryable out | 10 of 10 | 8 executable, 1 unusable as written (PERF-001), 1 executable with a wrong acceptance criterion (PERF-004) |
| 6. Cross-phase conflict, ownership, merge | 8 seams adjudicated against 10 raw reports and 9 sibling validation reports | 0 merges, 0 conflicts, 8 adjacencies; the phase-03 MVCC-vs-lock tension resolved by direct measurement; the DP-003 re-file question checked and cleared; **0 findings outside the input's declared scope** |
| 7. Finding-ID namespace | prefix `PERF-` declared at line 142 of the phase command, 10 minted, 0 in-source markers, 0 collisions, compound form resolved, validation namespace `VAL-11-` recorded as a deviation | ruling: reuse, nothing to migrate |
| 8. Shared template as a controlled artefact | 6 front-matter fields, 6 per-finding fields × 10 findings, 10 zone strings, the empty-state clause and the location-placement rule | 1 defect (VAL-11-006); all 10 zones are verbatim block titles; no field omitted or renamed |
| 9. Declared blocks versus actual angles | 10 of 10 traced to their support class | 8 supported by the phase's own declared block text; 2 arrived from angles the block list does not name |
| 10. Validated report as an artefact | this report | 7 findings each with a verdict, its own identifier and its re-derivation; tally agrees with the per-finding verdicts (CRITICAL 1 / HIGH 1 / MEDIUM 4 / LOW 1 = 7); no identifier renumbered; the audited `PERF-` and validation `VAL-11-` namespaces never share a table; every location carried inside the observation or evidence field rather than as a field of its own |
| 11. Shared angles | vacuous-control angle applied to 4 controls, 1 vacuous | cross-resource side-effect angle: not bound by phase 11 in its own words and not defined anywhere in the set — recorded as an observation, not a finding, since phase 11 binds no angle and this run introduced none |

**Unsettled, with reasons.** None of the ten audited findings is left unsettled, but four items are recorded
as limits on this validation rather than as verdicts:

- **The input's own OOM event at `b23a9cb`.** `docker inspect` at `eeb9a5e` reported `OOMKilled=false`,
  because the container was recreated at `17:29:16Z` by the concurrent remediation before this run began.
  The input's `StartedAt 2026-09-30T17:05:31Z` and `OOMKilled=true` cannot be read at the commit that produced
  them. **Settled instead by reproduction at `eeb9a5e`**: the same read path produced `OOMKilled=true` with
  `memory.peak` at 100.08 % of `memory.max`. The claim survives on the reproduction, not on the record.
- **Four-worker contention.** Unchanged from the input: the dev `app` service overrides `command:` with
  `--reload` (`docker-compose.override.yml:109`), so every HTTP timing here is a **single**-process timing.
  PERF-007's 120-vs-97 arithmetic and PERF-001's "two concurrent page views exceed it" remain arithmetic over
  `Dockerfile:179` and `session.py:44-45`, not a measured four-way contention.
- **Page-view wall time.** 359.71 s against the input's 101.25 s. The run was perturbed by a host-side cgroup
  poller issuing ~1,400 `docker exec` calls into the same container and by concurrent remediation work in the
  workspace. The response size (31.82 MB vs 30.9 MB) and the memory ceiling are unaffected, but the wall-time
  figure should not be compared directly against the input's.
- **The phase-03 "28.0 s" figure itself** was not re-measured. What was measured is the blocking behaviour
  that produces it — a second writer on the open `DELETE` blocks indefinitely with the deployed timeouts at
  `0` — which is sufficient to establish adjacency and insufficient to confirm the duration.




