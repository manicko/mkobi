---
phase: 03-db-concurrency
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 12
by-severity:
  CRITICAL: 3
  HIGH: 1
  MEDIUM: 5
  LOW: 3
---

# Phase 03 — Findings

## Summary

The zone examined was the Postgres store as a shared, concurrent resource: every path that
reaches it, who ends its unit of work, where the transaction boundary sits relative to the
invariant it protects, which invariants are carried by constraints, and what exclusion
exists. The dev stack was up throughout (app `:8010`, Postgres 18 `:5432`, Redis, RQ), and
all nine blocks were reached at runtime — the write paths were driven over HTTP, and the
worker, lock, and recovery paths were driven by executing the production code against the
live database. The single most consequential thing found is that this system has **no
convention for ending a unit of work**: the request-scoped session is only ever yielded, so
every write path is obliged to commit, and four endpoints that forget are silently discarded
while returning success. The second is a pair of adjacent boundary failures in the upload
pipeline — a handoff whose comment claims atomicity it does not have, and a status machine
whose middle state is never committed, which makes the documented 30-minute crash backstop
structurally unreachable. Twelve findings: three CRITICAL, one HIGH, five MEDIUM, three LOW.

## Findings

### TXN-001 — Four endpoints return success for a write that is never committed, and one of them is account deactivation

**Severity** — CRITICAL

**Zone** — "Who opens the unit of work, and who decides it ends"

**Observation** — `src/mkobi/db/session.py:70-88` `get_session()` is an
`@asynccontextmanager` whose body is `async with SessionLocal() as db: yield db`. It never
commits and never rolls back. `AsyncSession.__aexit__` calls `close()`, which rolls back any
open transaction, so a request whose only writes were `flush()`ed loses them. The
request-scoped session is handed to routes by `src/mkobi/api/deps.py:101-116`
`get_db_dependency`, which has the same shape. Nothing in the dependency layer ends the
unit of work, so the decision belongs to whichever layer happens to call `commit()`.

Three `UserService` methods that write do not call it, and no route above them does either:

| Route | Layer that writes | Ends the unit of work? |
|---|---|---|
| `POST /api/v1/users/` — `api/routes/users.py:48-88` | `UserService.create_user`, `services/user_service.py:152-204` | no |
| `PUT /api/v1/users/{user_id}` — `api/routes/users.py:213-267` | `UserService.update_user_role`, `services/user_service.py:206-246` | no |
| `PATCH /api/v1/admin/users/{user_id}/role` — `api/routes/admin.py:70-98` | `UserService.update_user_role`, `services/user_service.py:206-246` | no |
| `PATCH /api/v1/admin/users/{user_id}/active` — `api/routes/admin.py:145-193` | `UserService.update_user_active_status`, `services/user_service.py:248-285` | no |

`user_repo.create` and `user_repo.update` (`db/repositories/user_repo.py:36-49,52-77`) stop at
`await db.flush()`. The fourth method on the same class, `UserService.delete_user`
(`services/user_service.py:317-320`), does call `await db.commit()` — so the omission is not
a service-wide convention, it is three methods out of four. `AuthService.create_user`
(`services/auth_service.py:43-97`, reached by `POST /auth/register` and the admin-approval
path) does commit, which is why the same logical insert behaves differently depending on
which route creates a user.

**Evidence** — Reproduced live over HTTP against the dev stack, as an authenticated admin:

```
=== 1. POST /api/v1/users/ (create) ===
  HTTP 201 returned id=33944f5a-060c-4c74-8995-551bf9128d2d email=probe_uow_a@example.com
  after: admin@example.com, probe_txn_2@example.com
=== 3. PATCH /api/v1/admin/users/{id}/role ===
  response body role = editor
  re-read from DB      = viewer
=== 4. PATCH /api/v1/admin/users/{id}/active (is_active=false) ===
  response body is_active = False
  re-read from DB          = True
  login as the 'deactivated' user: SUCCEEDED (200)
=== 5. PUT /api/v1/users/{id} (legacy role update) ===
  response body role = admin
  re-read from DB      = viewer
```

The deactivation path is the security-relevant half. `api/routes/admin.py:162-182` writes
`is_active` through the service, then revokes the user's tokens in Redis. The Redis effect
is not transactional and the Postgres one is discarded, so only half of the deactivation
survives. Redis confirms the asymmetry — the key exists for a user the database still
considers active:

```
$ docker exec mkobi-redis-1 redis-cli KEYS "user_tokens_revoked*"
user_tokens_revoked:4cac4366-5fb5-49d1-b532-1b95913a61d9
```

A re-read of `is_active` and a fresh `POST /auth/login` for the same account were taken from
separate requests, so the value shown is committed state, not the in-transaction value the
first response was serialised from.

**Consequence** — Today, on this deployment, `POST /api/v1/users/` returns HTTP 201 with a
fresh UUID for an account that does not exist; the caller has an identifier for a user it
can never fetch, and the 409 duplicate-email check at `services/user_service.py:176-179` will
not fire for it because nothing was written. Role changes are reported to the administrator
as applied and are absent on the next request, including a promotion to `admin`. Account
deactivation is the sharpest case: the response says `is_active: false`, the operator's
existing access and refresh credentials are revoked in Redis, but the account remains active
in the database, so `POST /auth/login` still issues a fresh access token for it. A
deactivation is therefore reported as done, invalidates the victim's current sessions, and
leaves them able to sign back in immediately.

**Recommendation** — Pick one owner for the end of the unit of work and make it the only
one. The smallest change is to commit in `get_db_dependency` on a clean exit and roll back
on an exception, which removes the obligation from every route at once; the larger and more
honest change, given that several services already commit, is to declare the route the owner
and audit the remaining service methods against it — do not leave both. Whichever is chosen,
`UserService.create_user`, `update_user_role` and `update_user_active_status` need an
explicit `commit()` today, and the two methods that already have one should not gain a
second. Whatever the shape, put the commit on the `is_active` write **before** the Redis
revocation so the two effects cannot diverge again.

**Remediation blockers** — `tests/test_admin_user_management.py:194,217,291,315` assert only
the response body (`assert data["role"] == UserRole.EDITOR`, `assert data["is_active"] is
False`). Because `UserRead` is serialised from the still-open session, these pass while the
database is unchanged; they encode the defect and must gain a re-read from a separate
session. `tests/test_token_revocation.py:227-240` asserts the target's token is rejected,
which the Redis half alone satisfies, so it would still pass with the database write removed
entirely. `POST /api/v1/users/` and `PUT /api/v1/users/{user_id}` have no test at all.

### TXN-002 — The enqueue/commit handoff in the upload path claims atomicity and has none, so a completed job can be recorded as never started

**Severity** — CRITICAL

**Zone** — "Multi-row and multi-resource domain writes: does the boundary sit where the invariant is"

**Observation** — `services/file_processing.py:214-281` `process_upload_with_session` inserts
the `processing_logs` row, moves the file to its final name, dispatches the job, and only
then commits. The dispatch sits between the insert and the commit, under this comment
(`file_processing.py:253-254`):

```python
# Enqueue job BEFORE commit for proper transaction atomicity
# If enqueue fails, we rollback and clean up the moved file
```

