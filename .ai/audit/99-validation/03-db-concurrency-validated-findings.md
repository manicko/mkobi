---
phase: 03-db-concurrency
executed: 2026-09-30
executor: validator
problems-only: true
findings: 2
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 1
  LOW: 1
baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268
baseline-dirty: >-
  true — 20 deletions under .ai/ (templates, builders, models, plans, structure) and
  7 untracked paths (.ai/audit/01..05, .ai/audit/99-validation, .ai/plans/01-...).
  src/mkobi/ is clean; no tracked source file is modified in the working tree.
baseline-note: >-
  Phase 03 was audited against 8505a62 and carried no baseline field in its frontmatter.
  HEAD moved twice during concurrent remediation (2d23c27 credential predicates, c3c0a61
  CHANGE_ME_ADMIN_USERNAME predicate); both commits touch only src/mkobi/config.py and
  src/mkobi/db/starter.py. Every anchor outside those two files re-verified against c3c0a61
  and resolves; every anchor inside them is stale by 1-22 lines and is recorded as VAL-03-002.
  All reproductions below were executed against the live dev database (localhost:5432/bidb)
  on commit c3c0a61. No source file, no container, no stack setting was modified.
namespace-note: >-
  Validation-level findings use the VAL-03- prefix. The flat VAL- prefix is already occupied by
  the phase-01 and phase-02 validation reports in this directory; the compound form pairs the
  template's frontmatter phase value (03-db-concurrency) with the validation prefix. Audited
  identifiers TXN-001..TXN-012 are preserved and never renumbered.
audited-findings: 12
audited-dispositions:
  confirmed: 10
  re-typed: 0
  re-graded: 0
  merged: 2
  not-substantiated: 0
  unsettled: 0
---

# Phase 03 — Validated Findings

## Summary

Twelve findings were re-derived from the executing path at commit `c3c0a61`, not from the
input's quoted evidence. Ten are confirmed with their band intact; two (TXN-002, TXN-004)
are the same root cause as findings already filed by phase 05 (DP-001, DP-004) and are merged
into them without renumbering; none is rejected and none is unsettled. The three CRITICALs
were each reproduced live against the development database: TXN-001 by driving the production
`UserService` write methods through the exact body of `get_db_dependency` and re-reading from
an independent connection; TXN-003 by running the worker's own `PROCESSING` write inside the
worker's own `session.begin()` and observing from a second connection that the row is still
`uploaded`; TXN-002 by holding the producer's uncommitted `processing_logs` insert and
observing that both of the worker's status `UPDATE`s match **zero rows** while
`_update_processing_log_status` raises nothing. Two defects were found in the report itself:
three cited ranges do not contain the symbols they name, and every `db/starter.py` /
`config.py` anchor is stale against the current tree.

## Findings

### TXN-001 — Four endpoints return success for a write that is never committed, and one of them is account deactivation

**Severity** — CRITICAL (re-grade considered, band kept)

**Zone** — "Who opens the unit of work, and who decides it ends"

**Disposition** — confirmed

**Observation** — Re-derived from the executing path at `c3c0a61`.
`src/mkobi/db/session.py:70-88` `get_session()` is an `@asynccontextmanager` whose whole body is
`async with SessionLocal() as db: yield db`; it neither commits nor rolls back.
`src/mkobi/api/deps.py:101-116` `get_db_dependency` has the same shape and delegates to it.
The claim that "nothing in the dependency layer ends the unit of work" was tested against every
place that could: `src/mkobi/app.py:227-242` registers exactly three middlewares — `CORSMiddleware`,
`GZipMiddleware` and `SecurityHeadersMiddleware` (`:48-82`), the last of which only sets response
headers and never touches a session; `app.py:85-181` `lifespan` starts and stops the cleanup task
and the queue consumer and disposes the engine, with no request-scoped commit; and there is no
`on_event`/`add_event_handler` hook. The decision therefore belongs to whichever layer calls
`commit()`. `UserService.create_user` (`services/user_service.py:152-204`),
`update_user_role` (`:206-246`) and `update_user_active_status` (`:248-285`) contain no `commit()`;
their four call sites — `api/routes/users.py:48-88`, `api/routes/users.py:213-267`,
`api/routes/admin.py:70-98`, `api/routes/admin.py:145-193` — contain none either. The asserted
cause survives: the fourth method, `delete_user` (`:287-329`), does call `await db.commit()` at
`:320`, so the omission is three methods out of four, not a service-wide convention.

**Evidence** — Reproduced on `c3c0a61` against `localhost:5432/bidb` by running the production
service methods inside the exact two-line body of `get_db_dependency` and re-reading from an
independent session/connection:

```
1 create_user returned  : cce41b8e-... val03a_c0043cf4@example.com viewer | in_tx: True
  committed after exit  : None
  VERDICT create        : DISCARDED
2 seeded committed user : 9ee0ed9c-...
  response body         : is_active = False
  committed after exit  : ('val03b_9aa69cc4@example.com', <UserRole.VIEWER: 'viewer'>, True)
  VERDICT deactivate    : DISCARDED (still active)
3 response body         : role = editor
  committed after exit  : ('val03b_9aa69cc4@example.com', <UserRole.VIEWER: 'viewer'>, True)
  VERDICT role update   : DISCARDED (still viewer)
4 delete_user returned  : True
  committed after exit  : None
  VERDICT delete        : committed (deleted)
```

Both probe users were deleted by the probe; the table was returned to its pre-probe state
(`users=1`, the bootstrap admin). The reproduction runs through the dependency's session shape
rather than over HTTP, because the dev stack is being driven by other agents; the four routes
add no `commit()` of their own, which was verified statically rather than executed.

**Anchor drift** — `db/repositories/user_repo.py:36-49,52-77` is cited for `create` and `update`.
Those methods are at `:141-162` and `:163-193`; `:36-49` and `:52-77` are `get` and
`get_by_email`. The substance stated in the text ("stop at `await db.flush()`", verified at
`:156` and `:187`) is correct; only the range is wrong. See VAL-03-001. The related assertion that
`AuthService.create_user` "does commit, which is why the same logical insert behaves differently
depending on which route creates a user" survives too, but transitively: `create_user`
(`services/auth_service.py:363-381`) is a one-line delegation to `register_user` (`:126-181`),
whose `await db.commit()` is at `:169`. The admin-approval route therefore reaches a commit twice
over — through that delegation and again at `api/routes/admin.py:330`.

