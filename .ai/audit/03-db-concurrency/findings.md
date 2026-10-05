---
phase: 03-db-concurrency
executed: 2026-10-05
executor: auditor
problems-only: true
findings: 12
by-severity:
  CRITICAL: 1
  HIGH: 1
  MEDIUM: 4
  LOW: 6
---

# Phase 03 — Findings

## Summary

The store was examined as a shared, concurrent resource across all nine blocks: every path that
reaches PostgreSQL (request, RQ work horse, `DatabaseStarter` lifespan, Alembic, the documented
`--recreate-test-db` one-shot), the lifecycle of every unit of work, the constraint-enforced
invariants, the four exclusion mechanisms, the reconciler, and the migration chain. The dev stack
was already running and served as the instrument: two findings were reproduced end to end against
the live database, and `pg_stat_activity` was read directly to attribute one pooled connection to
the starter engine and two to the application request pool. The single most consequential thing
found is that two live write paths do not own their transaction: `AuthService.approve_registration_request`
commits the account before the password-change flag and the request status, so the three-row write can
part-commit into a state the API cannot then repair (TXN-101, CRITICAL), and `PUT` and
`DELETE /api/v1/processing-configs/{dashboard_id}` answer `200` and `204` while committing nothing
(TXN-102, HIGH). Three MEDIUM findings follow from the same class
of defect — a missing `IntegrityError` classification, an unsynchronised admin-count check, and an
exclusion released before the work dispatched under it — and six LOW findings cover a duplicated
retention delete, a dead generic repository, an RQ client that keeps the library default transport,
and three documentation statements the code contradicts.

## Findings

### TXN-101 — Registration approval commits the account before the flag and the request status, so the three-row write can part-commit

**Severity** — CRITICAL

**Zone** — "Multi-row and multi-resource domain writes: does the boundary sit where the invariant
is"

**Observation** — `AuthService.approve_registration_request` is documented as owning one
transaction over three writes, but the first of the three writes is performed by a nested call that
commits on its own. The sequence therefore spans **two** transactions: the `users` row becomes
durable inside `create_user`, and the `force_password_change` flag and the `registration_requests`
status become durable only at a second commit later.

**Evidence** — `src/mkobi/services/auth_service.py:672-689`, the whole sequence:

```python
        temp_password = self._generate_temp_password()
        user = await self.create_user(
            email=req.email,
            password=temp_password,
            role=UserRole.VIEWER,
            db=db,
        )

        # User must change the temporary password on first login.
        await self.user_repo.update(user.id, db, force_password_change=True)

        await self.reg_request_repo.update_status(
            request_id=request_id,
            status=RegistrationStatus.APPROVED,
            db=db,
            reviewed_by=admin_user_id,
        )
        await db.commit()
```

`src/mkobi/services/auth_service.py:163`, the commit that lands first — inside `register_user`,
which `create_user` calls at line 385 (`return await self.register_user(email, password, db, role)`):

```python
            await db.commit()
```

The claim the code does not meet, `src/mkobi/services/auth_service.py:639-641`:

```
        Owns the whole transaction: create the user, set the
        force_password_change flag, mark the request approved, commit, and only
        then hand the temporary password to the store.
```

and the same single-commit claim published to readers in `docs/04-admin/admin-api.md:735-739`:

```
create user             ┐
set force_password_change│  one transaction,
update request status   ┘  opened and committed by the service
      ↓
COMMIT
```

**Consequence** — a failure or a process kill between `auth_service.py:163` and
`auth_service.py:689` leaves a `users` row holding the bcrypt hash of a temporary password that
existed only in the worker's memory, with `force_password_change` still `false`, and the
`registration_requests` row still `pending`. No one can log in as that account, nobody knows its
password, and the request stays offerable in the admin list. The state does not self-heal and has no
API recovery: retrying the approval re-enters `approve_registration_request`, the guard at line 666
still passes because the request is `pending`, `create_user` reaches
`_check_email_uniqueness` (`auth_service.py:113-118`), which raises `ValueError(f"User with email
'{email}' already exists")`, and `api/routes/admin.py:442-447` maps that to
`500 INTERNAL_ERROR "Error approving registration request"` — so every subsequent retry is a 500.
Rejecting the request instead only sets `rejected`, and `AuthService.register_request` refuses both
`pending`/`approved` and `rejected` existing rows, so the address stays unusable either way.
Recovery requires deleting the orphan `users` row directly in PostgreSQL.

**Recommendation** — remove the nested commit's authority over the caller's transaction: have
`approve_registration_request` write the user itself (or pass an explicit flag that makes
`register_user` skip its `await db.commit()`), so that create + flag + status share the single
commit at line 689 and nothing is durable before it. Keep the Redis write after that commit — that
ordering is correct and is not the defect. Once the boundary is right, add the test the current
suite lacks: a mid-sequence failure must leave neither the `users` row nor the status change. Do not
attempt this by moving `auth_service.py:163` alone — `register_user` is also the body behind
`UserService.create_user` and the auth `POST /users/` path, both of which B1's accepted ruling
requires to keep committing for themselves; the narrower owner is the correct seam.

### TXN-102 — The processing-config write endpoints report success and persist nothing

**Severity** — HIGH

**Zone** — "Who opens the unit of work, and who decides it ends"

**Observation** — `ProcessingConfigService.upsert` and `ProcessingConfigService.delete` are the
only write methods among the dashboard-scoped services that neither commit nor delegate the ending
to anyone, and their two route handlers do not commit either. `get_db_dependency` is explicitly
commit-free by design, so the request's unit of work is discarded when the pooled connection is
returned.

**Evidence** — `src/mkobi/services/processing_config_service.py:172-199` — the write path, with no
`await db.commit()` anywhere in the method:

```python
        existing = await self.config_repo.get(dashboard_id, db)
        if existing:
            updated = await self.config_repo.update(
                dashboard_id, db, settings=stored
            )
            if updated is None:
                raise ValueError(
                    f"Failed to update config for dashboard {dashboard_id}"
                )
            logger.info("Config updated: dashboard_id=%s", dashboard_id)
            updated_settings = ProcessingSettingsModel.model_validate(updated.settings)
            return cast(
                ProcessingConfigRead,
                ProcessingConfigRead.model_validate(
                    {
                        "dashboard_id": updated.dashboard_id,
                        "settings": updated_settings,
                        "updated_at": updated.updated_at,
```