There is no atomicity. The queue is an in-process `asyncio.Queue`
(`core/task_queue.py:26-31,44-50`), and its single consumer runs in the same event loop
(`app.py:131-143`). `enqueue` returns as soon as `Queue.put()` releases the waiting
consumer, and the very next statement, `await db.commit()` at `file_processing.py:271`, is
an await point — so the consumer can start the worker before the producer's insert is
visible. The worker then opens its own session (`workers/data_worker.py:584-585`) and its
first write is `UPDATE processing_logs SET status='processing', started_at=now() WHERE id =
<task_id>` (`data_worker.py:390-396`). Against a row the producer has not committed, that
statement matches zero rows; so does the `completed` write at `data_worker.py:537-543`. The
aggregate rows the worker writes are keyed by `dashboard_id`, not by the log id, so nothing
about the ingested data is rolled back with the log.

**Evidence** — Reproduced with the production worker (`db_session=None`, the branch a
dispatched job takes) against the live database, holding the producer's transaction open
across the worker's whole run:

```
producer flushed processing_logs id=9ac3d022-... (NOT committed yet)
committed view of that row: <no row>
worker result: {'success': True, 'rows_processed': 3, 'message': 'Processing completed'}
aggregates written by the worker: 6 rows
producer committed afterwards; committed status of the row: uploaded
log row the operator sees: ('uploaded', 'handoff probe', None, None)
```

A job that ingested three rows and wrote six aggregate rows, all committed, is recorded as
`status='uploaded'` with `finished_at` and `error_code` both null. The window is not
contrived: it is the ordinary ordering of two awaits on one event loop. `Queue.put()`
(`core/task_queue.py:44-50`) returns as soon as a waiting getter is woken, the producer's next
statement is `await db.commit()` (`file_processing.py:271`), and the woken consumer —
`app.py:131-143`, awaiting `queue.process_next()` — is scheduled at that await. The probe
reproduces the resulting state deterministically by holding the producer's transaction open
across the worker's whole run; the `IllegalStateChangeError` that follows the transcript in the
raw probe output is the probe calling `close()` on a manually-entered session, not a product
behaviour.

**Consequence** — A successful upload is reported by `GET /api/v1/upload/status/{task_id}`
(`api/routes/upload.py:260-306`, which reads the log row) as permanently `uploaded`, never
`processing` and never `completed`, while the dashboard shows the new data. `GET
/api/v1/upload/result/{task_id}` (`api/routes/upload.py:309-322` →
`services/data_service.py:369`) short-circuits on `log.status != COMPLETED` and returns
`success=False, rows_processed=0`. The frontend polls
that status (`docs/07-frontend/upload-ui.md:113-116`), so the user is told the upload did not
complete for a dataset that is in fact loaded. Because the row is `uploaded` and not
`processing`, the only backstop that can touch it is the one-minute orphan marker, which
will later report the same successful job as `failed`.

**Recommendation** — Commit the log row before dispatching. The dispatch-failure
compensation is already in the right place, in the producer, and stays there:
`file_processing.py:263-268` unlinks the moved file and rolls back, and it should keep doing
so — but note it protects only the dispatch, never the commit that follows it, which is the
half that has no compensation. The `async with db.begin()` block the worker already opens
(`workers/data_worker.py:584-585`) is the right shape for the producer's commit too. Update
the comment at `file_processing.py:253-254` either way; it is the only place in the codebase
that asserts a property the code does not provide.

### TXN-003 — The documented stale-processing backstop can never fire, because no committed log row is ever in `processing`

**Severity** — CRITICAL

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Observation** — The project's crash-recovery mechanism for stuck uploads is a periodic
sweep. `workers/data_worker.py:235-293` (production branch `:269-285`)
`cleanup_stale_processing_logs` runs
`UPDATE processing_logs SET status='failed', message='Worker timeout - marked as failed by
cleanup job' WHERE status='processing' AND started_at < :cutoff`, scheduled every
`STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS` (300) with a
`STALE_PROCESSING_TIMEOUT_MINUTES` (30) budget. The state it selects on is never committed by
the code that produces it. The worker's production path
(`data_worker.py:584-603`) wraps its entire run in one transaction:

```python
async with get_session() as session:
    async with session.begin():
        try:
            return await _run_with_transaction(session)
```

and `_run_with_transaction` writes `status='processing'` and `started_at=now(UTC)` at
`data_worker.py:390-396`, then the aggregates, then `status='completed'` at
`data_worker.py:537-543` — all before `session.begin()` exits and commits. From every other
connection the row is therefore only ever `uploaded` (committed by the request at
`file_processing.py:271`) until it jumps straight to `completed`. The only code path that
commits a `processing` row is `DataService.trigger_processing`
(`services/data_service.py:279-284`), which has no route — grep finds callers only in
`interfaces/service_interfaces.py:404` and `tests/test_data_service.py`.

**Evidence** — Polled from an independent session on its own connection while a real
800 000-row job ran through the production worker, and then asked the reaper to run with
`timeout_minutes=0` — a cutoff that marks *every* `processing` row regardless of age:

```
observation window = 5.56s over 75 polls of an independent connection
statuses first seen (t, status, started_at):
    (0.0, 'uploaded', '2026-09-30 11:27:06.429524+00:00')
    (5.55, 'completed', '2026-09-30 11:27:06.466989+00:00')
DISTINCT COMMITTED STATUSES OBSERVED: ['completed', 'uploaded']
rows currently committed as status='processing' in the whole table: 0
cleanup_stale_processing_logs(timeout_minutes=0) marked: 0
```

`started_at` moved from `…06.429524` to `…06.466989`, which is the `PROCESSING` write landing
— but only together with `COMPLETED`, at the end. To confirm the reaper is not itself
broken, a row was planted in `processing` and the same function marked it on the first call.
Its logic is correct; nothing can hand it an input.

**Consequence** — `docs/SPEC.md:144` describes this sweep as "providing visibility into
crashed workers and preventing indefinite `PROCESSING` states", and
`docs/06-backend/architecture.md:154` repeats that it exists to detect logs "stuck in
`PROCESSING` state (e.g., due to worker crashes)". It provides no such visibility: there is
no interval at which an operator can observe an in-flight upload as `processing`, and a
worker killed mid-job leaves nothing for the sweep to find. The one recovery that does run
is the mirror image and mis-scoped — `mark_orphaned_uploaded_logs_failed`
(`data_worker.py:296-354`) selects on `status='uploaded'` with a **one-minute** cutoff, far
shorter than the 30-minute `processing` budget it was designed to sit behind:

```
== 2. what does the `uploaded` backstop do to a job that is merely slow? ==
  planted uploaded row <...> (2 min old, i.e. a job still well inside its 30-min budget)
  mark_orphaned_uploaded_logs_failed() marked=1; row now failed
```

So an upload that legitimately takes longer than a minute is declared `failed` by the next
application start — including a job that has already ingested its data — and the sweep
invariants that were meant to catch a crashed worker catch a slow one instead. (The three
different values this pair of backstops is described with — 5, 30, and 1 — are reconciled in
TXN-012.)

**Recommendation** — Commit the `processing` transition as its own transaction before the
work begins, and the `completed`/`failed` transition after, so the log row is a truthful
progress record rather than an outcome record. If the long parse and transform must stay
inside the same transaction as the writes, at minimum commit the transition first and rely on
the existing `except` path. Then raise the orphan marker's cutoff to the same budget as the
stale sweep, or drop it: with a committed `processing` state it is redundant, and without
one it is the wrong predicate. Correct `architecture.md:154`'s default to 30 minutes in the
same pass.

### TXN-004 — An upload that produces no aggregate rows wipes the dashboard's filter values while leaving its old chart rows in place