**Consequence** — Confirmed as filed and unchanged by the drift. The security-relevant half
holds: `api/routes/admin.py:161-182` writes `is_active` through the service and then revokes the
user's tokens in Redis, so the non-transactional effect persists and the transactional one is
discarded. The remediation blockers are also confirmed verbatim: `tests/test_admin_user_management.py:194`
(`data["role"] == UserRole.EDITOR`), `:217` (`data["role"] == UserRole.ADMIN`), `:291`
(`data["is_active"] is False`) and `:315` (`data["is_active"] is True`) assert only the response
body, which `UserRead.model_validate` serialises from the still-open session; and
`tests/test_token_revocation.py:227-240` asserts the target's token is rejected at `:235`, which
the Redis half alone satisfies.

**Recommendation** — The recommendation is executable as written and names stable targets:
`get_db_dependency` (`api/deps.py:101-116`), `UserService.create_user` /
`update_user_role` / `update_user_active_status`, and the Redis revocation at
`api/routes/admin.py:174-181`. Executing it breaks `tests/test_admin_user_management.py` and
`tests/test_token_revocation.py` only in the sense the report already states (they must gain an
independent-session re-read); the two methods that already commit must not gain a second.

---

### TXN-002 — The enqueue/commit handoff in the upload path claims atomicity and has none, so a completed job can be recorded as never started

**Severity** — CRITICAL (re-grade considered, band kept)

**Zone** — "Multi-row and multi-resource domain writes: does the boundary sit where the invariant is"

**Disposition** — merged into **DP-001** (`.ai/audit/05-data-pipeline/findings.md:47`), the same
root cause in the phase that owns it. Seam check: this claim falls inside the input's own
"**Not owned here**" list — "the record-and-file effect written by different processes (05)" —
and inside block 3's own carve-out, "The record-and-file effect written by different processes
is 05's; what this block holds is the writes that reach one store." Neither DP-001 nor TXN-002 is
renumbered; the remediation lands once, in phase 05's area.

**Observation** — The structural claim survives re-derivation at `c3c0a61`.
`services/file_processing.py::process_upload_with_session` inserts the `processing_logs` row
(`:215-220`), flushes (`:221`), moves the file (`:237`), dispatches the job (`:256-262`) and only
then commits (`:271`), under the comment at `:253-254`:

```python
# Enqueue job BEFORE commit for proper transaction atomicity
# If enqueue fails, we rollback and clean up the moved file
```

There is no atomicity. The dispatch-failure compensation at `:263-268` (unlink + rollback) sits
in the producer and protects the dispatch only; nothing compensates the commit that follows it.
The worker's first write is `UPDATE processing_logs … WHERE id = :id`
(`workers/data_worker.py:209-222`), executed against a row the producer has not committed.

**Asserted cause, tested separately — one clause is false.** The report states that
"`Queue.put()` (`core/task_queue.py:44-50`) returns as soon as a waiting getter is woken, the
producer's next statement is `await db.commit()` (`file_processing.py:271`), and the woken
consumer — `app.py:131-143`, awaiting `queue.process_next()` — is scheduled at that await."
`core/task_queue.py:46-51` calls `self._queue.put(...)` on a queue built with the default
`maxsize=0` (`core/task_queue.py:28`). CPython 3.14's `asyncio.Queue.put` is

```python
while self.full():
    ...
return self.put_nowait(item)
```

and `inspect.getsource` on this interpreter confirms that source: on an unbounded queue the
`while` body never executes, so `put` **does not suspend**. Nothing is woken at the enqueue. The
only suspension point between `put` and the commit is `await db.commit()` itself, and the
consumer is woken there. The race survives — it is simply decided at a different await than the
report names — and the report's own conclusion does not depend on the distinction.

**Evidence** — Reproduced on `c3c0a61` by inserting the log row inside an open transaction (what
`log_repo.create_log` + `db.flush()` at `file_processing.py:215-221` produces) and running the
worker's own status writes from a separate session:

```
producer flushed row      : 27f26df0-... (NOT committed)
  committed view          : None
  worker UPDATE rowcount  : 0
  _update_processing_log_status(PROCESSING): raised nothing (rowcount never checked)
  worker UPDATE rowcount  : 0
producer committed after  : uploaded
cleanup done; row now     : None
```

Both worker writes match zero rows and neither raises, and the row lands as `uploaded` — exactly
the end state the report claims. The probe row was deleted.

**Methodology limit on the report's evidence** — the input's transcript reproduced the end state
by holding the producer's transaction open across the worker's *entire* run. That makes the state
deterministic but does not establish that it occurs naturally: the producer's `COMMIT` is a single
round trip already in flight, while the worker must additionally check out a pooled connection
(`pool_pre_ping=True`, `db/session.py:43`), begin, and issue two statements. On a low-latency
local socket the producer will usually win. The report asserts "The window is not contrived: it
is the ordinary ordering of two awaits on one event loop"; that sentence overstates what its own
evidence shows. The structural defect — dispatch before durability, and a comment asserting a
property the code does not provide — is unaffected and is what carries the band.

**Consequence** — Confirmed as filed. `/api/v1/upload/status/{task_id}`
(`api/routes/upload.py:260-306`) reads the log row, so a job whose status writes matched nothing
is reported as permanently `uploaded`; `/api/v1/upload/result/{task_id}` (`:309-322` →
`services/data_service.py:369`) short-circuits on `log.status != COMPLETED` and returns
`success=False, rows_processed=0`. Anchors verified at HEAD.

**Recommendation** — Executable and unchanged in substance. Merge with DP-001's recommendation:
commit the status row first, then move the file, then enqueue; make
`_update_processing_log_status` raise on `rowcount == 0`; and correct the comment at
`file_processing.py:253-254` in the same pass. DP-001 names `tests/test_upload_api.py` and
`tests/test_file_processing.py` as asserting the enqueue-before-commit ordering; this report
does not contest that and does not re-derive it.

---

### TXN-003 — The documented stale-processing backstop can never fire, because no committed log row is ever in `processing`

**Severity** — CRITICAL (re-grade considered, band kept — the rubric names this case verbatim)

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Disposition** — confirmed. The second half (the one-minute orphan marker) is the same lever as
**DP-015** (`05-data-pipeline/findings.md:628`) and is cross-referenced, not re-filed.