`src/mkobi/api/routes/processing_configs.py:182-188` — the handler returns the service's value and
never ends the unit of work:

```python
        config = await processing_config_service.upsert(
            dashboard_id=dashboard_id,
            db=db,
            settings=config_update.settings,
            metric_agg=config_update.metric_agg,
        )
        return config
```

`src/mkobi/api/deps.py:126-129` — the declared contract the above violates:

```
    Creates a new session for each request and closes it after completion. It
    does not commit and does not roll back: closing the session is not a
    transaction boundary. The request's unit of work belongs to the service
    layer, whose write methods commit their own transactions.
```

Reproduced against the running dev database: `upsert` returned a populated `ProcessingConfigRead`
with a live `updated_at` and the row was visible inside the transaction, and a **fresh** session
found no row after the first session closed. `delete` returned `True` and the row was gone inside
the transaction, and the row was still present from a fresh session afterwards. `pg_stat_activity`
independently shows the request pool's last query as `ROLLBACK`, which is the pool's
`reset_on_return`, not any layer's decision.

**Consequence** — `PUT /api/v1/processing-configs/{dashboard_id}` returns `200` with a correct
`ProcessingConfigRead` body and changes nothing; `DELETE` on the same path returns `204` and
changes nothing. A caller using the documented API loses the write with no error, no log line
naming a rollback, and no way to tell a stored configuration from a discarded one. The only
`processing_configs` row in the running dev database was written by the dev seeder, which commits
its own transaction — the API path has never produced one. The React SPA does not currently call
either endpoint, so today's blast radius is the API surface and any direct consumer of it, not the
upload pipeline.

**Recommendation** — give `upsert` and `delete` the same owner every sibling write has: end the
transaction inside the service after a successful write, on the model `UserService.delete_user`
uses. That is the smaller change and the one that survives a future caller. The alternative — a
route-level `await db.commit()` — would leave the interface aliases
(`create_processing_config`, `update_processing_config`, `delete_processing_config`,
`services/processing_config_service.py:241-271`) callable from a non-request path with no owner, so
do not choose it. `tests/test_services_integration.py:611-619` is a remediation blocker: it asserts
only `result is not None` and `result.dashboard_id == dashboard_id`, so it proves the operation ran
and not that its effect survived; it must be extended to read the row back from a second session.

### TXN-103 — A duplicate dashboard name is reported as HTTP 500 instead of 409, and no pre-check exists to catch it

**Severity** — MEDIUM

**Zone** — "Constraint-enforced invariants and their recovery paths"

**Observation** — `dashboards.name` carries a unique index, and `DashboardService.create_dashboard`
performs no name pre-check, so the index is the only detector. The route's handler chain has no
`IntegrityError` arm, so the violation is reported as an internal error rather than as the conflict
its sibling routes report.

**Evidence** — `src/mkobi/api/routes/dashboards_crud.py:158-173`, the entire handler tail:

```python
    except ValueError as e:
        logger.warning("Validation error creating dashboard: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail="Invalid dashboard data",
        ) from e
    except Exception as e:
        logger.error(
            "Error creating dashboard name=%s",
            dashboard_data.name,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error creating dashboard",
        ) from e
```

`sqlalchemy.exc.IntegrityError` is not a `ValueError`, so it reaches the second arm.
`src/mkobi/services/dashboard_service.py:109-121` shows there is no pre-check to intercept it — the
service validates the config and calls straight through to the repository, whose `create` flushes at
`db/repositories/dashboard_repo.py:134`:

```python
        config_obj = DashboardConfig(**config)
        self._validate_config(config_obj)

        try:
            # Create dashboard through repository
            dashboard_obj = await self.dashboard_repo.create(
                db=db,
                name=name,
```

Contrast `src/mkobi/api/routes/graphs.py:135-147`, which does classify the same class of violation
correctly:

```python
    except IntegrityError:
        # A flush-time integrity error leaves the transaction aborted, so the
        # next statement on this session would raise PendingRollbackError.
        await db.rollback()
        logger.error(
            "Integrity error creating graph name=%s dashboard_id=%s",
            graph.name,
            graph.dashboard_id,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.DUPLICATE_RESOURCE,
```

Reproduced against the running dev database: with one dashboard named `audit-probe-<hex>`
committed, a second `DashboardService.create_dashboard` with the identical name raised
`sqlalchemy.exc.IntegrityError` and `isinstance(e, ValueError)` was `False`. The probe rows were
deleted afterwards.

**Consequence** — any duplicate dashboard name produces a `500 INTERNAL_ERROR` with detail
`"Error creating dashboard"` and a server-side traceback, for both the ordinary sequential
duplicate and the concurrent one. The write is correctly refused and nothing is corrupted, so the
caller's data is safe; what is wrong is that a user-caused, fully expected conflict is
indistinguishable from a server fault, and the documented conflict code
(`ErrorCode.DUPLICATE_RESOURCE`, used by `layouts` and `graphs`) is never reached on this path.

**Recommendation** — add the `except IntegrityError` arm the graph route already has: roll back,
log, and raise `AppException(ErrorCode.DUPLICATE_RESOURCE)`. Do **not** add a name pre-check —
`docs/06-backend/architecture.md`'s transaction-ownership section and `services/layout_service.py`
already rule that the database is the only detector, and a pre-check would reintroduce the
read-then-write race the index exists to settle. `tests/` contains no assertion on the duplicate-name
status for this route, so nothing has to be un-asserted.

### TXN-104 — The last-admin guard reads the admin count and then deletes without any lock, so two concurrent admin deletions can leave zero admins

**Severity** — MEDIUM

**Zone** — "Read-modify-write, destructive operations, and derived values"

**Observation** — `UserService.delete_user` decides whether a deletion would remove the last
administrator by reading the whole user table and counting, and then deletes the row in the same
unit of work. Nothing serialises the two, there is no row-level lock on the read and no version
column, and the count is taken from a plain unadorned `SELECT`.