**Severity** — HIGH

**Zone** — "Read-modify-write, destructive operations, and derived values"

**Observation** — `dashboard_filter_values` is a derived value: it is cleared and rebuilt from
the aggregate records on every upload. `workers/data_worker.py:799-825` does the clear
unconditionally and the rebuild conditionally, and the two are not reading the same thing.
`StorageManager.save_aggregates` (`data/storage/manager.py:70-134`) returns `0` at
line 97 on an empty input list, before it reaches its `if clear_old:` branch at line 113, so
in `overwrite` mode the `delete_by_dashboard` call at line 114
(`manager.py:255`) does not run. `dashboard_filter_values` has no such guard: the clear
at `data_worker.py:804` runs regardless, and the rebuild then iterates
`combined_records` (`data_worker.py:809-812`), which in overwrite mode is the in-memory `records` list, not the rows in
the table. When the aggregate set is empty, `records` is `[]`, `extract_filter_values([])`
(`services/aggregation_service.py:126`) returns empty lists, `if fvalues:` at `data_worker.py:816` is
false, and nothing is written back.

The empty case is reached whenever no graph on the dashboard has both a matching dimension
and a matching metric column in the uploaded file. `AggregationService.aggregate_for_dashboard`
(`services/aggregation_service.py:44,77-81`) skips a graph when
`not groupby_cols or not metric_cols`, and appends nothing to `records`.

**Evidence** — Two identical uploads of the same CSV to the same dashboard, differing only
in the graphs' `metrics`, with the process config read from the database exactly as
`DataService._execute_upload` does:

```
=== graphs.metrics = ["tvr"] (matches the upload) ===
  aggregated_data rows=8  filter_values=[('brand',6),('category',4),('targetaudience',4)]
=== graphs.metrics = ["ghost"] (no graph matches the upload) ===
  BEFORE  aggregated_data rows=8  filter_values=[('brand',6),('category',4),('targetaudience',4)]
  worker result: {'success': True, 'rows_processed': 4, 'message': 'Processing completed'}
  AFTER   aggregated_data rows=8  filter_values=NONE
```

The job reports `success: True` and the log row ends `completed`. Every filter dropdown on
the dashboard is now empty while its charts still render the eight rows from the previous
upload.

**Consequence** — On any dashboard whose graph configuration does not fully match the
columns of the file being uploaded — the common case after a schema change on either side —
the upload completes successfully, the old aggregates stay on screen as if nothing changed,
and the entire filter value set is deleted. Nothing in the response, the status endpoint, or
the log message distinguishes this from a clean rebuild, and the missing values are restored
only by a subsequent upload that does produce aggregates. A `metrics`/`dimensions` typo on one
graph is enough to trigger it.

**Recommendation** — Decide what an empty aggregate set means before touching either table.
If it means "this upload matched nothing", the clear and the delete must share that condition:
guard `dashboard_filter_values` on `if aggregates` the same way `save_aggregates` guards its
own delete, and return early from `_store_aggregates` so the log reports zero rows rather
than a success over a half-rebuilt dashboard. If it means "this dashboard now has no data",
then the `DELETE` must run even for an empty input list and the finding is that
`save_aggregates`' early return is the defect. Either way the two conditions must be the
same condition, and the `rows_processed` in the completion message should reflect which
branch was taken.

### TXN-005 — Two concurrent rebuilds of one dashboard serialise on a row lock with no timeout, and the waiter reports `uploaded` for the whole wait

**Severity** — MEDIUM

**Zone** — "Exclusion mechanisms as one system: lifetime, holder, and what is not covered"

**Observation** — There is exactly one declared mutual-exclusion mechanism in `src/`.
`alembic/env.py:113-127` takes a session-level `pg_advisory_lock(42)`, held for the duration
of one `alembic upgrade head` and released in a `finally`; it covers only migration work (see
TXN-011). There is no other: grep for `advisory`, `with_for_update`, `FOR UPDATE`,
`SELECT … FOR UPDATE` and Redis lock primitives across `src/`, `alembic/` and `tests/`
returns only `alembic/env.py:58,116,125,132`. Nothing keys on `dashboard_id`. The OVERWRITE
rebuild at `manager.py:113-134` is therefore unprotected by declaration, and in practice
serialises only by the implicit row locks its own `delete_by_dashboard` call takes.

The bound on that wait is the server's, and on the deployed database every timeout is
disabled: `lock_timeout = 0`, `statement_timeout = 0`, `idle_in_transaction_session_timeout = 0`.
The waiting job holds a pooled connection for as long as the holder's transaction is open,
and the whole worker transaction spans the CSV parse, the Polars transform, the aggregate and
the writes (`data_worker.py:584-603`), so the hold is the entire job, not just the delete.

**Evidence** — Two sessions, each running the exact statement sequence
`StorageManager.delete_by_dashboard` performs, with writer B sampled from the `db` container
while it waited:

```
    t+  0.0s  writerA deleted 4 rows, holding tx open
    t+  2.0s  writerB issuing the same DELETE ...
    t+  5.0s  writer B finished? False
      pid=9013 state='idle in transaction' wait_event_type=None wait_event=None
           query='DELETE FROM aggregated_data WHERE dashboard_id = %(dashboard_id_1)s'
      pid=9022 state='active' wait_event_type=Lock wait_event=transactionid
           query='DELETE FROM aggregated_data WHERE dashboard_id = %(dashboard_id_1)s'
      locktype=transactionid mode=ShareLock granted=f
show lock_timeout; show statement_timeout; show idle_in_transaction_session_timeout;
 lock_timeout | statement_timeout | idle_in_transaction_session_timeout
-------------+-------------------+----------------------------------
 0           | 0                 | 0
...
    t+ 32.0s  writerB DELETE returned after 28.0s (deleted 0)
```

B blocked for 28.0 s — until A committed — and then deleted 0 rows because A had already
removed them.

**Consequence** — The dashboard's data survives; the second writer does not corrupt the
first. But for the whole wait the second upload's `processing_logs` row reads `uploaded` (its
`processing` write is in the blocked transaction), so `GET /api/v1/upload/status/{task_id}`
reports a permanently queued job and the frontend spinner never resolves; a pooled
connection is held for the duration; and nothing in the log says a wait is happening —
`pg_stat_activity` is the only place the wait is visible. Today the blast radius is bounded:
one app process runs one queue consumer (`app.py:131-143`), so at most one job per worker
process is ever in this state, four in a `--workers 4` production deployment
(`docker/Dockerfile` CMD). It becomes a process-wide problem the moment the consumer count
or the per-dashboard job rate rises above one, and the absent bound is what makes it
unrecoverable rather than merely slow: there is no statement timeout to convert a stuck
holder into an error, and no log line to tell an operator which dashboard is stuck.

**Recommendation** — Declare the exclusion rather than inheriting the `DELETE`'s row locks.
A `pg_advisory_xact_lock(hashtext('overwrite:' || dashboard_id))` taken as the first
statement of the worker's transaction is two lines, is released automatically on commit,
crash or rollback, and makes the wait visible in `pg_locks` under a name that identifies the
dashboard. Pair it with a `lock_timeout` on the session so a genuinely stuck holder produces
an error and a `failed` log row rather than a silent wait. Ordering the lock before the
`DELETE` also makes the serialisation cover the read the rebuild depends on, which the
`DELETE`'s row locks do not.

### TXN-006 — A duplicate access grant is answered with a 500 instead of the repository's own defined no-op