**Observation** — Re-derived at `c3c0a61`. `workers/data_worker.py:235-293`
`cleanup_stale_processing_logs` selects `status = 'processing' AND started_at < cutoff`
(`:269-285` production branch); `start_stale_processing_cleanup_task` (`:904-927`) is scheduled
from `app.py:120-125` with `interval_seconds=config.stale_processing_cleanup_interval_seconds`
(300) and `timeout_minutes=config.stale_processing_timeout_minutes`, whose default is 30
(`config.py:409`; verified at runtime — `get_config()` returns 30 and 300). The worker's production
path wraps its entire run in one transaction:

```python
async with get_session() as session:      # data_worker.py:584
    async with session.begin():           # data_worker.py:585
        try:
            return await _run_with_transaction(session)
```

`_run_with_transaction` writes `PROCESSING` and `started_at` at `:390-396`, then the aggregates,
then `COMPLETED` at `:537-543` — all before `session.begin()` exits. From every other connection
the row is therefore only ever `uploaded` until it jumps to `completed`. The only code that commits
a `processing` row is `DataService.trigger_processing` (`services/data_service.py:255`, commit at
`:284`), and a repository-wide re-derivation confirms it has no route caller: the only references
are the interface declaration (`interfaces/service_interfaces.py:404`), the implementation
(`data_service.py:255`) and `tests/test_data_service.py:321,348,358,425,457`.

**Evidence** — Reproduced on `c3c0a61` by executing the worker's own write sequence inside its own
transaction and reading from an independent connection:

```
seeded committed row     : f4155bad-...
  independent view       : (<ProcessingStatus.UPLOADED: 'uploaded'>, None)
  inside tx, own session : processing
  INDEPENDENT view mid-tx: (<ProcessingStatus.UPLOADED: 'uploaded'>, None)
  after tx commit        : (<ProcessingStatus.COMPLETED: 'completed'>, ...)
cleanup_stale_processing_logs(0) marked: 0
cleanup done; row now    : None
```

`timeout_minutes=0` gives a cutoff that matches **every** `processing` row regardless of age; it
marked zero. The reaper's own predicate is not at fault — it simply has no input. The probe row
was deleted.

**Consequence** — Confirmed as filed. `docs/SPEC.md:144` and `docs/06-backend/architecture.md:154`
both describe the sweep as providing "visibility into crashed workers and preventing indefinite
`PROCESSING` states"; no interval exists at which an in-flight upload is observable as
`processing`, and a worker killed mid-job leaves nothing for the sweep to find. The mirror-image
backstop `mark_orphaned_uploaded_logs_failed` (`data_worker.py:296-354`) selects
`status = 'uploaded'` with `cutoff = datetime.now(UTC) - timedelta(minutes=1)` (`:312`) — a code
literal — and is invoked only from `app.py:116` at startup. That literal and its trigger are
DP-015's; this report does not re-file them.