**Evidence** — `src/mkobi/services/user_service.py:88-99`, the whole guard:

```python
    all_users = await user_repo.get_all(db)
    admin_users = [u for u in all_users if u.role == UserRole.ADMIN]
    if len(all_users) > 1 and len(admin_users) <= 1:
        logger.error(
            "Deletion of last admin is prohibited. Total users: %s, admins: %s",
            len(all_users),
            len(admin_users),
        )
        raise ValueError(
            "Cannot delete admin if there are other users in the system. "
            "Assign another admin first."
        )
```

`src/mkobi/services/user_service.py:337-345`, the read-then-act with the decision and the write in
one transaction:

```python
        # Check admin deletion prohibition
        if user_obj.role == UserRole.ADMIN:
            await _check_admin_deletion_allowed(db, self.user_repo)

        # Delete through repository
        result: bool = await self.user_repo.delete(user_id, db)

        if result:
            await db.commit()
```

`src/mkobi/db/repositories/user_repo.py:137-144` confirms the read takes no lock:

```python
        try:
            query = select(user_model.User)
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
```

**Consequence** — with exactly two administrators and at least one other user present, two
concurrent `DELETE /api/v1/admin/users/{id}` calls against two *different* admin ids both read a
count of two administrators, both pass the guard, and both commit. The deployment is left with zero
administrators: `/api/v1/admin/users/`, role changes and registration approval all become
unreachable, and there is no self-service way back — the guard's own recovery instruction, "Assign
another admin first", requires an administrator. Nothing is logged that indicates the invariant was
crossed; each call logs an ordinary successful deletion.

**Recommendation** — take the count and the delete under one serialising lock. A
`SELECT ... FOR UPDATE` over the `users` table is the smallest change that closes the window and
fits the existing code, since the guard already loads every row; the alternative, a partial unique
index or a `SELECT ... FOR UPDATE` on just the admin rows, changes more than this phase should. A
shipped test must be added that drives two deletions concurrently and asserts at least one
administrator survives. Note for the record that `B1-txn-001-transaction-ownership.yaml:516-518`
deliberately left this guard unchanged when it moved the user write path, but on a different
ground — it ruled the guard "over-eager because promotions never persisted". That ruling did not
consider the concurrency window, so this is new and not a re-report of B1.

### TXN-105 — The test-database recreation exclusion is released before the migration that repopulates the database it just recreated

**Severity** — MEDIUM

**Zone** — "Schema and reference-data mutation, and the window each step opens"

**Observation** — `DatabaseStarter.recreate_test_database` acquires a per-name advisory lock around
the destructive terminate/drop/create/grant block and releases it in that block's `finally`. The
`alembic upgrade` that installs the schema into the freshly created database runs afterwards, with
no lock held.

**Evidence** — `src/mkobi/db/starter.py:370-395`, acquisition and release:

```python
                await acquire_test_database_recreate_lock(conn, str(db_name))
                try:
                    # Terminate existing connections to the target database
                    await conn.execute(
                        text(
                            "SELECT pg_terminate_backend(pid) "
```

… and the release, at `src/mkobi/db/starter.py:394-395`:

```python
                finally:
                    await release_test_database_recreate_lock(conn, str(db_name))
```

`src/mkobi/db/starter.py:437-438`, the work dispatched under that exclusion but outside it:

```python
        # Apply migrations to test database
        await self._apply_migrations(test_url)
```

**Consequence** — two processes both configured with the environment set to `test` and targeting
the same test database name — the documented CLI at `docs/99-reference/run-guide.md:291`
(`uv run python -m mkobi.db.starter --recreate-test-db`), which
`src/mkobi/db/starter.py:300-305` only admits under `ENV=test`, or two app processes in a `test`
tier with `RECREATE_TEST_DB=true` — serialise on the drop/create and then race on the migration.
The loser of that race issues `pg_terminate_backend` against the winner's live migration connection
and drops the database underneath it, so one `alembic upgrade head` dies with an
operator-command termination error while the other proceeds. The end state is still a migrated test
database, so this is not data loss; the cost is a failed run and a traceback that reads like a
database fault rather than a race. The two locks involved are keyed differently — the recreate lock
on the database name (`db/test_database_lock.py`) and the migration lock on the fixed key `42`
(`db/migration_lock.py:38`) — so neither can see the other.

**Recommendation** — hold the per-name recreation lock across `_apply_migrations`, or widen the
exclusion so the migration runs inside the locked region. Because `DROP DATABASE` cannot run inside
a transaction, the shape should be: acquire the lock on the autocommit admin connection, run the
terminate/drop/create/grant, run the migration, release in the `finally`. One shipped test has to
change with it: `tests/test_starter.py:697-698` currently asserts the **engine-creation order** —
"The grant engine is the second engine created" — and moving the migration inside the locked region
changes what that ordering assertion is anchoring, so read it before the fix rather than after.

### TXN-106 — The processing-log retention delete exists twice: a hand-written startup statement that runs, and a layered implementation nothing calls

**Severity** — LOW

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Observation** — two implementations of the same retention policy exist. The live one is a
hand-written `DELETE` executed on the starter engine's own connection during every process start.
The layered one — repository plus service, with the service opening its own `session.begin()` — has
no caller anywhere in `src/`, `tests/` or `alembic/`.

**Evidence** — `src/mkobi/db/starter.py:597-613`, the live path:

```python
        async with cast(AsyncEngine, self._main_engine).connect() as conn:
            result = await conn.execute(
                text(
                    "DELETE FROM processing_logs "
                    "WHERE finished_at < :cutoff "
                    "AND status IN (:completed_status, :failed_status)"
                ),
                {
                    "cutoff": cutoff_date,
                    "completed_status": ProcessingStatus.COMPLETED.value,
                    "failed_status": ProcessingStatus.FAILED.value,
                },
            )
            await conn.commit()
```

called unconditionally from `DatabaseStarter.startup` at `src/mkobi/db/starter.py:268`. The
unreachable twin is `src/mkobi/services/processing_log_service.py:254-258`:

```python
        # Production mode - create new session
        async with get_session() as session:
            async with session.begin():
                count = await self.log_repo.delete_old_logs(cutoff, session)
                return count
```

over `src/mkobi/db/repositories/processing_log_repo.py:349-364`. A repository-wide search for
`delete_old_logs` returns exactly three files — the interface declaration
(`src/mkobi/interfaces/repository_interfaces.py:484`), the repository and the service — and no call
site; `tests/` returns none.

**Consequence** — no runtime defect today: the live delete is correct, its predicate matches the
unreachable one exactly, and `logs_retention_days` defaults to 90 so the statement matches nothing
in a normal database. The cost is that the only *tested*, session-owning implementation of a
destructive delete is the one nothing reaches, while the implementation that does run is a
hand-written statement in the startup path with no lock bound, no rollback handler and no test — and
it runs once per uvicorn worker, so four concurrent identical `DELETE`s on the same predicate at
every boot. The two copies will drift.

**Recommendation** — establish which implementation is meant to own the retention policy and delete
the other. Deleting the raw statement is the better direction: it puts a destructive write back in
the repository layer where its transaction scope and error reporting are explicit, and it makes the
service method — which already opens its own unit of work correctly — the single owner. Do not
simply wire the service into startup without checking: the service opens a session on the
*application* engine, which is the cold-start pool `docs/06-backend/architecture.md:419-425` says
startup must avoid.

### TXN-107 — The RQ submission client keeps the library's default Redis transport instead of the project's declared bound

**Severity** — MEDIUM — **already recorded as a hand-over, disclosed rather than reported as new**