**Severity** — MEDIUM

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Observation** — `dashboard_access` carries its invariant in the schema:
`PrimaryKeyConstraint("user_id", "dashboard_id", name="dashboard_access_pkey")` in
`db/models/access.py:67-75`, confirmed live as
`PRIMARY KEY (user_id, dashboard_id)`. `AccessRepository.grant_access`
(`db/repositories/access_repo.py:31-79`) reaches it by read-then-insert: a
`select(...).scalar_one_or_none()` at lines 50-56, and only if that returns `None` an
`INSERT` at lines 65-71. There is no lock, and the read is not covered by anything. The
repository defines the correct recovery for the race at lines 57-63 — return the existing row,
a no-op — but that branch is only reachable if the read wins. When both writers read
`not exists`, the second `INSERT` blocks on the primary key index and then fails with
`UniqueViolationError`, which is an `IntegrityError`, which is a `SQLAlchemyError`, so it is
swallowed and re-raised as a bare `SQLAlchemyError` at `access_repo.py:80-85`. The route
`api/routes/dashboards_access.py:74-98` catches `ValueError` and `AppException` and maps
everything else to `ErrorCode.INTERNAL_ERROR`.

**Evidence** — Two sessions running the exact statement sequence `grant_access` performs,
with writer B released after writer A's `SELECT` so both read `not exists`:

```
  pre-condition: no dashboard_access row for (user, dashboard)
    writerA SELECT -> existing=False
    writerA INSERT flushed (uncommitted)
    writerB SELECT -> existing=False
    writerB IntegrityError: duplicate key value violates unique constraint "dashboard_access_pkey"
  writerA: INSERT committed
  writerB: IntegrityError -> UniqueViolationError
  rows now in dashboard_access for this dashboard: 1
```

Eight genuinely concurrent HTTP `POST /api/v1/dashboards/{id}/access` requests for the same
`(user, dashboard)` did not reproduce it — the round trips serialised — so the window is
narrow, but it is the ordinary read-then-insert window and the constraint is what closes it.

**Consequence** — One of two administrators clicking "grant access" for the same person at
the same time receives `500 INTERNAL_ERROR: Access grant error` for a request the repository
itself treats as a no-op (`access_repo.py:57-63` logs "Access already exists" and returns the
row). The data is correct afterwards — exactly one row exists — so the failure is a spurious
500 on a successful intent, not a corrupted grant, and `DashboardService.grant_access`
(`services/dashboard_service.py:356-401`) cannot even report the difference: it discards the
returned object and declares `True if access granted` either way. A client that retries on
5xx will hammer a request whose precondition is already satisfied.

**Recommendation** — Make the write the thing that is conflict-tolerant, not the read.
`pg_insert(DashboardAccess).on_conflict_do_nothing(index_elements=["user_id","dashboard_id"]).returning(...)`
collapses the race to a single statement and needs no lock, and it matches the pattern the
project already documents as correct for `ensure_admin_user` (`docs/SPEC.md:148`,
"eliminating the TOCTOU race condition"). Keep the `select` only to decide whether to return
the existing object for the caller's convenience. Independently, `api/routes/dashboards_access.py:96-98`
should not map an `IntegrityError` to `INTERNAL_ERROR` even after the repository is fixed —
map it to the conflict code so a future constraint violation is reported as such.

### TXN-007 — The same graph insert has three documented outcomes and two implementations, and the global route's own OpenAPI declares the one it cannot emit

**Severity** — MEDIUM

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Observation** — `[SPEC-DEVIATION]` `graphs` carries
`Index("idx_graphs_dashboard_name", "dashboard_id", "name", unique=True)`
(`db/models/graphs.py:103-105`), confirmed live as `CREATE UNIQUE INDEX
idx_graphs_dashboard_name ON public.graphs USING btree (dashboard_id, name)`. Two mounted
routes reach the same repository method `GraphRepository.create`
(`db/repositories/graph_repo.py:115-137`), and the single constraint behind it has three
different published outcomes:

| Surface | Published outcome for a duplicate name | Actual |
|---|---|---|
| `POST /api/v1/dashboards/{id}/graphs` | `409` — `docs/02-dashboards/dashboards-api.md:914-918` | 409 ✓ |
| `POST /api/v1/graphs/` (route decorator) | `409` — `api/routes/graphs.py:57` | **500** ✗ |
| `POST /api/v1/graphs` (API doc) | `422` — `docs/02-dashboards/dashboards-api.md:417-423` | **500** ✗ |

`api/routes/dashboards_graphs.py:70-95` imports `IntegrityError` and handles it: rollback,
then `AppException(ErrorCode.DUPLICATE_RESOURCE, "Conflict: graph creation failed")` — 409.
`api/routes/graphs.py:113-139` calls the same method, has no `IntegrityError` clause, and
falls into `except Exception` at line 133 → `ErrorCode.INTERNAL_ERROR`, "Error creating
graph" — 500. That route's own `responses` block lists `409: error_409` at
`api/routes/graphs.py:57`, so the generated OpenAPI client for `POST /api/v1/graphs/` is told
to expect a status the handler cannot produce, while the hand-written API doc for the same
endpoint promises a third. `docs/SPEC.md:129` describes both surfaces as equivalent
alternatives ("in addition to the global `/api/v1/graphs` endpoints"), so nothing tells a
caller they differ.

**Evidence** — Both routes driven over HTTP as an administrator with admin access to the same
dashboard, each with the same body:

```
POST /api/v1/dashboards/{id}/graphs -> 201     (first)
POST /api/v1/dashboards/{id}/graphs -> 409 DUPLICATE_RESOURCE: Conflict: graph creation failed
POST /api/v1/graphs/               -> 201     (first)
POST /api/v1/graphs/               -> 500 INTERNAL_ERROR: Error creating graph
```

The application log for the second pair shows the repository's own
`"Error creating graph: ..."` line — the `IntegrityError` is caught and re-raised as a bare
`SQLAlchemyError` at `graph_repo.py:130-135`, indistinguishable from a real database fault
by the time the route sees it.

**Consequence** — A client that creates a graph through `POST /api/v1/graphs/` and retries on
duplicate names receives a 500 and, if it retries on 5xx, loops. Neither published contract is
met: the OpenAPI schema says 409, the API doc says 422, and the handler sends 500. The two
routes are documented in `docs/SPEC.md:129` and `docs/02-dashboards/dashboards-api.md` as
parallel surfaces for the same operation, so the difference is not something a caller can be
expected to know, and the API doc's `422` is additionally wrong as a matter of intent — a
name conflict that only the database can detect is not a request-validation error.

**Recommendation** — Handle `IntegrityError` in `api/routes/graphs.py` the way
`dashboards_graphs.py` already does, and have the two routes share one handler rather than
re-implementing the mapping. Then settle the published contract on 409 in all three places
(route decorator, `docs/02-dashboards/dashboards-api.md:417-423`) and correct the API doc's
`422`. If `POST /api/v1/graphs/` is meant to be retired in favour of the dashboard-scoped
route, delete it and its documentation instead — leaving a second mounted surface with a
different failure contract is the part that costs. Re-check `graph_repo.py:130-135` while
there: it converts a constraint violation into an indistinguishable `SQLAlchemyError`, so
neither route can currently tell a name conflict from a connection failure.

### TXN-008 — The development seeder deletes the seeded dashboard's graphs on every process start, and the cascade takes every uploaded dataset with them

**Severity** — MEDIUM