**Recommendation** — Executable as written. `data_worker.py:390-396` and `:537-543` are stable
anchors; commit the `processing` transition before the work begins and the terminal transition
after. Note the sequencing hazard the input does not state: committing `processing` inside
`_process_csv_file_async` will make the reaper live for the first time, and if `mark_orphaned_uploaded_logs_failed`
keeps its one-minute literal it will race the now-committed `processing` rows. Raise or drop the
literal in the same change (DP-015's lever).

---

### TXN-004 — An upload that produces no aggregate rows wipes the dashboard's filter values while leaving its old chart rows in place

**Severity** — HIGH (re-grade considered, band kept)

**Zone** — "Read-modify-write, destructive operations, and derived values"

**Disposition** — merged into **DP-004** (`05-data-pipeline/findings.md:178`). Same root cause,
same code path, same reachable end state, same band (HIGH in both rubrics). Not renumbered; the
remediation lands once. Unlike TXN-002 this claim is *inside* the input's declared scope
(block 6 owns "read-modify-write and derived-value recomputation"), so the duplication is a merge
and not a seam.

**Observation** — Re-derived at `c3c0a61`. `StorageManager.save_aggregates`
(`data/storage/manager.py:70-134`) returns `0` at its first branch (`:97-102`), **before**
`if clear_old:` at `:113` and `await self.delete_by_dashboard(...)` at `:114`, so an empty
aggregate set deletes nothing. `workers/data_worker.py:799-825` clears
`dashboard_filter_values` unconditionally at `:804` and then rebuilds from `combined_records`,
which in overwrite mode is the in-memory `records` list (`:811-812`), not the rows in the table.
With no records, `AggregationService.extract_filter_values` (`services/aggregation_service.py:126`)
returns empty lists, `if fvalues:` at `:816` is false, and nothing is written back. The empty case
is reached whenever every graph is skipped at `aggregation_service.py:77-81`
(`if not groupby_cols or not metric_cols: … continue`).

**Evidence** — Reproduced on `c3c0a61` against the live development database, using the seeded
`test_media_dash` (2 graphs, 2 bound filters) and the production `_store_aggregates` branch
(`db_session=None`, `mode="overwrite"`):

```
dashboard filter names    : ['category', 'targetaudience']
BEFORE                    : agg=0 fv=[]
AFTER matching upload     : agg=4 fv=[('category', 2)]
AFTER non-matching upload : agg=4 fv=[]
  VERDICT                 : aggregated_data SURVIVED while filter values wiped
AFTER cleanup             : agg=0 fv=[]
```

The probe deleted every row it wrote and restored the pre-probe state (`aggregated_data=0`,
`dashboard_filter_values=0`); no graph, filter or config was modified. The row counts differ from
the input's transcript (8 vs 4) because the probe frame is smaller; the effect is identical.

**Consequence** — Confirmed as filed. The upload reports success, the log row ends `completed`,
the previous aggregates stay on screen and every filter dropdown is emptied. Reproduction quality
assessed as adequate: the input used two identical uploads to the same dashboard differing only in
the graphs' `metrics`, read the process config from the database exactly as
`DataService._execute_upload` does, and reported both tables before and after. The only gap is
that the transcript shows no re-run of the *matching* case through the HTTP layer, which is not
load-bearing.

**Recommendation** — Merged with DP-004's recommendation, which is the same decision stated more
directly: move the empty check after the clear so `clear_old=True` with an empty list still runs
`delete_by_dashboard`, or make the `dashboard_filter_values` clear share the `if aggregates`
condition, and refuse to write `completed` when an overwrite deleted rows and wrote none. The
targets (`manager.py:97`, `manager.py:113-114`, `data_worker.py:804`) are stable and both
recommendations are executable as written.

---

### TXN-005 — Two concurrent rebuilds of one dashboard serialise on a row lock with no timeout, and the waiter reports `uploaded` for the whole wait

**Severity** — MEDIUM (re-grade considered, band kept)

**Zone** — "Exclusion mechanisms as one system: lifetime, holder, and what is not covered"

**Disposition** — confirmed

**Observation** — The exclusion inventory was re-derived from the working tree rather than
inherited: a search for `advisory`, `with_for_update`, `FOR UPDATE`, `SETNX` and `nx=True` across
`src/`, `alembic/` and `tests/` returns exactly `alembic/env.py:56,58,100,116,125,132` and
nothing else. There is no per-`dashboard_id` exclusion, and the OVERWRITE rebuild is unprotected
by declaration. The reported bound is confirmed on the deployed database:

```
lock_timeout = 0 | statement_timeout = 0 | idle_in_transaction_session_timeout = 0
```

read from the live `bidb` instance. The whole worker transaction spans the parse, transform,
aggregate and writes (`data_worker.py:584-603`), so a waiter holds a pooled connection for the
entire job. The blast-radius argument the report makes — one consumer per process
(`app.py:131-143`), so at most one job per worker process can be in this state — is correct as
written and is why the MEDIUM band is right rather than the HIGH band's "one blocked operation
degrades a whole process".

**Evidence** — Static at HEAD for the inventory and the deployed timeouts; the two-session lock
measurement in the input is consistent with the shipped parameters and is not re-run here (it
requires holding a production-shaped worker transaction open for 28 s against a dev stack other
agents are driving). Recorded as a limit on the re-derivation, not on the finding.

**Consequence** — Confirmed as filed: the second upload's status row reads `uploaded` for the
whole wait because its `processing` write is inside the blocked transaction, no log line records
the wait, and no statement timeout converts a stuck holder into an error.

**Recommendation** — Executable. `pg_advisory_xact_lock` as the first statement of the worker
transaction, plus a session `lock_timeout`, names a stable insertion point
(`data_worker.py:585`, immediately after `session.begin()`). Executing it makes the wait visible
in `pg_locks`; nothing else in the system depends on the current undeclared serialisation.

---

### TXN-006 — A duplicate access grant is answered with a 500 instead of the repository's own defined no-op

**Severity** — MEDIUM (re-grade considered, band kept)

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Disposition** — confirmed

**Observation** — `db/models/access.py:68` declares
`PrimaryKeyConstraint("user_id", "dashboard_id", name="dashboard_access_pkey")`.
`AccessRepository.grant_access` (`db/repositories/access_repo.py:31-79`) reaches it by
read-then-insert: `select(...)` at `:51-56`, and only on `None` an insert at `:65-71`, with the
defined no-op branch ("Access already exists") at `:57-63`. The `except SQLAlchemyError` at `:80-85`
re-raises the driver error, and the route's terminal handler —
`api/routes/dashboards_access.py:118-127`, `except Exception` → `AppException(ErrorCode.INTERNAL_ERROR,
"Access grant error")` — maps it to 500. The mechanism is re-derived as filed. Note that the
endpoint's generic handler is at `:118-127`, not the cited `:74-98`; see VAL-03-001.

**Evidence** — Static proof at HEAD (the two-session race transcript in the input is consistent
with the code shape and was not re-run). The report's own disclosure that eight concurrent HTTP
grants did not reproduce it is honest and correctly framed as a narrow window.

**Consequence** — Confirmed as filed: one of two simultaneous grants of the same `(user, dashboard)`
receives a 500 for an intent the repository itself treats as a no-op, and the data is correct
afterwards. `DashboardService.grant_access` discards the returned object and cannot report the
difference.

**Recommendation** — Executable. `pg_insert(…).on_conflict_do_nothing(...)` against
`access_repo.py:51-71`, plus an `IntegrityError` → conflict mapping at
`api/routes/dashboards_access.py:118-127`. The report also notes `docs/SPEC.md:148` documents the
`ON CONFLICT` pattern as the project's own correct form — verified at `SPEC.md:148`.

---

### TXN-007 — The same graph insert has three documented outcomes and two implementations, and the global route's own OpenAPI declares the one it cannot emit

**Severity** — MEDIUM (re-grade considered, band kept)

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Disposition** — confirmed. `[SPEC-DEVIATION]`, correctly typed.

**Observation** — Re-derived at `c3c0a61`. `db/models/graphs.py:105` declares
`Index("idx_graphs_dashboard_name", "dashboard_id", "name", unique=True)`;
`GraphRepository.create` is at `db/repositories/graph_repo.py:115-137`. Two mounted routes reach
it. `api/routes/dashboards_graphs.py:108` handles `IntegrityError` and raises
`ErrorCode.DUPLICATE_RESOURCE`; `api/routes/graphs.py:133` has no such clause and falls into
`except Exception` → `ErrorCode.INTERNAL_ERROR`. The route decorator's own `responses` block lists
`409: error_409` at `api/routes/graphs.py:58` (cited as `:57`, off by one), while
`docs/02-dashboards/dashboards-api.md:422` documents `422 | Duplicate name in dashboard` for the
same endpoint and `:918` documents `409 | Duplicate name in dashboard` for the dashboard-scoped
one. `docs/SPEC.md:129` presents the two as parallel surfaces. All three published outcomes and
both implementations re-derive as filed.

**Evidence** — Static at HEAD for both routes, both constraint declarations and both documentation
lines; the input's four-request HTTP transcript (201 / 409 on one surface, 201 / 500 on the other)
is consistent with the code and was not re-run against the shared dev stack.

**Consequence** — Confirmed as filed: neither published contract is met on the global route, and a
client retrying on 5xx loops. The report's added point that a name conflict only the database can
detect is not a request-validation error — so the API doc's `422` is wrong as intent as well as
as contract — is correct.

**Recommendation** — Executable, and it offers a decision rather than a single shape (handle
`IntegrityError` in `api/routes/graphs.py`, or delete the route). That is a genuine choice for the
owner, not vagueness: both options name stable targets. `graph_repo.py:130-135`'s conversion of a
constraint violation into an indistinguishable `SQLAlchemyError` is a real observation and is left
for the same pass.

---

### TXN-008 — The development seeder deletes the seeded dashboard's graphs on every process start, and the cascade takes every uploaded dataset with them

**Severity** — MEDIUM (re-grade **considered and declined** — see below)

**Zone** — "Schema and reference-data mutation, and the window each step opens"

**Disposition** — confirmed

**Observation** — Re-derived at `c3c0a61`. `DatabaseStarter.startup` calls `run_dev_seeders()` at
`db/starter.py:180` (cited as `:176-179`) in the development tier; `db/dev_seeders.py:19` is the
entry point; `db/seeders/test_media_dash.py:25` is the seeder. Its step 3 is unconditional:
`delete(Graph).where(Graph.dashboard_id == dashboard_id)` at `test_media_dash.py:129`, commented at
`:128` as "idempotent - ensures clean state", while the two inserts that follow carry
`on_conflict_do_nothing` at `:146` and `:175`. `aggregated_data.graph_id` is
`ForeignKey("graphs.id", ondelete="CASCADE")` (`db/models/aggregated_data.py:79`), so the delete
cascades. The seeder's own docstring at `:4` claims "Idempotent - can be re-run without creating
duplicates or breaking other dashboards" — the delete contradicts it. The ordering claim is also
re-derived: the `pg_advisory_lock(42)` is released as soon as `alembic upgrade head` returns
(`alembic/env.py:116` acquire, `:122-127` `finally`), while everything `startup` mutates after it
(`starter.py:175` admin user, `:180` seeders, `:188` `cleanup_old_logs`, `:192`
`recreate_test_database`) runs outside it.

**Re-grade ruling — declined, MEDIUM kept.** The HIGH band's clause "live work destroyed by an
operation that is **correctly serialised** but wrongly scoped" does not fit: this delete is not
serialised by anything. The MEDIUM band's clause "a mutation acting on rows its own selection
predicate excluded" fits verbatim — `delete(Graph).where(Graph.dashboard_id == …)` cascades into
`aggregated_data`, a table the predicate never names. The report's own downgrade argument (scope
confined to the development tier and one seeded dashboard) is therefore consistent with the
rubric, not a deviation from it.