**Zone** — "Exclusion mechanisms as one system: lifetime, holder, and what is not covered" (the
Redis-client-sharing item named in this phase's scope note)

**Observation** — the project has made a deliberate, documented choice to bound every Redis
transport: one pinned no-retry policy plus two configurable socket bounds, applied to both the
sync and async client factories. The third Redis client in the tree — the one the RQ queue is built
from — reads the same `RedisSettings` for host/port/db/password and none of the transport bounds.

**Evidence** — `src/mkobi/core/task_queue.py:41-49`:

```python
    config = get_config()
    redis_settings = config.redis
    connection = redis.Redis(
        host=redis_settings.host,
        port=redis_settings.port,
        db=redis_settings.db,
        password=redis_settings.password,
    )
    return rq.Queue(DEFAULT_QUEUE_NAME, connection=connection)
```

against `src/mkobi/core/redis_client.py:42-51`, which is the same constructor with the policy:

```python
    return redis.Redis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        password=config.redis.password,
        decode_responses=True,
        socket_timeout=config.redis.socket_timeout_seconds,
        socket_connect_timeout=config.redis.socket_connect_timeout_seconds,
        retry=_NO_RETRY,
    )
```

with the policy declared at `src/mkobi/core/redis_client.py:13-19`. The installed library is
redis 8.0.0, whose `redis.Redis` signature defaults are `socket_timeout=5`,
`socket_connect_timeout=5` and `retry=Retry(ExponentialWithJitterBackoff(base=0.01, cap=1),
retries=10)` (`redis/client.py:248-264`, `redis/_defaults.py:7-8` and `:37-39`) — the same
"eleven 5-second attempts, roughly 59 s per request" figure the project documents for the default it
removed. The submission is offloaded to a worker thread at `src/mkobi/core/task_queue.py:72`:

```python
        job = await asyncio.to_thread(queue.enqueue, func, *args, **kwargs)
```

**Consequence** — during a partial Redis fault — reachable at the `LPUSH` while the earlier
commands in the same request succeed — `enqueue_job` blocks for up to roughly a minute while
holding one thread of the default executor, and `POST /api/v1/upload/{dashboard_id}` does not
answer until it gives up. With four uvicorn workers and the default executor's small thread budget,
enough concurrent uploads exhaust the executor and stall every other `asyncio.to_thread` caller in
that process. The blast radius is bounded on two sides: a total Redis outage is caught earlier in
the same request by the rate limiter, which fails closed by default
(`Settings.rate_limiter_fail_closed = True`), and the wait itself is finite.

**Recommendation** — pass the two socket bounds and the shared `_NO_RETRY` to this client exactly as
`redis_client.py` does; no new setting is needed, both fields already exist on `RedisSettings`.
**This item is not new work.** `docs/SPEC.md`'s `3.33` row records it as a named hand-over:
"`rq_worker_wrapper.py`'s three `Redis.from_url` sites and `core/task_queue.py::get_rq_queue`
(both hand-overs, `HO-9`)". It is reported here so the concurrency consequence of that deferral is
on the record with a measured severity, and so the ID does not get minted twice. Do not close it
under this finding without also deciding `HO-9`'s other half.

### TXN-108 — The health API document describes a short-lived Redis client that the code deliberately does not create

**Severity** — LOW

**Zone** — "Schema and reference-data mutation, and the window each step opens" (documentation
half of the block's "deliberate asymmetry is not a defect; report it only where the code's own
documentation misstates it" rule)

**Observation** — `docs/05-health/health-api.md` states twice that the `/health/detailed` Redis
probe builds a short-lived client and closes it so a health poll cannot leak a connection pool. The
code uses the process-wide shared client and deliberately does not close it, with a comment
explaining why.

**Evidence** — `docs/05-health/health-api.md:136`:

```
| `redis`        | Sends a `PING` on a short-lived client from `get_async_redis_client()` | Non-critical (reported only) |
```

`docs/05-health/health-api.md:142`:

```
  the driver exception is logged server-side and is **not** echoed in the response. The client it built is **always closed** so a health poll cannot leak a connection pool.
```

against `src/mkobi/app.py:446-450`:

```
        # client is the process-wide shared one, so this check must NOT close it:
        # closing it here would evict the pooled connections every later request
        # depends on. It is closed once at lifespan teardown instead.
        try:
            await get_async_redis_client().ping()
```

**Consequence** — the code is right and the document is wrong. An operator or reviewer reasoning
from the document would conclude a health poll opens and discards a Redis pool per request, would
not look for the leak-avoidance rationale at `app.py:446-448`, and would be misled about whether
the shared client is safe to reuse. No runtime consequence today.

**Recommendation** — update `docs/05-health/health-api.md:136` and `:142` to describe what the code
does: the probe pings the process-wide shared client, does not close it, and the client is closed
once at lifespan teardown. This is a documentation edit only; no code change, and
`docs/SPEC.md`'s `3.34` row already records the correct behaviour, so the two documents can be
brought into line by copying that row's wording.

### TXN-109 — The architecture document still calls the UPLOADED orphan sweep boot-only, and it now runs on every reconciler tick

**Severity** — LOW

**Zone** — "Background and one-shot operation safety"

**Observation** — the reconciler's `UPLOADED` sweep was moved from process start onto the periodic
lease-guarded loop. `docs/03-processing/file-cleanup.md` was updated to match; the architecture
document's table and its explanatory paragraph were not.

**Evidence** — `docs/06-backend/architecture.md:367`:

```
| `mark_orphaned_uploaded_logs_failed()` | `UPLOADED` | **Boot only** — once per process start, lease-guarded | same setting |
```

`docs/06-backend/architecture.md:393-396`:

```
**The boot-time marker is boot-only, and stays that way.** It runs once per process start and is
not periodic. Its predicate is "`UPLOADED` and older than the horizon", so a queued orphan that
arrives *after* the boot sweep survives the restart untouched and is only reaped the next time the
horizon has elapsed **and** a later boot happens — in practice, up to a full horizon of quiet.
```

against `src/mkobi/workers/data_worker.py:1551-1553`, inside the per-tick loop body:

```python
            orphaned = await mark_orphaned_uploaded_logs_failed(
                timeout_minutes=timeout_minutes
            )
```

whose own comment at lines 1543-1546 records the move ("This ran only at boot before; a row
stranded by a process that died an hour after boot waited for the next restart"). The correct
statement is already in `docs/03-processing/file-cleanup.md:117` ("Runs | **On the periodic
reconciler loop**, on every tick").

**Consequence** — an operator reasoning about how long a stranded `uploaded` row survives reads
"up to a full horizon of quiet" plus a restart requirement, when the actual bound is one tick
(300 s by default). Two documents in the same repository state the same sweep's cadence
differently. No runtime consequence: the code is correct and the sweep is idempotent and
lease-guarded.

**Recommendation** — update `docs/06-backend/architecture.md:367` and `:393-396` to the periodic
cadence, matching `docs/03-processing/file-cleanup.md:117`, and drop the "stays that way"
construction. Documentation only.

### TXN-110 — The one start-up call site that does use the application engine contradicts the stated reason the starter has its own

**Severity** — LOW

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Observation** — `DatabaseStarter` builds a separate engine with a pinned small pool for start-up
work, and the architecture document gives the reason: start-up must not sit on the request pool
because a cold-start pool timeout is the worst moment for one. The admin-user bootstrap, which runs
inside that same start-up sequence, uses the application sessionmaker instead.

**Evidence** — `docs/06-backend/architecture.md:420-422`:

```
**require an AUTOCOMMIT connection**, and the starter must not share the
application engine: putting start-up reads on the request pool would expose them
to a pool timeout during cold start, the worst possible moment for one.
```

`src/mkobi/db/starter.py:510-513`, the call site that does share it:

```python
    async with get_async_sessionlocal() as session:
        user = await UserRepository().get_by_username(username, session)
        if user is None:
            await _create_admin_user(username, password, session)
```

**Consequence** — no runtime consequence today: the bootstrap needs one connection from a
`pool_size=10` pool per worker, and `pg_stat_activity` shows two `mkobi-app` connections on the
running dev database. The consequence is to the reader. A cold-start pool analysis built from the
document will omit one request-pool connection per worker per boot, and will not find the
rationale where it is looking, because the exception is not written down anywhere.

**Recommendation** — one of two directions, and the document is the cheaper one to get right:
either state the exception explicitly in `docs/06-backend/architecture.md` (the admin upsert is a
bounded, idempotent single-row write that is acceptable on the request pool), or move the call site
onto the starter engine it was given. Prefer the documentation change: it is the only start-up path
that returns an ORM object relying on the application's mapper configuration, and it is not worth
the coupling for one connection.

### TXN-111 — `core/base_repository.py` is a 204-line generic repository nothing uses, and its shape contradicts the live convention

**Severity** — LOW

**Zone** — "How the store is reached, by which process, and what each connection costs"

**Observation** — the repository that was meant to be the shared base is referenced by nothing in
`src/`, `tests/`, `alembic/` or `docs/`. Every live repository in `db/repositories/` takes `db` as a
per-method argument; `BaseRepository` takes it in `__init__` and holds it as instance state, so any
future adopter would carry a session on the repository object.

**Evidence** — `src/mkobi/core/base_repository.py:31-39`:

```python
    def __init__(self, model: type[T], db: AsyncSession) -> None:
        """Initialize repository.

        Args:
            model: SQLAlchemy model class.
            db: Async SQLAlchemy session.
        """
        self.model = model
        self.db = db
```

The file ends at line 204 with `exists()`, and a repository-wide search for `BaseRepository`
returns the definition site and nothing else. Compare the live convention at
`src/mkobi/db/repositories/dashboard_repo.py:118-120`:

```python
    async def create(
        self, db: AsyncSession, **kwargs: Any
    ) -> DashboardRead | None:
```

**Consequence** — no runtime consequence: nothing instantiates it. The cost is that the dead file
is the only place in the tree that shows a session held on a repository instance, which is the
shape this phase's scope note names as a hazard, and it is a template a future contributor will
copy. It also never commits, so an adopter who honoured the per-method `db` argument would end up
with the same missing-owner defect as TXN-102 with no signal.

**Recommendation** — establish why it exists before removing it. If the per-method `db` argument is
the intended convention — it is what all ten live repositories do, and what makes the request-scoped
unit of work pass through unchanged — then delete the file, because leaving a generic base that
contradicts the convention is worse than having none. If something is planned to adopt it, the
`__init__(model, db)` signature has to change first. A repository-wide search of `docs/` found no
mention of `BaseRepository` today, so nothing in the documentation has to go with it.

### TXN-112 — `FilterService`'s write methods have no transaction owner and no production caller

**Severity** — LOW

**Zone** — "Who opens the unit of work, and who decides it ends"

**Observation** — `FilterService.create_filter` performs a uniqueness pre-check, inserts, flushes and
returns without committing, exactly as `ProcessingConfigService.upsert` does (TXN-102). Its route
module is not mounted, so nothing in production reaches it; the only callers are
`tests/test_filters.py`. Its uniqueness check is also a read-then-create rather than a constraint
classification, the shape TXN-103's recommendation warns against.

**Evidence** — `src/mkobi/services/filter_service.py:68-80`, the head of the write path:

```python
        # Check name uniqueness
        existing = await self.filter_repo.get_by_name(name, db)
        if existing:
            logger.warning("Filter with name already exists: name=%s", name)
            raise ValueError(f"Filter with name '{name}' already exists")

        try:
            filter_obj = await self.filter_repo.create(
                db=db,
                name=name,
                type=type_,
                config=config,
            )
```

No `await db.commit()` appears anywhere in `src/mkobi/services/filter_service.py`. The router is
assembled in `src/mkobi/app.py:361-371` from eleven route modules and `routes.filters` is not
among them; `src/mkobi/api/routes/__init__.py` does not export it either.

**Consequence** — no runtime consequence today, because the path is unreachable. The risk is that
the service looks like a live writer: it is exported through `src/mkobi/interfaces/__init__.py`
alongside the mounted services, and it is the second instance of the TXN-102 pattern, which makes
the pattern look like a convention rather than an oversight.

**Recommendation** — decide the module's fate before it is re-mounted. If filters are coming back,
give `create_filter` a commit like every other service and let the unique index on `filters.name`
be the detector, as `LayoutService.create_layout` already does. If they are not, delete the write
methods and the unmounted `routes/filters.py` rather than leaving the next reader to infer intent
from a module nothing routes to. `tests/test_filters.py` covers the current shape and must be
brought along with whichever direction is chosen.

## Distribution

The findings fall on the **service layer's transaction ownership** above all: four of the twelve
concern a write method that performs a write and leaves the ending of the unit of work to nobody.
`src/mkobi/services/` carries three of them outright (`processing_config_service`, `auth_service`,
`filter_service`) and a fourth by adjacency (`dashboard_service` + its route's handler chain). The
remaining findings spread across the API layer's error classification, the startup path, the Redis
client factory, the retention statements, and three documentation files. Nothing lands in
`alembic/versions/`, `docker/`, or the frontend.

- Service layer (`services/`) — TXN-101, TXN-102, TXN-103 (partly), TXN-112
- API layer (`api/routes/`, `api/deps.py`) — TXN-103, TXN-101's contract half
- Startup / one-shot paths (`db/starter.py`, `db/repositories/`) — TXN-105, TXN-106, TXN-110
- Redis client factories (`core/`) — TXN-107, and TXN-111's dead base repository
- Documentation drift (`docs/`) — TXN-108, TXN-109, TXN-110

The single component carrying the most is `src/mkobi/services/`, and within it the **transaction
owner that a write method is supposed to be**: three separate services implement "commit my own
transaction" and one of the two that do not is fully live.

## Cross-Finding Analysis

Two findings share a cause and it is worth naming, because fixing the symptom in either place
leaves the other.

**The transaction owner was assigned per file rather than per convention.** TXN-102 and TXN-112 are
the same defect in two services — a write method that flushes and returns, with no commit, inside a
request unit of work that `get_db_dependency` explicitly declines to end. The codebase has the
right convention (`api/deps.py:126-129` states it; `UserService.delete_user`,
`DashboardService.update_dashboard`, `GraphService` and `LayoutService` all honour it) and nothing
enforces it, so a service author has to remember. TXN-101 is the same gap reached from the other
direction: there the owner exists but is nested inside another operation, so the boundary is
narrower than the invariant it is supposed to hold. Three of the four would be prevented by one
check — a test or a lint rule that asserts a service write method reaches a commit — which is why
they are grouped in the roadmap below rather than fixed as three unrelated bugs.

TXN-103 and TXN-104 share no cause and are independent. Every other finding is independent.

## Roadmap

1. **Give the orphaned write paths an owner** (TXN-102, TXN-112). Give `ProcessingConfigService.upsert`
   and `.delete` the service-level commit their siblings have, decide `FilterService`'s fate, and
   extend `tests/test_services_integration.py:611-619` to read the row back from a second session.
   Must be true before step 2: the tests assert durability across sessions, so they fail against the
   current code and pass only after the owner exists.
2. **Widen the approval boundary** (TXN-101). Remove `register_user`'s authority to commit on its
   caller's behalf without giving up the boundary `UserService.create_user` and the auth
   `POST /users/` path rely on. Must be true before step 3: step 3 adds a mid-sequence failure test
   that will fail twice while two commits remain.
3. **Close the unsynchronised read-then-write** (TXN-104). Serialise the admin count against the
   delete, and add the concurrent two-deletion test. Independent of steps 1–2; sequenced here only
   because it is the same class of "one row's decision is made from a snapshot nothing protects".
4. **Classify the constraint it already has** (TXN-103). Add the `IntegrityError` arm to
   `create_dashboard_endpoint` and copy `graphs.py`'s wording. Smallest item on the list; no
   ordering constraint.
5. **Widen the recreation exclusion** (TXN-105). Move `_apply_migrations` inside the per-name lock.
   `tests/test_starter.py:697-698` anchors the engine-creation order and will have to move with it.
   Test-tier only, so it can ship independently of everything above.
6. **Decide the dead paths, the Redis client, and the stale documents** (TXN-106, TXN-111, TXN-107,
   TXN-108, TXN-109, TXN-110). Two removals, one client construction change and three documentation
   edits, with no runtime coupling between them and no coupling to steps 1–5; TXN-107 additionally
   carries the `HO-9` hand-over, which is the only item on this list whose fix belongs to another
   phase's decision.

## Rollout Safety

Steps 1–4 change observable behaviour on four endpoints, so they are the only steps with a
rollout surface. Step 1 makes `PUT` and `DELETE /api/v1/processing-configs/{dashboard_id}` actually
persist; any consumer that has silently worked around the current no-op behaviour — a client that
re-sends the full config on every save, or a caller that assumed the write failed — will see a
different result, and the `DELETE` in particular starts destroying rows that survive today. Step 2
narrows the approval flow to one commit; the observable difference is that a failure between the
two former commits now leaves nothing behind instead of leaving an orphan account, so the failure
mode improves and no success path changes. Step 3 only rejects deletions that today succeed in a
concurrent pair. Step 4 changes `500` to `409` on duplicate dashboard names, which is the one change
a client could be matching on: `docs/06-backend/architecture.md` and `graphs.py` establish
`DUPLICATE_RESOURCE` as the house answer for a duplicate-name insert, so the risk is a client
special-casing `500` for this route, which nothing in the repository suggests.

Verify after step 1 by reading a written config back from a **fresh** session, not from the writing
one; that is the check that would have caught this. Verify step 2 by reading `registration_requests`
and `users` together after an induced mid-sequence failure. Revert by reverting the commit; none of
the four changes touches a migration, so no schema rollback is involved, and none of them writes
outside a transaction it now owns.

## Appendices

**Finding-ID namespace.** `TXN-` is assigned to this phase by
`.kilo/commands/audit/phases/03-audit-db-concurrency.md:129`, and the low range is already taken: a
prior audit run minted `TXN-001 … TXN-012`, referenced from `docs/SPEC.md:220` and from six task
files in `.ai/tasks/`. All twelve findings here therefore start at `TXN-101`; a repository-wide
search for `TXN-1[0-9][0-9]` returns nothing, so no ID in this report collides.

**Collisions with already-tracked work.** TXN-102 and TXN-112 do not appear in any `.ai/tasks/`
file. TXN-104 is adjacent to `B1-txn-001-transaction-ownership.yaml`, whose `out_of_scope` entry
at lines 516-518 deliberately left the last-admin guard unchanged on different grounds (it was
over-eager because promotions never persisted, not because it is unsynchronised) — the ruling did
not consider the concurrency window, so this is new. TXN-107 collides by subject with the `HO-9`
hand-over recorded in `docs/SPEC.md`'s `3.33` row (line 236) and is disclosed in the finding
rather than reported as new. TXN-106 overlaps with nothing tracked, but note that the tracked
remediation plan these findings are read against, `.ai/plans/03-db-concurrency-remediation.md`, is
named by `B1`, `B2`, `B3`, `B4`, `B5` and `B9` **and does not exist** — `.ai/plans/` holds only
`_code-context/`, `00-owner-rulings-2026-10-03.md`,
`16-chart-presentation-contract-remediation-execution.md`,
`16-phase16-residual-execution.md` and `17-authentication-implementation-execution.md`. A validator
cross-checking the accepted rulings against that plan cannot; the rulings themselves are readable
in the task files and were used instead.

**Runtime method.** The dev stack (`-p mkobi`) was already running and served as the instrument.
Three probes were run against the live `bidb` database from inside the `app` container via inline
`python -c`, covering two findings: the processing-config **upsert** durability probe and the
**delete** durability probe, both halves of TXN-102, and the duplicate dashboard-name probe for
TXN-103. `pg_stat_activity`, `pg_locks` and `SHOW max_connections` were read directly and
attributed one blank-`application_name` pooled connection to the starter engine (last query
`COMMIT`, age 1 d 10 h) and two `mkobi-app` connections to the request pool (last query `ROLLBACK`),
and confirmed `max_connections = 100`. All probe rows were deleted afterwards: the five
`audit-probe-*` dashboards were removed and `dashboards` returned to its pre-probe count, and the
`processing_configs` table was verified byte-identical because that write never committed.

**Zones checked with no findings.** Recorded for completeness; these were examined and produced
nothing to report.

- *Block 1* — no path constructs a second engine per operation: the engine and the session factory
  are each a module-global singleton built on first call (`db/session.py:29-30` and `:69-70`), so
  every session in a process comes from one `create_async_engine` at
  `db/session.py:47-59`, and the five engine-construction sites in the tree match
  `docs/06-backend/architecture.md:407-417` exactly. Nothing is found on the "one connection lost
  mid-operation" question: `db/session.py` is the only place the pool is touched outside a
  repository, and a returned connection is reset by the pool's `reset_on_return` rather than reused
  mid-transaction.
- *Block 2* — no path opens a second unit of work inside a request. `get_session()` is reached only
  from `deps.get_db_dependency`, the two health handlers, `file_processing`, the startup path, the
  CLI one-shot and the orphan-test mode; none of them runs inside a live request transaction. There
  is no `session.begin()` nested inside an open transaction: the only two `async with
  session.begin()` sites in production code are `workers/data_worker.py:1013`, which opens the
  worker's own transaction, and `services/processing_log_service.py:256`, which opens a fresh
  session — and the latter is the unreachable path reported as TXN-106.
- *Block 3* — the aggregate rebuild is all-or-nothing as documented: the advisory lock is taken as
  the first statement inside the worker's own `session.begin()` block
  (`data_worker.py:1013-1023`, matching `docs/06-backend/architecture.md:602-606`), so it is
  released before the failure-compensation handler writes the `FAILED` row on a fresh session, and
  `_run_with_transaction` commits once, so a failed rebuild leaves the previous aggregates intact.
  The two-commit split in `DataService._execute_upload` → `process_upload_with_session` is
  deliberate: the row is committed before the file is moved and before the enqueue, and the
  compensation for a failed enqueue exists and does remove the moved file
  (`src/mkobi/services/file_processing.py:259-273`).
- *Block 4* — no swallowed database error leaves a caller's transaction aborted. Every
  `except SQLAlchemyError` in the repository and service layers logs and re-raises; the only places
  that absorb an error are the lock managers (`advisory_lock`, `migration_lock`,
  `test_database_lock`), each of which uses a session-scoped lock on a connection nothing else uses.
  No `SAVEPOINT` is used anywhere, so the "aborted session reused" failure mode does not arise.
  The one route whose `except` arms are narrower than its sibling's is
  `api/routes/dashboards_graphs.py:108-113`, and its gap is inert for the inverse reason: the
  `ValueError` that arm does not roll back cannot be raised by the only call in its `try` block,
  because `graph_repo.create` (`db/repositories/graph_repo.py:132-141`) catches only
  `SQLAlchemyError` and re-raises — and `IntegrityError`, the error that actually reaches that
  handler, has its own rollback arm at line 116.
- *Block 5* — the constraints that carry invariants classify their violations correctly and
  consistently everywhere else: `layouts.name` (`api/routes/layouts.py:114-127`), `graphs
  (dashboard_id, name)` (`api/routes/graphs.py:135-147` and `api/routes/dashboards_graphs.py:116-127`)
  all map a flush-time `IntegrityError` to `409 DUPLICATE_RESOURCE` with an explicit rollback;
  `dashboard_access` is a conflict-tolerant upsert (`db/repositories/access_repo.py:46-49`), so a
  re-grant is defined behaviour rather than an error. Deletes cascade correctly for
  `dashboard_access`, `graphs`, `aggregated_data` and `processing_configs` (`ON DELETE CASCADE`) and
  `dashboards.created_by` (`ON DELETE SET NULL`); `DashboardRepository.delete` relies on the ORM's
  `delete-orphan` cascades for the same rows. No live writer bypasses a constraint with a
  conflict-tolerant write while a sibling writer uses a plain insert, apart from the
  read-then-create pattern flagged inside TXN-112.
- *Block 6* — `save_aggregates` receives the recomputed rows as an argument rather than reading the
  rows it is about to delete (`src/mkobi/data/storage/manager.py:185-190`, `:247-254`), and the
  `clear_old` deletes share the advisory-locked transaction with the inserts, so a rebuild that fails
  part-way rolls the delete back rather than leaving the derived value absent. `grant_access` is a
  conflict-tolerant upsert, so it cannot destroy a concurrent grant's work. **No operation in the
  tree takes a row-level lock at all** — there is no `with_for_update()` anywhere in `src/`, and the
  legacy `db/session.py::get_db()` dependency is a plain session yielder, not a locking one. TXN-104
  is reported as the finding that absence produces, not as an omission.
- *Block 7* — four exclusion mechanisms, all with a measured lifetime and none held across `await`
  points it should not be: `pg_advisory_xact_lock` on the dashboard rebuild (acquired at
  `workers/data_worker.py:1021-1023`, released by the transaction's end, `lock_timeout_ms` applied
  via `set_config(..., true)` in the same transaction), `pg_try_advisory_lock(42)` on the Alembic run
  (session-scoped, released in `alembic/env.py:152-169`, and only reachable when `AUTO_MIGRATE` is
  set, which no compose file does), the Redis `ReconcilerLease` (`SET NX EX` at
  `core/reconciler_lease.py:37` and `:136-139`, 90 s TTL by default, renewed after every
  `max(1.0, ttl/3)` slice of the wait — `workers/data_worker.py:1418-1423` — and released before the
  task returns; it fails open by design), and the per-name recreate lock. No `asyncio.Lock`,
  `threading.Lock` or `Semaphore` exists in `src/`, so the lock-ordering class is empty. Every
  Redis-touching request path shares one process-wide client except the RQ client, which is TXN-107.
- *Block 8* — both reconciler sweeps are monotone, idempotent `UPDATE`s and are therefore safe to
  run on every replica; the lease elects a single holder but fails open deliberately, which is
  sound for this workload and is documented as such at `architecture.md:398`. De-duplication is a
  stored status value in both cases and is correct, because the sweep predicates are disjoint by
  status. The lease is a single-key `SET NX EX` on the one Redis instance, which is correct for
  the single-Redis topology; its behaviour under a Redis failover is a topology question, and the
  resulting double sweep is harmless by construction. `file_cleanup.py` documents and implements a
  three-way outcome so that concurrent sweepers' counts sum to the files removed exactly once.
- *Block 9* — the migration chain takes no application-visible locks beyond what
  `docs/09-database/migration-index-policy.md` already records: `CREATE INDEX IF NOT EXISTS` runs
  inside the migration transaction and takes a write lock on the table, which the policy document
  names explicitly. `AUTO_MIGRATE` is `"false"` in every compose file, so migrations run from the
  dedicated `migrate` service before `app` starts and no window is open to a live writer. The only
  unmigrated destructive step is the test-database recreate, reported as TXN-105.

**Limits on this report.** Three defects could not be reproduced under genuine concurrency in this
environment, and each is reported from static proof of the boundary shape rather than from an
observed interleaving: TXN-101 (needs a failure induced between two commits), TXN-104 (needs two
concurrent admin deletions) and TXN-105 (needs two concurrent `--recreate-test-db` runs). The
boundaries themselves were each read directly at the cited lines, so the proofs do not depend on the
interleaving being reproducible here. TXN-106's raw `DELETE` running four times concurrently at boot
is reasoned from `--workers 4` in `docker/Dockerfile:242` plus `app.py`'s `lifespan` being per
process; it was not observed, and PostgreSQL makes concurrent identical `DELETE`s on one predicate
safe regardless.

**Concurrent modification.** The working tree is being modified by other work while this report was
written (branch `claude/phase-05-data-pipeline-remediation-exec`, HEAD `8a317e9`); `git status`
carries uncommitted modifications to `src/mkobi/data/storage/manager.py`,
`src/mkobi/services/data_service.py`, `src/mkobi/interfaces/service_interfaces.py`,
`src/mkobi/api/routes/data.py`, `src/mkobi/models/data.py`,
`frontend/src/shared/types/api.types.ts` and three test modules. Two of those files **are** named
in this report — `data/storage/manager.py` in the Block 6 appendix and `services/data_service.py`
in the Block 3 appendix — and both references are structural rather than line-anchored
(`save_aggregates`'s signature and its `clear_old` delete; `_execute_upload`'s existence), so
neither is sensitive to a line shift; both were read from the current on-disk state. No other cited
file is in motion. Every line-anchored citation in this report was opened and read within minutes of
the report being written, and the four library-version figures in TXN-107 were read out of the
installed `.venv`, not from documentation.