**Zone** — "Schema and reference-data mutation, and the window each step opens"

**Observation** — `DatabaseStarter.startup` calls `run_dev_seeders()` on every start in the
development tier (`db/starter.py:176-179` → `db/dev_seeders.py:19-40` →
`db/seeders/test_media_dash.py:25`). That seeder's step 3 is unconditional:
`db/seeders/test_media_dash.py:128-129` issues `delete(Graph).where(Graph.dashboard_id ==
dashboard_id)`, and the two `INSERT`s that follow it use
`on_conflict_do_nothing(index_elements=["dashboard_id", "name"])`
(`test_media_dash.py:146,175`) — so the `ON CONFLICT` guard that makes the insert idempotent
sits downstream of a delete that is not. `aggregated_data.graph_id` is
`ForeignKey("graphs.id", ondelete="CASCADE")` (`db/models/aggregated_data.py:77-80`), so the
delete cascades. The seeder's own docstring at `test_media_dash.py:4` reads "Idempotent - can
be re-run without creating duplicates or breaking other dashboards", and
`test_media_dash.py:128` annotates the delete "idempotent - ensures clean state".

This is a destructive path that runs on every start, and it is the last step before
`db/starter.py:193` reports the database ready. It is covered by no exclusion: the
`pg_advisory_lock(42)` in `alembic/env.py:113-127` is released as soon as `alembic upgrade
head` returns (`db/starter.py:300-321`), before `ensure_admin_user`
(`starter.py:174`), before the seeders (`starter.py:177-179`), before
`cleanup_old_logs` (`starter.py:187`) and before `recreate_test_database`
(`starter.py:190-191`). A production-tier deployment with `--workers 4` would run this four
times concurrently; the dev tier runs it once per restart, which is the frequent case.

**Evidence** — Uploaded a dataset to the seeded `test_media_dash` (4 `aggregated_data` rows
confirmed by query), then let the app container restart, which re-ran the lifespan and
therefore the seeder:

```
before restart:  agg=4  graphs=2  dashboard_filter_values=0
app-1  |  {"message": "Created graph 'Monthly TVR by Brand' id=...", "module": "mkobi.db.seeders.test_media_dash"}
after  restart:  agg=0  graphs=2  dashboard_filter_values=0
```

The graphs are recreated with new ids, so the cascade had nothing to key on — the aggregate
rows are simply gone.

**Consequence** — In the development tier, every application restart destroys every uploaded
dataset for `test_media_dash` while leaving the dashboard, its graphs and its filter
definitions in place, so the dashboard renders as empty rather than as broken. A developer
comparing two CSV revisions across a restart compares nothing. The scope is confined to the
development tier and to the one seeded dashboard, which is why this is not graded higher; the
reportable part is that the seeder's own documentation promises an idempotence its delete
does not deliver, and that the step is ordered after the only exclusion in the system and
before the service is declared ready.

**Recommendation** — Take the graph rows out of the delete. The seeder already upserts the
dashboard, the filters and the bindings, and both graphs are declared with `ON CONFLICT DO
NOTHING`; dropping line 129 makes the whole seeder genuinely idempotent and removes the
cascade. If the delete is wanted, it belongs behind an explicit operator action, not in a
startup path. Independently, amend the docstring at `test_media_dash.py:4` to say what the
seeder does to uploaded data, so the next reader is not misled. Nothing here needs to change
for the production tier, which does not run seeders.

### TXN-009 — No setting can change a connection-pool parameter, and the app process builds two differently-sized engines

**Severity** — MEDIUM

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Observation** — Every path into the store is enumerated in Appendix A. The parameters that
govern those connections are literals in two constructions and settings in none.
`db/session.py:40-47` builds the process-wide application engine with
`pool_pre_ping=True, pool_size=10, max_overflow=20, pool_timeout=30` hard-coded, and
`db/session.py:60-66` binds the sessionmaker to it once, so this is the client every request
path and every worker shares. `db/starter.py:148-152` builds a **second** engine in the same
process with `pool_pre_ping=True, pool_recycle=300` and no `pool_size`, no `max_overflow` and
no `pool_timeout` — i.e. SQLAlchemy's defaults of 5 and 10 and a 30-second checkout wait, a
different set of numbers from the first engine for no stated reason. It is used by
`_check_db_connection` (`starter.py:82-117`), `_get_alembic_revision` (`starter.py:119-136`),
`_verify_role_privileges` (`starter.py:384-399`) and `cleanup_old_logs`
(`starter.py:401-424`), and is disposed at `starter.py:426-431`. `alembic/env.py:107-110` adds
a third client with `poolclass=pool.NullPool`, so a migration run opens as many connections as
it wants. `config.py` exposes no pool field — grep for `pool` in `config.py` returns nothing.

**Evidence** — Static: the four numbers in `db/session.py:44-46` and the three absences in
`db/starter.py:150-151`. The deployed values are the only ones available, since no setting
and no environment variable reaches them:

```
$ grep -n "pool" src/mkobi/config.py
(no matches)
```

**Consequence** — The application's connection footprint cannot be sized for a given
Postgres `max_connections` without editing source and rebuilding, and the number an operator
would size from (`pool_size`/`max_overflow` = 30) is not the only one in play: a process
running the starter path also carries up to 15 from the second engine, and a migration run
adds an unbounded burst on top. With `--workers 4` in production each of those multiplies
four-fold, and there is no value in any configuration surface that reveals any of it. What
the pool costs as a measurement, and the tier's ceiling, are phase 11's; the finding here is
that the parameters are unreachable by configuration at all.

**Recommendation** — Move `pool_size`, `max_overflow`, `pool_timeout` and `pool_recycle` into
`config.py` as settings with the current values as defaults, so they are visible in
`docs/06-backend/configuration.md` alongside every other tunable. While there, decide whether
`DatabaseStarter` needs its own engine: four of its five uses are start-up-only reads and one
is a single `DELETE`, so the cheapest fix is to reuse the application engine
`ensure_admin_user` already uses (`starter.py:332,365`) and delete the second one, which also
removes the `pool_recycle` inconsistency between the two.

### TXN-010 — Hand-written privilege DDL runs outside any transaction, only against the test database, and the advisory lock is built with a forbidden f-string

**Severity** — LOW

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Observation** — The write paths that bypass the persistence layer are enumerated in
Appendix A. Three of them are not covered by a transaction, error-reporting convention or
layering that the rest of the codebase has. `db/starter.py:279-285` issues five statements —
`GRANT USAGE, CREATE ON SCHEMA public`, `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`,
`GRANT USAGE ON ALL SEQUENCES`, and two `ALTER DEFAULT PRIVILEGES` — over a connection opened
with `isolation_level="AUTOCOMMIT"` (`starter.py:275`). Each is therefore its own
transaction; a failure on the third leaves the first two applied and the last two not, with
only a `logger.error` at `starter.py:290-293`. They run only against the recreated **test**
database (`starter.py:268-287`); the equivalent privileges for the main database are not
granted by any code path, so the least-privilege role described at
`db/starter.py:384-399` depends on `docker/init-scripts/` having done it. The advisory lock
that does exist is expressed as an f-string inside `text()` at `alembic/env.py:116,125,132`:
`text(f"SELECT pg_advisory_lock({MIGRATION_ADVISORY_LOCK_KEY})")` with the key at
`alembic/env.py:58`. `AGENTS.md` forbids raw SQL via f-strings; the interpolated value is a
module constant integer, so this is a rule violation rather than an injection.