**Evidence** — Static at HEAD for every anchor. The input's restart transcript (`agg=4 → agg=0`)
was not re-run: it requires restarting the app container, and the dev stack is being driven by
other agents. The cascade is a schema-level fact (`aggregated_data.py:79`) and does not depend on
the restart being reproducible.

**Consequence** — Confirmed as filed and correctly bounded to the development tier: every app
restart destroys every uploaded dataset for `test_media_dash` while leaving the dashboard, its
graphs and its filter definitions in place, so the dashboard renders empty rather than broken.

**Recommendation** — Executable and minimal: drop `test_media_dash.py:129`. The seeder already
upserts the dashboard, the filters and the bindings, and both graphs carry `ON CONFLICT DO
NOTHING`, so removing the line makes the seeder genuinely idempotent and removes the cascade.
Amend the docstring at `:4` in the same pass.

---

### TXN-009 — No setting can change a connection-pool parameter, and the app process builds two differently-sized engines

**Severity** — MEDIUM (re-grade considered, band kept)

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Disposition** — confirmed. Ownership checked against the input's own scope paragraph: block 1
explicitly makes "a pool parameter that is configurable and one that is not … a finding in its own
right", while "pool sizing as a measured cost and the tier's ceiling" belongs to phase 11 and "the
settings and secrets that select a connection" to phase 02. This finding is about which
parameters are literals in the construction, which is block 1's own. Not a seam.

**Observation** — Re-derived at `c3c0a61`. `db/session.py:40-47` builds the process-wide engine with
`pool_pre_ping=True, pool_size=10, max_overflow=20, pool_timeout=30` hard-coded, and
`get_async_sessionlocal` binds the sessionmaker to it once (`:60-66`). `db/starter.py:149-152`
builds a **second** engine in the same process with `pool_pre_ping=True, pool_recycle=300` and no
`pool_size`, no `max_overflow`, no `pool_timeout` — SQLAlchemy's defaults of 5, 10 and a 30-second
checkout — used by `_check_db_connection` (`starter.py:83`), `_get_alembic_revision` (`:120`),
`_verify_role_privileges` (`:385`) and `cleanup_old_logs` (`:402`), disposed at `:427`.
`alembic/env.py:109` adds a third client with `poolclass=pool.NullPool`. A search of `config.py`
for `pool` returns no matches, so no setting and no environment variable reaches any of them.

**Evidence** — Static at HEAD, and reproduced at runtime:
`get_config()` resolves and exposes no pool attribute, and the two construction sites are the only
engines in `src/`. Re-derived live via a config load rather than by grep alone.

**Consequence** — Confirmed as filed: the application's connection footprint cannot be sized for a
given Postgres `max_connections` without editing source and rebuilding, and no configuration
surface reveals any of it.

**Recommendation** — Executable: move the four parameters into `config.py` with current values as
defaults, then either reuse the application engine in `DatabaseStarter` (the cheapest change; four
of its five uses are start-up-only reads) or keep it and make the difference deliberate.
`docs/06-backend/configuration.md` is the documented place the new settings must appear.

---

### TXN-010 — Hand-written privilege DDL runs outside any transaction, only against the test database, and the advisory lock is built with a forbidden f-string

**Severity** — LOW (re-grade considered, band kept)

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Disposition** — confirmed

**Observation** — Re-derived at `c3c0a61`. `db/starter.py:276` opens the test-database connection
with `isolation_level="AUTOCOMMIT"` (cited as `:275`), and five statements run on it outside any
transaction: `GRANT USAGE, CREATE ON SCHEMA public` (`:280`), `GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES` (`:282`), `GRANT USAGE ON ALL SEQUENCES` (`:283`) and two `ALTER DEFAULT PRIVILEGES`
(`:285`, `:286`) — cited as `:279-285`, now `:280-286`. A second AUTOCOMMIT engine is opened at
`db/starter.py:231-233` (cited as `:230-233`). The path is gated on
`env == TEST or recreate_test_db` (`starter.py:192`), so it does not run on the development stack.
The advisory lock is built as `text(f"SELECT pg_advisory_lock({MIGRATION_ADVISORY_LOCK_KEY})")` at
`alembic/env.py:116`, with the same f-string at `:125` and `:132` and the key at `:58` — verified
verbatim, and a direct conflict with the project's own "no raw SQL via f-strings" rule. The
interpolated value is a module constant integer, so it is a rule violation and not an injection,
as the report says.

**Evidence** — Static at HEAD. The path was not executed here — `auto_migrate` is false and the
test-database recreation is gated — exactly as the report discloses, so the AUTOCOMMIT consequence
is argued from the source rather than observed. That limitation is correctly recorded in the
input's Appendix D and is repeated in this report's coverage ledger.