**Evidence** — Static: the `isolation_level="AUTOCOMMIT"` constructions at
`db/starter.py:230-233` and `db/starter.py:275`, the five unparameterised `text()` statements
at `db/starter.py:279-285`, and the three f-string `text()` calls in `alembic/env.py`. None
of these paths executed in this environment: the test-database recreation is gated on
`env == TEST or recreate_test_db` (`db/starter.py:190`) and is never true in development, and
`auto_migrate` is false here, so `alembic/env.py:113-127` was not entered. The
consequence of the f-string and the AUTOCOMMIT DDL is therefore argued from the code, not
observed.

**Consequence** — No runtime consequence today: neither path runs on the development stack.
What it costs is the next time someone does: a partially-applied privilege grant on a
recreated test database surfaces as a permission error in a test run rather than as a failed
grant, and the reason is in a log line. The f-string is a standing conflict with a project
rule that `ruff` cannot catch.

**Recommendation** — Bind the constant rather than interpolating it, matching the rest of the
file's parameterised style: `text("SELECT pg_advisory_lock(:key)")` with
`{"key": MIGRATION_ADVISORY_LOCK_KEY}`. Wrap the five grants in one explicit transaction on a
non-AUTOCOMMIT connection so a failure is all-or-nothing, and state in the module docstring
that these privileges must be established for the main database by the init script, because
no code path does it. Alternatively, promote them into an Alembic migration, which would put
them under the advisory lock and in the linear chain (phase 14's inventory).

### TXN-011 — The one exclusion in the system covers only the migration run, and the periodic sweep runs on every replica with nothing electing one

**Severity** — LOW

**Zone** — "Exclusion mechanisms as one system: lifetime, holder, and what is not covered"

**Observation** — The complete inventory of mutual exclusion in `src/` is one mechanism.
`pg_advisory_lock(42)` at `alembic/env.py:113-117`, released in a `finally` at
`alembic/env.py:122-127` and again on the `except` path at `alembic/env.py:128-134`. Lifetime:
one `alembic upgrade head` invocation, on one connection, held by the thread that ran
`command.upgrade` inside `asyncio.to_thread` (`db/starter.py:300-320`). What it does not
cover: everything else `DatabaseStarter.startup` mutates after `_apply_migrations` returns —
`ensure_admin_user` (`starter.py:174`), the dev seeders (`starter.py:177-179`),
`cleanup_old_logs` (`starter.py:187`) and `recreate_test_database` (`starter.py:190-191`).
The `ON CONFLICT` upserts in `ensure_admin_user` (`starter.py:369-381`) and in the seeders
are what make the first two safe, not the lock; the last two are idempotent by deletion. The
lock is also acquired with the blocking `pg_advisory_lock`, not `pg_try_advisory_lock`, and
with no `lock_timeout` set, so a process that blocks on it waits for as long as the
holder's migration takes, and nothing logs that it is waiting.

Separately, the operation a periodic schedule runs on more than one replica is
`cleanup_stale_processing_logs` via `start_stale_processing_cleanup_task`
(`app.py:120-125`), scheduled in every process that starts. **No mechanism
decides which replica runs it** — there is no leader election, no advisory lock on the timer,
no Redis key. The same is true of the one-shot startup mutations above, which run once per
process: four times over in a `--workers 4` deployment.

**Evidence** — Grep across `src/`, `alembic/` and `tests/` for `advisory`, `with_for_update`,
`FOR UPDATE`, `SETNX`, `nx=True` and lock primitives returns `alembic/env.py:58,116,125,132`
and nothing else. The unelected replication is visible in the current dev log, where five
process starts each print their own
`"Starting stale processing cleanup task (interval=300s, timeout=30m)"`.
That last figure is also the deployed timeout, which TXN-012 relies on.

**Consequence** — Today every one of these paths is idempotent, so a duplicate run is wasted
work and a log line, not damage — which is why this is graded LOW rather than as a lost-update
risk. The absent bounds are the reportable part: the advisory lock can be held by a
migration that never finishes, and nothing in the waiter's log says so. The unelected
periodic sweep is currently also inert, for a reason unrelated to any of this: see TXN-003,
where its predicate never matches. If TXN-003 is fixed and the sweep is left unelected, four
workers will sweep every 300 seconds instead of one, which is still harmless but should be a
decision rather than an accident.

**Recommendation** — Record the intended coverage in the docstring at
`alembic/env.py:100-102`, which currently claims the lock "prevent[s] concurrent migrations
in multi-instance deployments" without saying what else runs outside it. Use
`pg_try_advisory_lock` with a bounded retry and a warning on refusal, so a worker that cannot
get the lock says so instead of vanishing. For the periodic sweep, either give it its own
advisory key so only one worker sweeps, or move it into the existing `rq-worker` service,
which is a single process and is already deployed for exactly this kind of work.

### TXN-012 — The documentation states three boundary properties the code does not have

**Severity** — LOW

**Zone** — "Who opens the unit of work, and who decides it ends"

**Observation** — `[DOC-UPDATE]` Three statements in the backend documentation describe
transaction behaviour that the code does not implement. `docs/06-backend/architecture.md:128`
describes admin user creation as using "a SAVEPOINT (nested transaction) to handle race
conditions cleanly"; `db/starter.py:365-381` uses a top-level `async with db.begin():`, and
the race is handled by the `ON CONFLICT (email) DO NOTHING` clause, which
`docs/SPEC.md:148` describes correctly and `architecture.md` does not.
`docs/06-backend/architecture.md:154` states the stale-processing timeout is "default: 5
minutes". The code has two defaults: `workers/data_worker.py:39`
`DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES = 5`, used as the signature default of
`cleanup_stale_processing_logs` and `start_stale_processing_cleanup_task`, but
`config.py:387` defaults `STALE_PROCESSING_TIMEOUT_MINUTES` to 30 and that is what
`app.py:120-124` passes, so the running value is 30. `docs/03-processing/file-cleanup.md:70`
and `docs/SPEC.md:144` both say 30, agreeing with the deployed behaviour and with neither
`architecture.md` nor the function signature.
`services/file_processing.py:253-254` asserts "proper transaction atomicity" for a handoff
that has none — covered as TXN-002, and listed here because it is the same class of defect:
a comment standing in for a property.

**Evidence** — Each claim is a direct comparison of the cited documentation line with the
cited code line. The `architecture.md:154` default is contradicted by the application's own
startup log on the running stack, which reports `timeout=30m`.

**Consequence** — No runtime consequence: the code's behaviour is unchanged by the text. The
cost is that a reader auditing the transaction boundaries works from three false premises, and
`architecture.md:154` in particular is the sentence a reader would use to conclude that
TXN-003's backstop fires within 5 minutes.

**Recommendation** — Correct `architecture.md:128` to name the `ON CONFLICT` clause (matching
`SPEC.md:148`) and `:154` to 30 minutes (matching `config.py:387` and `file-cleanup.md:70`).
These are one-line edits and belong with the TXN-002 and TXN-003 fixes, which change the
behaviour those sentences are meant to describe.

## Distribution

All twelve findings land on the request/worker boundary of the application tier, and the
concentration is not spread across subsystems: eight of the twelve are in the write path
itself (routes, services, the worker transaction, the aggregate storage layer). The single
component carrying the most is the **upload processing pipeline's transaction boundary** —
`workers/data_worker.py`, `services/file_processing.py`, `services/data_service.py` and
`data/storage/manager.py` together account for four findings including two CRITICAL — because
it is the only place in the system where one unit of work spans a file, a queue, a status
record and a derived value, and it is the only place with no convention holding those four
together. The user/admin route family is the second cluster, and its cause is a single
missing decision rather than a design problem.

- `api/routes/users.py`, `api/routes/admin.py`, `services/user_service.py` — 1 finding (TXN-001), four endpoints
- `workers/data_worker.py`, `services/file_processing.py`, `services/data_service.py` — 3 findings (TXN-002, TXN-003, TXN-004)
- `data/storage/manager.py`, `db/repositories/access_repo.py`, `db/repositories/graph_repo.py` — 3 findings (TXN-005, TXN-006, TXN-007)
- `db/dev_seeders.py`, `db/seeders/test_media_dash.py` — 1 finding (TXN-008, development tier only)
- `db/session.py`, `db/starter.py`, `alembic/env.py` — 2 findings (TXN-009, TXN-010)
- `alembic/env.py`, `app.py` — 1 finding (TXN-011)
- documentation only — 1 finding (TXN-012)

## Cross-Finding Analysis

Two causes account for eight of the twelve findings.

**Cause 1 — no declared owner for the end of a unit of work (TXN-001, TXN-002, TXN-003,
TXN-004).** `db/session.py:70-88` yields a session and commits nothing, so every write path
is individually obliged to end its own transaction. Four endpoints forgot (TXN-001); the
upload path remembered to commit but did it *after* dispatching the job (TXN-002); the worker
remembered to commit but put its whole status machine inside the transaction it commits
(TXN-003); and the derived-value rebuild inside that same transaction tests a condition the
table write above it does not (TXN-004). These are four symptoms of one missing convention,
and fixing them one at a time will produce a fifth variant. The phase-01 finding TOPO-001 is
a fifth symptom of the same convention from the other direction: the compensating `FAILED`
write that was written is skipped because the `raise` that triggers it sits outside the
boundary that would have committed it. The remediation belongs in one place, not five.

**Cause 2 — invariants carried by code and by schema disagreeing about who enforces them
(TXN-005, TXN-006, TXN-007, TXN-008).** In each case a constraint exists in the database and
a read-then-write exists in Python, and the two were written without reference to each other:
the composite primary key on `dashboard_access` (TXN-006) and the unique index on
`graphs(dashboard_id, name)` (TXN-007) are both the last line of defence *and* the
user-visible outcome, and in TXN-007 one of the two mounted routes declares the correct
recovery it does not implement. TXN-005 and TXN-008 are the destructive-operation half of the
same pattern: the selection predicate and the mutation condition are maintained separately and
have drifted — in TXN-005 the `DELETE` is conditional and the `DELETE` of the derived table
next to it is not; in TXN-008 the seeder's `ON CONFLICT` idempotence guard sits downstream of
a `DELETE` that is not. The project's own `docs/SPEC.md:148` describes the correct pattern for
this ("atomic UPSERT … eliminating the TOCTOU race condition"), so the remedy is already
written down and simply has not been applied to these four writers.

The two CRITICALs in the upload path and the missing-commit CRITICAL in the user path are
independent — different subsystems, different fixes — and only share the convention named
above. Phase 04's AUTH-007 ("the admin bootstrap reports success for a key it did not create")
is a third instance of the *shape* — a success-shaped response over a write that did not
happen — reached by a different mechanism, and is owned by that phase; it is named here so
that a remediator treats the pattern once rather than three times.

## Roadmap

**Step 1 — declare who ends a unit of work, then fix the four endpoints (TXN-001).** Nothing
else in this roadmap can be verified until a re-read from a second session distinguishes a
committed write from a flushed one. Choose the DI layer or the route as the owner; add the
commits; move the `is_active` commit ahead of the Redis revocation. *Before step 2:* the
response-body assertions in `tests/test_admin_user_management.py` and
`tests/test_token_revocation.py` are re-read from an independent session and pass, and the
four endpoints' writes survive a fresh process.

**Step 2 — move the processing-log transitions outside the worker's transaction (TXN-003,
then TXN-002).** TXN-003 first: commit `processing` as its own transaction before the work
begins, and `completed`/`failed` after. That is what makes the backstop reachable and the
status endpoint truthful. TXN-002 second: commit the log row before dispatch, so a dispatched
job can never outlive its record. They are ordered because TXN-002's fix is only observable
once TXN-003's fix means the row is visible to the worker's own writes. *Before step 3:* the
independent-session poll of TXN-003 observes `processing` during a real job, and
`cleanup_stale_processing_logs(0)` marks a planted row while leaving a healthy in-flight one
alone.

**Step 3 — reconcile the guards with the constraints (TXN-006, TXN-007).** Convert
`grant_access` and, if it survives, `POST /api/v1/graphs/` to conflict-tolerant writes; align
the two graph-creation routes on one handler. *Before step 4:* a concurrent duplicate grant
returns the existing row rather than a 500, and both graph routes return 409.

**Step 4 — give the aggregate rebuild a declared exclusion and a bound (TXN-005, TXN-004).**
Take the `pg_advisory_xact_lock` before the `DELETE`, set a `lock_timeout`, then make the
`dashboard_filter_values` clear share the `if aggregates` condition the `DELETE` already
tests. *Before step 5:* two concurrent rebuilds serialise on a named lock visible in
`pg_locks`, and an upload that matches no graph leaves both tables untouched with a log
message that says so.

**Step 5 — the low-band cleanups, in one pass (TXN-008, TXN-009, TXN-010, TXN-011, TXN-012).**
Remove the seeder's graph `DELETE`; move the pool parameters into `config.py` and drop the
second engine; bind the advisory-lock key; bound the lock acquisition; fix the three sentences.
Grouped because none depends on another and all are small. *Before closing the phase:* the
documentation statements in TXN-012 match the code as changed by steps 1, 2 and 4.

## Rollout Safety

Steps 1 and 2 change observable behaviour in ways other zones depend on.

**Step 1** makes writes that are currently discarded actually persist. Anything that has been
running against a discarded write will start taking effect: user rows created through
`POST /api/v1/users/` will begin to exist and to collide on the unique `users.email` index
(so the 409 at `services/user_service.py:176-179` starts firing for clients that have been
getting a 201 with a phantom id), and role changes will take effect, so any account an
operator believes is still a `viewer` may now be an `editor` or `admin`. Phase 04's
AUTH-003 and AUTH-004 are in the same area and should be re-checked against the change; their
own findings assume specific role and session states. Re-verify by re-reading the four
endpoints' targets from a second session and by confirming that `POST /auth/register` and the
admin-approval path — which already commit — are unchanged. Revert is a single commit
revert, but the rows that begin persisting do not un-persist: if the change must be pulled
back, the users created in the interim need deleting by hand.

**Step 2** changes what `GET /api/v1/upload/status/{task_id}` and
`GET /api/v1/upload/result/{task_id}` return during a job: `uploaded` becomes `processing`
and then `completed`, and the frontend polling loop
(`docs/07-frontend/upload-ui.md:113-116`) will start rendering a `processing` state it has
never been given, including the `progress: 50` value at `services/data_service.py:340` that
no client has observed before. Phase 05 owns the pipeline and owns the data half of this
boundary; it should confirm the status contract before the change lands. It also makes
`cleanup_stale_processing_logs` live for the first time, so a worker that is genuinely stuck
for 30 minutes will now start producing `failed` rows it has never produced — that is the
intent, but it will look like a regression the first time it fires. Re-verify with the
TXN-003 poll (an in-flight job is visible as `processing` and is not swept) and with one
planted stale row (it is swept). Revert is a single commit revert; no schema change is
involved in either step.