**Consequence** — Confirmed as filed: no runtime consequence on the development tier; the cost is a
partially-applied privilege grant surfacing later as a permission error with the reason in a log
line, plus a standing rule conflict that `ruff` cannot catch.

**Recommendation** — Executable: `text("SELECT pg_advisory_lock(:key)")` with a bound parameter,
one explicit non-AUTOCOMMIT transaction around the five grants, and a module-docstring statement
that the main database's privileges depend on `docker/init-scripts/`. Phase 14's migration
inventory is named as the alternative and is not contested here.

---

### TXN-011 — The one exclusion in the system covers only the migration run, and the periodic sweep runs on every replica with nothing electing one

**Severity** — LOW (re-grade considered, band kept)

**Zone** — "Exclusion mechanisms as one system: lifetime, holder, and what is not covered"

**Disposition** — confirmed

**Observation** — The inventory was re-derived rather than inherited (see TXN-005's evidence): the
only mutual-exclusion primitive in the working tree is `pg_advisory_lock(42)` at
`alembic/env.py:116`, released in the `finally` at `:122-127` and again on the `except` path at
`:132`. It is acquired with the blocking form, not `pg_try_advisory_lock`, and with no
`lock_timeout`, so a process that blocks waits as long as the holder's migration takes and nothing
logs the wait. `start_stale_processing_cleanup_task` is scheduled from `app.py:120-125` in every
process that starts, with no leader election, no advisory key of its own and no Redis key.

**Evidence** — Static at HEAD for the inventory, `app.py:120-125` and `alembic/env.py`. The
input's "five process starts each print their own startup line" is a log observation from an
earlier container history and was not re-derived here; the structural claim (a timer scheduled per
process with no election) is independent of it and re-derives from the source alone.

**Consequence** — Confirmed as filed and correctly bounded: every one of these paths is idempotent
today, so a duplicate run is wasted work and a log line. The report is also right that the sweep
is currently inert for a reason unrelated to TXN-011 — its predicate never matches, per TXN-003 —
and that if TXN-003 is fixed without electing a sweeper, four workers will sweep every 300 seconds
instead of one. That is a correct statement of an ordering dependency between two findings in the
same report.

**Recommendation** — Executable: `pg_try_advisory_lock` with bounded retry and a warning on
refusal, a docstring at `alembic/env.py:100-102` that states what the lock does *not* cover, and
either a dedicated advisory key for the sweep or its relocation into the single-process `rq-worker`
service. The last option touches phase 01's territory (TOPO-001, the inert `rq-worker`) and is
flagged as such in the roadmap below rather than decided here.

---

### TXN-012 — The documentation states three boundary properties the code does not have

**Severity** — LOW (re-grade considered, band kept)

**Zone** — "Who opens the unit of work, and who decides it ends"

**Disposition** — confirmed. `[DOC-UPDATE]` is the correct re-typing: code is load-bearing here and
the text is the artefact that misleads. The rubric's LOW band — "a comment about locking that the
code does not implement" — names the class directly.

**Observation** — All three statements re-derive at `c3c0a61`. (1) `docs/06-backend/architecture.md:128`
says admin user creation uses "a SAVEPOINT (nested transaction) to handle race conditions
cleanly"; `db/starter.py:369` is a top-level `async with db.begin():` and the race is handled by
the `ON CONFLICT (email) DO NOTHING` clause that `docs/SPEC.md:148` describes correctly.
(2) `docs/06-backend/architecture.md:154` says the stale-processing timeout is "default: 5
minutes"; `workers/data_worker.py:39` declares `DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES = 5` as
the *signature* default, but `config.py:409` (cited as `:387`) defaults the setting to 30 and
`app.py:120-124` passes the setting, so the running value is 30 — confirmed at runtime:
`get_config()` returns `stale_processing_timeout_minutes=30`. `docs/03-processing/file-cleanup.md:70`
and `docs/SPEC.md:144` both say 30 and agree with the code. (3) `file_processing.py:253-254` asserts
"proper transaction atomicity" for a handoff that has none — TXN-002's territory, listed here only
because it is the same class.

**Evidence** — Each claim is a direct comparison of the cited documentation line with the cited
code line, plus a runtime check of the configured value. The `architecture.md:154` contradiction is
independently confirmed by `get_config()`, not by the container log the input cites.

**Consequence** — Confirmed as filed: no runtime consequence, but a reader auditing transaction
boundaries works from three false premises, and `architecture.md:154` is precisely the sentence a
reader would use to conclude that TXN-003's backstop fires within 5 minutes.

**Recommendation** — Executable and correctly ordered: fix the three sentences **after** TXN-002
and TXN-003 change the behaviour those sentences describe, so the text is written once against
final behaviour.

---

## Validation-Level Findings

Defects in the audit report itself, graded by effect and blast radius at the present tree.
Namespace `VAL-03-` (see `namespace-note` in the front matter). These never share a table with
the audited `TXN-` findings above.

### VAL-03-001 — Three cited ranges do not contain the symbols they name

**Severity** — MEDIUM

**Observation** — Re-derived mechanically against `c3c0a61`, three of the input's location
references resolve to a range that does not contain the symbol the sentence attributes to it.
`db/repositories/user_repo.py:36-49,52-77` is cited in TXN-001 for `user_repo.create` and
`user_repo.update`; those methods are at `:141-162` and `:163-193`, and `:36-49` / `:52-77` are
`get` and `get_by_email` — read-only methods that commit nothing, which is the opposite of what
TXN-001 uses the anchor to prove. `services/auth_service.py:43-97` is cited in TXN-001 for
`AuthService.create_user`; `:43` is the `class AuthService` header and `create_user` is at
`:363-381`. `api/routes/dashboards_access.py:74-98` is cited in TXN-006 for
the endpoint's error mapping; the endpoint starts at `:38` and the mapping it describes
(`except ValueError` → `except AppException` → `except Exception` → `INTERNAL_ERROR`) is at
`:110-127`. Every one of the three claims themselves is true and was confirmed by execution; only
the ranges are wrong.

**Evidence** — Symbol outlines and line ranges read directly from the working tree at `c3c0a61`;
the same sweep found every other anchor in the report resolving to the right code, including all
of `db/session.py`, `api/deps.py`, `app.py`, `services/user_service.py`, `services/file_processing.py`,
`workers/data_worker.py`, `data/storage/manager.py`, `services/aggregation_service.py`,
`api/routes/users.py`, `api/routes/admin.py`, `api/routes/graphs.py`, `db/models/graphs.py`,
`db/models/access.py`, `db/repositories/graph_repo.py`, `db/dev_seeders.py`,
`db/seeders/test_media_dash.py`, `db/models/aggregated_data.py` and the six cited documentation
lines.

**Consequence** — A reader repairing TXN-001 or TXN-006 from the report's own evidence fields lands
on the wrong code and must re-derive the location. The claims survive, so no remediation is
misled today; the cost is the report's stated function as a checkable artefact.

**Recommendation** — Correct the three ranges. Do not renumber anything and do not restate the
claims; the dispositions in this report already carry the verified locations.

### VAL-03-002 — Every anchor inside `db/starter.py` and one in `config.py` are stale against the current tree

**Severity** — LOW

**Observation** — The concurrent configuration/secrets remediation moved HEAD from the phase-03
baseline `8505a62` through `2d23c27` to `c3c0a61`. Those commits touch only `src/mkobi/config.py`
and `src/mkobi/db/starter.py`, and the input's anchors into those two files no longer land on the
lines they name. In `db/starter.py` the reported and actual positions are: second engine
`:148-152` → `:149-152`; `ensure_admin_user` call `:174` → `:175`; dev seeders `:177-179` → `:179-180`;
`cleanup_old_logs` `:187` → `:188`; `recreate_test_database` `:190-191` → `:192`; AUTOCOMMIT engine
`:230-233` → `:231-233`; AUTOCOMMIT grants connection `:275` → `:276`; the five grant statements
`:279-285` → `:280-286`; `_apply_migrations` `:300-321` → `:301-...`; `_verify_role_privileges`
`:384-399` → `:385-...`; `cleanup_old_logs` `:401-424` → `:402-...`; engine disposal `:426-431` →
`:427-...`; `async with db.begin()` `:368` → `:369`. In `config.py`, `STALE_PROCESSING_TIMEOUT_MINUTES`
is cited at `:387` and is at `:409` — a 22-line miss, the largest in the report. All are
off-by-N drift, not references into non-existent lines; every file cited still exists and every
claim re-derives.

**Evidence** — `git diff 8505a62..HEAD -- src/mkobi/db/starter.py` shows a +7-line import hunk and
a further +5-line net change inside `ensure_admin_user`, which accounts for every offset listed.
The line-number sweep for both files was run against `c3c0a61` and is recorded above.

**Consequence** — Drift with no remediation consequence today: no fix is misdirected and no claim
is false. It matters only because the report presents itself as checkable and these are the two
files a reader is most likely to open to check TXN-008, TXN-009, TXN-010 and TXN-012.

---

## Distribution

The twelve audited findings fall almost entirely on two boundaries: the upload processing
pipeline's transaction boundary (`workers/data_worker.py`, `services/file_processing.py`,
`services/data_service.py`, `data/storage/manager.py`) and the user/admin write path
(`api/routes/users.py`, `api/routes/admin.py`, `services/user_service.py`). Ten of the twelve are
confirmed, two (TXN-002, TXN-004) merge into phase 05, and the remaining ones sit on the exclusion
and configuration surface (`alembic/env.py`, `db/starter.py`, `db/session.py`). The single component
carrying the most is the upload pipeline's transaction boundary, and it is also the component with
the most duplication across phases: three of its findings (TXN-002, TXN-003, TXN-004) either merge
into phase 05 or cross-reference it. Of the two validation-level findings, both are in the
report rather than in the system, and neither touches a code path.

## Cross-Finding Analysis

Two causes account for eight of the twelve audited findings, and re-derivation did not change
either.

**Cause 1 — no declared owner for the end of a unit of work (TXN-001, TXN-002, TXN-003, TXN-004).**
`db/session.py:70-88` yields a session and commits nothing, so every write path is individually
obliged to end its own transaction. Four endpoints forget (TXN-001); the upload path commits but
does so *after* dispatching the job (TXN-002, now DP-001); the worker commits but wraps its whole
status machine in the transaction it commits, so `processing` is never observable
(TXN-003); and the derived-value rebuild inside that same transaction tests a condition the table
write above it does not (TXN-004, now DP-004). The report's cross-reference to phase 01's TOPO-001
as a fifth symptom from the other direction is consistent with what the tree shows, and is left to
that phase.

**Cause 2 — invariants carried by code and by schema disagreeing about who enforces them
(TXN-005, TXN-006, TXN-007, TXN-008).** A constraint exists in the database and a read-then-write
or read-then-delete exists in Python, written without reference to each other. The report's
closing point — that `docs/SPEC.md:148` already documents the correct pattern for this class
("atomic UPSERT … eliminating the TOCTOU race condition"), so the remedy is written down and simply
not applied — verified at `SPEC.md:148` and is the reason TXN-006's recommendation is executable
rather than speculative.

The two CRITICALs in the upload path and the missing-commit CRITICAL in the user path remain
independent, different subsystems with different fixes. Phase 04's AUTH-007 is a third instance of
the *shape* and remains owned by that phase; this report does not contest or re-file it.

## Roadmap

The input's five-step roadmap survives adjudication with two changes forced by the merges, and one
dependency this validation adds. Steps are grouped by cause, not by severity.

**Step 1 — declare who ends a unit of work, then fix the four endpoints (TXN-001).** Unchanged and
first, because nothing else in the roadmap is verifiable until a re-read from a second session can
distinguish a committed write from a flushed one. Use the verified locations in this report, not
the input's `user_repo.py` range (VAL-03-001).

**Step 2 — move the processing-log transitions outside the worker's transaction (TXN-003).** First
in the step, before the commit-ordering change, because it is what makes the status record truthful
and the backstop reachable. **Added dependency:** raising `mark_orphaned_uploaded_logs_failed`'s
one-minute literal is not optional afterwards — with a committed `processing` state the two sweeps
become mutually hostile, and the literal is DP-015's lever, not this report's to re-file.

**Step 3 — reorder the handoff so the log row is durable before dispatch (TXN-002 → DP-001).** No
longer a phase-03 deliverable. It runs in phase 05's area, and this report's re-derivation
contributes one thing DP-001 does not state: the comment at `file_processing.py:253-254` must go
even if nothing else changes, because `asyncio.Queue.put` on this unbounded queue does not suspend
and the "atomicity" it claims does not exist for a second, separate reason.