## Appendices

### Appendix A — Access-path inventory and client lifetime

| Path | Client | Constructed | Lifetime | Ends the unit of work? |
|---|---|---|---|---|
| Every HTTP request | `get_async_sessionlocal()` | once per process, `db/session.py:57-66` | request | **no** — `get_db_dependency`, `api/deps.py:101-116` |
| `process_csv_background` (in-memory queue) | `get_session()` | per call, `data_worker.py:584` | the whole job | yes — `async with session.begin()`, `data_worker.py:585` |
| `process_csv_background` (RQ) | `get_session()` | per call, via `data_worker.py:871-901` → `:584-585` | the whole job | yes — `async with session.begin()` |
| `cleanup_stale_processing_logs` | `get_session()` | per run, `data_worker.py:270-271` | one statement | yes — `async with session.begin()` |
| `mark_orphaned_uploaded_logs_failed` | `get_session()` | per run, `data_worker.py:332-333` | one statement | yes |
| `find_task_file` / temp-file scan | none | — | — | no store access |
| `ensure_admin_user` | `get_async_sessionlocal()` | `starter.py:332,365` | one statement | yes — `async with db.begin()`, `starter.py:368` |
| `cleanup_old_logs` | second engine | `starter.py:148-152` | one statement | yes — explicit `conn.commit()`, `starter.py:421` |
| `_get_alembic_revision`, `_check_db_connection`, `_verify_role_privileges` | second engine | same | read-only | no writes |
| `recreate_test_database` | two AUTOCOMMIT engines | `starter.py:232,275` | DDL | **no** — AUTOCOMMIT, `starter.py:279-285` |
| `_apply_migrations` | `NullPool` engine | `alembic/env.py:107-110` | one migration run | yes — per-migration |
| `ProcessingLogService.delete_processing_log` | caller's | — | — | **no** — and unreachable from any route |

### Appendix B — Constraint inventory mapped to the invariant each enforces

| Constraint | Invariant | Writers | Outcome on conflict |
|---|---|---|---|
| `dashboard_access_pkey (user_id, dashboard_id)` | one grant per pair | `access_repo.py:65-71` (insert), `:50-56` (read first) | 500 `INTERNAL_ERROR` — TXN-006 |
| `idx_graphs_dashboard_name` unique | one graph name per dashboard | `graph_repo.py:115-137` via two routes | 409 on one, 500 on the other — TXN-007 |
| `users.email` unique | one account per email | `starter.py:369-374` (upsert), `user_repo.py:36-49` (plain) | `ON CONFLICT DO NOTHING` vs bare insert — asymmetry, see TXN-001 |
| `uq_aggregated_data_dashboard_graph_dims` | one row per (dashboard, graph, dims) | `manager.py:311` `_bulk_upsert` (`ON CONFLICT DO UPDATE`), `manager.py:280` `_bulk_insert` (plain), `manager.py:150` `upsert_aggregate` (`ON CONFLICT DO UPDATE`, `:179`) | the same logical insert is conflict-tolerant on the append path and a plain insert on the overwrite path; correctness on overwrite depends entirely on the `DELETE` having run — TXN-005 |
| `dashboard_filter_values` unique (dashboard_id, filter_name, filter_value) | one value per filter per dashboard | `data_worker.py:817-819` | clear-then-insert inside the same transaction; tolerant, but the clear is unconditional — TXN-004 |
| `aggregated_data.graph_id` → `graphs.id` `ON DELETE CASCADE` | aggregate rows die with their graph | `test_media_dash.py:129` deletes the graph rows | every dataset for the dashboard is destroyed — TXN-008 |

### Appendix C — Exclusion inventory

| Mechanism | Lifetime | Holder | Acquired | Released | Not covered |
|---|---|---|---|---|---|
| `pg_advisory_lock(42)` (`alembic/env.py:113-117`) | one `alembic upgrade head` | the migrating thread, via `to_thread` (`starter.py:320`) | blocking, no timeout | `finally` at `env.py:122-127`, plus `env.py:128-134` | everything `startup` mutates after `_apply_migrations`; a `DROP DATABASE` in `recreate_test_database` (phase 01, TOPO-004) |
| Implicit row locks from `delete_by_dashboard` | the worker transaction | the job holding the transaction | at `manager.py:114` | commit / rollback / disconnect | any second identifier for the dashboard; APPEND mode takes no lock at all; no bound — TXN-005 |
| `TaskQueue` single consumer (`app.py:131-143`) | the process | the process | at lifespan | at shutdown | other processes' queues; per-process, so 4 production workers run 4 independent consumers |

Operations that must be exclusive and hold no declared mechanism: the OVERWRITE rebuild of a
dashboard (TXN-005), the dev seeders' graph replacement (TXN-008), and the periodic stale
sweep (TXN-011).

### Appendix D — What could not be settled in this environment

- **The production tier was not started.** Reaching the `--workers 4` shape needs a populated
  `.env` and a prior `npm run build`, and the same environment constraint phase 02 recorded
  applies. Every statement in this report about multi-replica behaviour (four workers each
  running the startup mutations and their own cleanup loop, four concurrently seeded
  dashboards) is derived from `docker/Dockerfile`'s `CMD` and FastAPI's per-worker lifespan
  contract, not observed.
- **The cross-process status case was not exercised.** With one app process in dev, a status
  request served by a worker other than the one holding the job cannot be reproduced. It was
  not filed: `GET /api/v1/upload/status/{task_id}` reads the `processing_logs` row
  (`services/data_service.py:320`), not the in-memory map, so the per-process `TaskQueue`
  status dictionary is write-only and no cross-process status defect exists.
- **`lock_timeout` / `statement_timeout` were not reconfigured.** TXN-005's absent bound is
  reported as the server reports it (`0` on the deployed database). A deployment that sets
  them would bound the wait without a code change.
- **The `text()` f-string in `alembic/env.py` was not executed** (`auto_migrate` is false in
  this environment), so TXN-010's f-string is a rule violation argued from the source, not an
  observed behaviour.
- **`recreate_test_database` was not run**; TOPO-004 already records that it is never
  executed because the test harness bypasses the lifespan, and this phase did not re-derive it.

### Appendix E — Reproduction method and residue

Probes ran in throwaway containers on the compose network
(`docker compose -p mkobi -f docker/docker-compose.yml -f docker/docker-compose.override.yml
run --rm --no-deps`), never inside the running `app` service: importing `mkobi` writes
`__pycache__` under `/app`, which trips uvicorn's `--reload` watcher, restarts the app, and
re-runs the dev seeder — which destroys the state under test (this is TXN-008, and it
reproduced twice as a side effect before the cause was identified). All probe scripts were
deleted after the transcripts above were captured.

Dev-stack state after the probes: `users=1` (the bootstrap admin), `graphs=2`,
`aggregated_data=0`, `processing_logs=0`, `dashboard_filter_values=0`, `dashboard_access=0`
— the values the phase found. The probe `processing_configs` update and the `graphs.metrics`
change used for TXN-004 were both reverted, and all probe users, graphs and log rows were
deleted. The login rate-limit key `login:172.21.0.1` (5 attempts / 300 s,
`api/routes/auth.py:88-90`) was cleared once to continue probing; that is rate-limiter state,
not application state.