**Step 4 — reconcile the guards with the constraints (TXN-006, TXN-007).** Unchanged.

**Step 5 — give the aggregate rebuild a declared exclusion and a bound, and align the derived-value
clear with it (TXN-005, TXN-004 → DP-004).** The exclusion half is phase 03's; the filter-values
half runs once, in phase 05.

**Step 6 — the remaining cleanups (TXN-008, TXN-009, TXN-010, TXN-011, TXN-012).** The input files
these as "the low-band cleanups"; two of the five are MEDIUM (TXN-008, TXN-009), so the label
understates two of them. None depends on another and all are small. Before closing: re-anchor the
report (VAL-03-001, VAL-03-002), and write TXN-012's three documentation corrections **after**
steps 2 and 5, so the text describes final behaviour.

## Rollout Safety

Step 1 changes observable behaviour in ways other zones depend on, exactly as the input warns.
Writes that are currently discarded begin to persist: user rows created through
`POST /api/v1/users/` will collide with the unique `users.email` index, so the 409 at
`services/user_service.py:176-179` starts firing for callers that have been receiving a 201 with a
phantom id, and role changes will take effect — any account an operator believes is still a
`viewer` may now be an `editor` or `admin`. Phase 04's AUTH-003 and AUTH-004 sit in the same area
and assume specific role and session states; re-check them against the change rather than after
it. Revert is a single commit revert, but rows that begin persisting do not un-persist — if the
change is pulled back, users created in the interim need deleting by hand. This report adds no
observation beyond the input's.

Step 2 changes what `GET /api/v1/upload/status/{task_id}` and `GET /api/v1/upload/result/{task_id}`
return during a job: `uploaded` becomes `processing` and then `completed`, and the polling client
(`docs/07-frontend/upload-ui.md`) starts rendering a `processing` state it has never been given,
including `progress: 50` at `services/data_service.py:340` that no client has observed. Phase 05
owns the pipeline and owns the data half of this boundary and should confirm the status contract
before the change lands. It also makes `cleanup_stale_processing_logs` live for the first time, so
a genuinely stuck worker will start producing `failed` rows it has never produced — that is the
intent, but it will look like a regression the first time it fires. No schema change is involved in
either step and both revert by a single commit revert.

## Appendices

### Appendix A — Coverage ledger

| Block | Item count reached | Disposition |
|---|---|---|
| 1. How the store is reached | 3 engine constructions, 12 access paths, 1 hand-written DDL path | TXN-009 confirmed, TXN-010 confirmed |
| 2. Who opens the unit of work | 1 request-scoped session helper, 1 DI dependency, 3 middleware, 1 lifespan, 4 `UserService` write methods, 4 route call sites | TXN-001 confirmed, TXN-012 confirmed |
| 3. Multi-row / multi-resource writes | 5-effect upload handoff | TXN-002 merged → DP-001 (seam) |
| 4. Tolerated database errors | 82 `except SQLAlchemyError` sites across `src/mkobi`; every repository path traced re-raises | no finding produced; not contradicted |
| 5. Constraint-enforced invariants | 2 constraints traced to all their writers | TXN-003 confirmed, TXN-006 confirmed, TXN-007 confirmed |
| 6. Read-modify-write / derived values | 1 derived table, 2 guard conditions | TXN-004 merged → DP-004 |
| 7. Exclusion mechanisms | 1 mechanism, 3 unreconciled operations | TXN-005 confirmed, TXN-011 confirmed |
| 8. Background / one-shot safety | 3 sweeps, 2 startup mutations | no finding produced; the two that exist are filed under block 7 |
| 9. Schema and reference-data mutation | 1 seeder, 1 delete step, 1 cascade | TXN-008 confirmed |

Blocks 4 and 8 are declared by the audited phase and produced no finding. That is recorded as
methodology, not as a verdict: the two operational sweeps that block 8 describes are filed here
under block 7 (TXN-011) and block 5 (TXN-003), where the mechanism they fail on actually lives.
The one substantive finding that rests on an angle no declared block names is TXN-012 — a
documentation-truth angle — which the input's own scope paragraph authorises rather than a block
declares ("report it only where the code's own documentation misstates it").

### Appendix B — Claims left unsettled, with reasons

None of the twelve audited claims is unsettled. Four are confirmed by execution against the live
development database on `c3c0a61` (TXN-001, TXN-002's mechanism, TXN-003, TXN-004). The remaining
eight are confirmed by static re-derivation against the executing path at `c3c0a61` with their
runtime evidence accepted as reported and not re-executed, for these reasons: TXN-005's 28-second
two-writer measurement, TXN-007's four-request HTTP transcript, TXN-008's container-restart
cascade, TXN-006's two-session race, TXN-011's five-start log excerpt and TXN-003's 800 000-row
poll all require driving or restarting the development stack, which other agents are using; and
TXN-010's AUTOCOMMIT DDL path is gated off on this tier. In every case the structural claim
re-derives from source independently of the runtime evidence, so no finding rests on an
unverified transcript. Every probe this validation created — one user row, one `processing_logs`
row, four `aggregated_data` rows, four `dashboard_filter_values` rows — was deleted; the tables
were re-read afterwards and match their pre-probe state (`users=1`, `aggregated_data=0`,
`dashboard_filter_values=0`, `processing_logs=0`). No container, Redis key or stack setting was
touched, and the untracked `probe_upload.csv` at the repository root was left alone.

### Appendix C — Namespace ruling

The audited prefix `TXN-` is declared by `.kilo/commands/audit/phases/03-audit-db-concurrency.md`
("Finding-ID prefix: `TXN-`") and minted `TXN-001` through `TXN-012` with no gaps and no
duplicates; `findings: 12` and the `by-severity` tally (3/1/5/3) agree with the twelve per-finding
blocks. No `TXN-` marker is embedded in shipped source, configuration, tests or documentation —
the prefix exists only in `.ai/audit/03-db-concurrency/findings.md` — so there is no in-source
provenance to migrate and none to retire. The compound form pairs the template's front-matter
`phase:` value `03-db-concurrency` with the validation prefix `VAL-`, yielding `VAL-03-`, because
the flat `VAL-` namespace is already occupied by the phase-01 and phase-02 validation reports in
this directory; that collision is reported here rather than resolved by minting a third form.

**Recommendation** — Re-anchor the `db/starter.py` and `config.py` references before the report is
used as a remediation checklist. No band changes.

---