---
phase: 01-process-architecture
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 4
  LOW: 2
---

# Phase 01 — Findings

## Summary

The dev tier was brought up (`mkobi` project: `db`, `redis`, `app`, `rq-worker`, `frontend`) and driven
end to end — an authenticated CSV upload was pushed through `POST /api/v1/upload/{dashboard_id}` and the
resulting work record, Redis keyspace, RQ worker state and process logs were read back; the app container
was restarted while a client polled `/health` to measure the startup window. The single most consequential
finding is that the deployed `rq-worker` container has never received a byte of work: every submission goes
to an `asyncio.Queue` inside the request-serving process, so the component that exists to make processing
durable and horizontally scalable is inert, and the only reconciler for abandoned work is the next process
start. Immediately behind it, a background job that fails leaves its record permanently reading
"awaiting processing", because the code that would mark it failed is unreachable behind a `raise`.

## Findings

### TOPO-001 — A failed background job is recorded as still awaiting processing until the process restarts

**Severity** — HIGH

**Zone** — Termination: what an in-flight operation leaves behind

**Observation** — `mkobi/workers/data_worker.py:582-620` is the production branch of
`_process_csv_file_async` — the only branch a real upload takes. Its `except` handler ends with
`raise  # Re-raise inside transaction block triggers rollback` (line 603), which propagates out of both
`async with` blocks and out of the function. The sixteen lines that follow (605-620) — the independent
`_update_processing_log_status(..., FAILED, ...)` call — are therefore unreachable on both paths: on
success the function has already returned at line 587, and on failure the exception has already escaped.
The comment immediately above them (`# Use independent session for status update OUTSIDE the rolled-back
transaction. / # This ensures the FAILED status persists even when main transaction rolls back.`) states
the opposite of what the code does. The `PROCESSING` write made at line 390-396 is inside the same
transaction, so it is rolled back with everything else and the row returns to its previous value. The
only component that ever moves such a row on is `mark_orphaned_uploaded_logs_failed()`
(`app.py:116`), which runs once, inside the lifespan startup.

**Evidence** — Reproduced live. A 3-row CSV was uploaded to dashboard `a5214e7a-…` at 09:52:41 UTC
(HTTP 201, `task_id=9afde10a-228f-4d50-a07b-68a0bade794d`). The job failed with
`polars.exceptions.ColumnNotFoundError: "TVR" not found`; `app` logs show
`Processing log updated: …, status=processing` at 09:52:42 and no subsequent status write, and
`docker logs … | Select-String "status=failed"` over the following twelve minutes returns nothing.
`psql -c "select id, status, error_code from processing_logs"` returns the row as
`status=uploaded, error_code=NULL, message='File uploaded successfully, awaiting processing. mode=overwrite'`.
`/app/data/tmp_uploads/` is empty — the file the row still points at was deleted by the failure handler at
`data_worker.py:594-602`. Static proof of unreachability: `data_worker.py:603` (`raise`) precedes
`data_worker.py:605-620`, and no `return` exists between them.

**Consequence** — A user who uploads a file the pipeline cannot process is told, and continues to be told
by `GET /api/v1/upload/status/{task_id}`, that the file is "awaiting processing", while the file itself no
longer exists. The row stays in that state for as long as the process lives; it is only corrected the next
time the app starts, and only if more than one minute has passed. The operator sees a clean log line
("Processing failed: …") and a row that contradicts it. Nothing in the running system distinguishes
"still working" from "died an hour ago".

**Recommendation** — Make the compensating write reachable: move the FAILED `_update_processing_log_status`
call into the `except` handler, after the `async with session.begin()` block has exited (i.e. let the
exception escape the transaction, then write on a fresh session), or drop the bare `raise` and perform the
write from a `finally` that runs outside the transaction. Delete the now-misleading comment. Note the
remediation blocker: every shipped test that drives this function passes `db_session=async_db_session`
(`tests/test_upload_api.py:712`, `tests/test_e2e_upload.py:157/244/320`,
`tests/test_filter_values_consistency.py:178/275/298`), which selects the *test-mode* branch at
`data_worker.py:552-581` where the FAILED write does execute. The suite therefore cannot fail on this
defect; a fix needs a test that drives the branch with `db_session=None`.

### TOPO-002 — The deployed RQ worker has never received work; every submission goes to the serving process's memory

**Severity** — MEDIUM

**Zone** — The periodic loop and the work-submission mechanisms inside the request-serving process

**Observation** — Two work-submission mechanisms exist. `TaskQueue` (`core/task_queue.py`) is an
`asyncio.Queue` plus three in-process dicts, instantiated as the module-level singleton `default_queue`
(line 159). The Redis/RQ queue is constructed in exactly one place, `rq_worker_wrapper.py:104`, in a
function nothing calls. There is no `rq.Queue(...).enqueue(...)` call anywhere under `src/`: the only
matches for `enqueue(` are `TaskQueue.enqueue` and the docstring at `task_queue.py:66`. The only
submission call site in the product is `enqueue_job(process_csv_background, …)` at
`services/file_processing.py:366`, which routes to `default_queue.enqueue` (`task_queue.py:181`).
`TaskQueue.enqueue_with_worker` — the method documented as "the integration point for background worker
migration" — has no caller. Yet the `rq-worker` service is declared in both
`docker/docker-compose.yml:169-221` and `docker/docker-compose.override.yml:118-152`, holds the same
`app_data` volume as `app` (override comment: "RQ worker needs write access to tmp_uploads for file
processing"), and carries a healthcheck. `docker-compose.override.yml:123` launches it with the bare
`/app/.venv/bin/rqworker` CLI, so `mkobi.rq_worker_wrapper.start_rq_worker` — the module that retries the
Redis connection with backoff and whose stated purpose is to survive Redis being unavailable at container
start — is a declared entry surface that is never executed.

**Evidence** — Static: `Select-String` over `src/` for `Queue\(|enqueue\(|\.enqueue` returns seven matches,
none of which is an RQ enqueue. Runtime, after the live upload described in TOPO-001: `app` logs show
`Task enqueued: task_id=6301ccb5-…` (`module: task_queue`, `function: enqueue`) followed one second later by
`Task failed: task_id=6301ccb5-…` from the same module — the job was consumed by the in-process loop
(`app.py:131-141`), not by the worker. In the same window `redis-cli LLEN rq:queue:default` returns `0` and
`redis-cli EXISTS rq:queue:default` returns `0` — the key was never even created. `rq:worker:856abb34…`
hashes to `state=idle`, `queues=default`, and `docker logs mkobi-rq-worker-1` shows `*** Listening on
default...` at 08:40:00 followed only by periodic `cleaning registries for queue: default` lines, with no
job line in 1h07m of uptime. The full Redis keyspace at that moment was
`rq:workers`, `rq:workers:default`, `rq:worker:856abb34…`, `login:127.0.0.1`, `upload:13a1f341-…`.

**Consequence** — A container, a Redis service, a mounted volume, a healthcheck and a documented retry
entry point exist solely to consume a queue nothing writes to. The declared benefit of the Redis path —
durability across restart and horizontal scale (`core/task_queue.py:4`, `:23`, `:60-61`) — is absent: work
is only as durable as the process that accepted it. The compose file and
`docker/.env.production`/deployment documentation describe a Redis-backed worker topology that does not
exist in the running system, so an operator reading the deployment has no accurate picture of where
processing work runs.

**Recommendation** — Pick one and make the deployment match it. Either (a) point the upload path at
`rq.Queue(...).enqueue(process_csv_background_sync, …)` — the sync wrapper already exists at
`data_worker.py:871` and the RQ-compatible signature is described at `task_queue.py:69` — and change
`rq-worker`'s command to `python -m mkobi.rq_worker_wrapper` so the retry entry point is the one that
actually runs, or (b) delete the `rq-worker` service, the Redis queue wiring and
`rq_worker_wrapper.py`, and document that processing is in-process. Option (a) is the smaller change and
is what the code was already shaped for; it also removes the in-memory loss described in TOPO-003.

### TOPO-003 — Accepted work and its outcome are held only in the serving process, and the shutdown report that would announce the loss never runs

**Severity** — MEDIUM

**Zone** — Shared state across processes, and what is per-process by construction

**Observation** — `TaskQueue` keeps the payload queue (`_queue`), the per-task status map (`_statuses`),
the result map (`_results`) and the error map (`_errors`) in process memory, and `default_queue`
(`task_queue.py:159`) is a module-level singleton. `TaskQueue.enqueue` mints its own identifier —
`task_id = str(uuid.uuid4())` at `task_queue.py:44` — which is *not* the `processing_logs` id the job
actually updates. The single call site discards it: `services/file_processing.py:366` is a bare
`await enqueue_job(...)` with no assignment, and `enqueue_job` (`task_queue.py:181`) returns the in-memory
id. `get_status`, `get_result` and `get_error` (`task_queue.py:107`, `:122`, `:133`) therefore have no
reachable caller — the only `get_status`/`get_result` symbols in the tree are the unrelated HTTP handlers
`upload.py:260` and `upload.py:317`, which read the database. `TaskQueue.shutdown()` (line 144), whose
docstring says "Called during application shutdown to warn about tasks that will be lost", has no caller:
the lifespan's `finally` block (`app.py:156-180`) cancels the two background tasks, disposes the engine and
shuts the starter down, and never touches the queue.

**Evidence** — Static: `Select-String` over `src/` and `tests/` for `get_status|get_result|get_error|\.shutdown\(\)|TaskQueue`
returns no caller of the three accessors and no caller of `TaskQueue.shutdown`; the two `.shutdown()` hits
are `starter.shutdown()` at `app.py:180` and an unrelated symbol at `exceptions.py`. Runtime: a full
shutdown was observed at 09:02:29 UTC when the dev reloader picked up a file change. The complete log
sequence is `Shutting down application...` → `Stale processing cleanup task cancelled` → `Task queue
worker cancelled` → `Database engine disposed cleanly` → `Database engines disposed`. A `Select-String` for
`TaskQueue shutting down` over the container's entire log history returns nothing.

**Consequence** — Two of the three things a caller could want to know about submitted work — its in-process
status and its outcome — are unreachable by construction, and the third (the database row) is wrong after a
failure per TOPO-001. At termination, the queue worker task is cancelled mid-`await` inside
`TaskQueue.process_next` with no drain and no compensating action; anything still sitting in `_queue` is
discarded with the process and the operator is told nothing, because the one function written to say so is
never called. The declared loss and the actual loss do not match, and the actual loss is invisible.

**Recommendation** — Call `await get_task_queue().shutdown()` from the lifespan `finally` block, before the
worker task is cancelled, so the declared warning is actually emitted; that is a two-line change and closes
the documentation/behaviour gap on its own. Separately, stop pretending the in-memory status maps are a
result channel: if work is to move to RQ (TOPO-002 option a) the three accessors and the three dicts go
away with them. If it is to stay in-process, `enqueue_processing_job` should at least propagate the
`task_id` it already receives from `enqueue_job` to the caller instead of discarding it.

### TOPO-004 — The only path that drops and recreates the whole store takes no guard, and the one guard in the system is entered after the store is gone

**Severity** — HIGH

**Zone** — The schema and reference-data bootstrap gate, and whether any of its steps can destroy a schema

**Observation** — Four paths can mutate the schema or reference data. (1) The `migrate` one-shot service
(`docker-compose.yml:55-80`, `command: ["alembic","upgrade","head"]`, `restart: "no"`), ordered ahead of
`app` by `condition: service_completed_successfully`. (2) `AUTO_MIGRATE` / `auto_migrate` inside the
application process — `db/starter.py:153-154` calls `_apply_migrations` — set to `"false"` in every compose
tier. (3) The ad-hoc CLI `python -m mkobi.db.starter --recreate-test-db` (`starter.py:423-430`). (4) The
in-process `DatabaseStarter.startup()`, which reaches `recreate_test_database()` whenever
`env == TEST or config.recreate_test_db` (`starter.py:184-185`). `recreate_test_database` issues
`SELECT pg_terminate_backend(pid) … WHERE datname = :db_name`, then `DROP DATABASE IF EXISTS` and
`CREATE DATABASE` (lines 240-256), as `mkobi_app`… no — as the configured admin role, on a connection
opened with `isolation_level="AUTOCOMMIT"`. It takes **no** lock of any kind. The project's only concurrency
guard is `pg_advisory_lock(42)` in `alembic/env.py:113-127`, and that is reached only by the
`command.upgrade` call at `starter.py:310` — which `recreate_test_database` invokes at line 290, *after* the
database has already been dropped. The guard is a plain blocking `pg_advisory_lock` with no timeout and no
`try_lock`/`skip` variant, and its docstring's claim that it "prevent[s] concurrent migrations in
multi-instance deployments" covers only the migration step, not the drop.

**Evidence** — Static: `starter.py:184-185` (the condition), `starter.py:240-256` (terminate + drop + create,
no lock), `starter.py:290` (`_apply_migrations`, the first and only lock acquisition on this path),
`alembic/env.py:58` and `:113-127` (the advisory lock and its unbounded blocking acquire). The
`test-app` service is configured with both triggers: `docker-compose.test.yml:93` (`ENV: test`) and
`:147` (`RECREATE_TEST_DB: "true"`). The test harness is the only current consumer of the destructive
method: `tests/conftest.py:433` calls the same `recreate_test_database()` from a session-scoped fixture, so
two independent, uncoordinated creators of `bidb_test` exist in the same tier. The application's own copy of
this path is never executed by the harness: `tests/conftest.py:559` builds the client with
`httpx.ASGITransport(app=app)`, which does not emit ASGI lifespan events, so `DatabaseStarter.startup()`
never runs in a single test.

**Consequence** — The store is one setting away from being destroyed by every process that starts. In the
test tier it is already armed: any run of the app image's own `CMD` (`docker/Dockerfile:151`) or any
lifespan-driven run drops `bidb_test` and `pg_terminate_backend`s every connection to it, including the
engine pool that `conftest.py:433` just created. In the production tier the same flag would be acted on by
each of the four uvicorn workers described in TOPO-005, in parallel and unguarded, with no advisory lock
between them. The once-only guarantee for the destructive step comes from neither declared ordering nor
the guard — it comes only from the fact that no deployment currently sets the flag on a tier that runs
the lifespan.

**Recommendation** — Put the drop under the same lock the migration already uses, and make the lock
bounded: acquire `pg_advisory_lock(42)` on the admin connection *before* `pg_terminate_backend` and release
it after `_apply_migrations(test_url)` returns, mirroring `alembic/env.py`. Better, make
`recreate_test_database` refuse to run unless the target database name matches an explicit test pattern
(`bidb_test` or `bidb_test_<worker>`) rather than trusting a boolean that can be set on any tier, and drop
`recreate_test_db` from `DatabaseStarterConfig` in favour of that check. If the intent is for the
harness to be the only creator, remove the `RECREATE_TEST_DB` setting from
`docker-compose.test.yml:147` and assert in `conftest` that the database it is about to use is one it
created.

### TOPO-005 — Production starts four uvicorn workers from one image entry, and every one of them runs the boot preconditions and its own copy of the periodic loop

**Severity** — MEDIUM

**Zone** — Component inventory, and the topology that differs between deployment tiers

**Observation** — The production image's `CMD` is
`["uvicorn","src.mkobi.main:app","--host","0.0.0.0","--port","8000","--workers","4"]`
(`docker/Dockerfile:179`). The dev tier replaces it with a single reloading process and no `--workers`
(`docker-compose.override.yml:109`), so the running topology the project exercises is 1 process and the
shipped topology is 4. Each worker independently executes the whole `lifespan`: `starter.startup()`
(`app.py:112`, which runs `ensure_admin_user` with a bcrypt hash, `cleanup_old_logs`, and
`cleanup_stale_temp_files` against the shared `app_data` volume), `mark_orphaned_uploaded_logs_failed()`
(`app.py:116`), and `start_stale_processing_cleanup_task` (`app.py:120-125`) — a `while True` loop with a
300-second cadence, started unconditionally, with no election, lease or leader check of any kind. The loop's
only evidence of running is the line it writes for itself
(`data_worker.py:917-921` at start, `:287-292` only when it marks rows). No counter, timestamp, health
field or metric exposes it. The in-process work queue is likewise per-worker
(`core/task_queue.py:159`), so the queue that exists is 4 independent queues; an upload is handled by
whichever worker the load balancer picks, and the load is not shared.

**Evidence** — Static: `docker/Dockerfile:179` (`--workers 4`) against
`docker/docker-compose.override.yml:109` (no `--workers`, `--reload`); `app.py:120-125` creating the
cleanup task with no guard; `grep` for any leader-election or Redis-lock primitive in `app.py` /
`data_worker.py` returns nothing. Runtime, dev tier (the only tier running): `docker inspect
mkobi-app-1 --format '{{json .Config.Cmd}}'` returns
`["uvicorn","src.mkobi.main:app","--host","0.0.0.0","--port","8000","--reload","--reload-exclude","/app/tests/"]`
— one process. Its log shows the loop starting exactly once:
`Started stale processing cleanup task (interval=300s, timeout=30m)` at 08:40:25, with no further output
from it in the following 1h20m, because `cleanup_stale_processing_logs` logs only when `count > 0`.

**Consequence** — Horizontal scale multiplies the sweeps: at four replicas the stale-log `UPDATE`,
the `DELETE` of retained logs, the admin bcrypt hash and the temp-file sweep all run four times per
interval instead of once, and `mark_orphaned_uploaded_logs_failed` — a bulk `UPDATE` with a one-minute
cutoff — runs four times at every restart of any single worker, including a restart of one worker while
another still has uploads queued in its own memory (those rows are still `UPLOADED` and would be flipped to
`FAILED` by a sibling that is not the process holding them). Because the loop emits nothing when it has
nothing to do, an operator cannot tell from outside the process whether it is running at all, and a loop
that has died is indistinguishable from a loop with no work.

**Recommendation** — Keep the single-worker default and add `--workers` as a compose-level override with
the loop made safe for N replicas: gate `start_stale_processing_cleanup_task` behind a Redis lease
(`SET key value NX EX <ttl>` renewed by the loop, with only the holder running the sweep) — the Redis
dependency is already a hard requirement of the request path, so this adds no new failure mode. Add one
health-visible signal for the sweep (a last-success timestamp in `/health/detailed`, which already has a
`components` map and currently reports only `database` and `static_files`) so a dead loop is
distinguishable from an idle one. If the four workers are not wanted at all, drop `--workers 4` from
`docker/Dockerfile:179` — the dev tier already runs one process, and that is the topology the suite covers.

### TOPO-006 — The admin approval route sequences four cross-store effects, one of them non-transactional, with a rollback that cannot undo it

**Severity** — MEDIUM

**Zone** — Entry-layer discipline and dependency direction

**Observation** — `approve_registration_request_admin_endpoint`
(`api/routes/admin.py:~280-345`) is the request-entry module, and it owns the whole approval rule. In one
handler body it (1) calls `auth_service._generate_temp_password()` — a private method of the service,
reached from the transport; (2) creates the user via `auth_service.create_user`; (3) sets
`force_password_change` via `auth_service.user_repo.update`; (4) writes the temporary password to **Redis**
via `temp_password_store.store` (line 321), which is an immediate, non-transactional `SETEX`; (5) updates
the registration request's status; and only then (6) calls `await db.commit()` at line 330. The `except`
handler calls `await db.rollback()`, which reverses (2), (3) and (5) but not (4). The transport module
also owns the commit boundary directly in ten places — `admin.py:330`, `admin.py:386`,
`dashboards_access.py:205`, `dashboards_crud.py:139`, `dashboards_filters.py:64`,
`dashboards_filters.py:106`, `dashboards_graphs.py:98`, `graphs.py:122`, `graphs.py:372`,
`graphs.py:467` — and one rollback (`graphs.py:383`), with no corresponding `rollback` in
`dashboards_filters.py:68-79`. `api/deps.py:112-113` runs `db.execute(select(User))` in the
dependency-injection layer.

**Evidence** — Static: the call sequence and the commit/rollback placement read directly from
`api/routes/admin.py:305-345`; the ten `db.commit()` call sites listed above are the complete set returned
by `Select-String -Pattern "db\.execute|session\.execute|text\(|commit\(|\.scalars\("` over
`src/mkobi/api/routes/*.py` and `src/mkobi/api/deps.py`. `Select-String` for
`from mkobi.api|import mkobi.api` across `core/`, `services/`, `db/`, `data/loaders/`, `workers/`,
`utils/`, `models/` and `db/repositories/` returns **no** matches, so the dependency direction itself is
clean — the violation is entirely in what the transport does, not in what it imports.

**Consequence** — If step (4) succeeds and step (5) or the commit fails, the handler rolls back the
database work, returns HTTP 500, and leaves a live retrieval token in Redis holding a temporary password
for a user that no longer exists. The client receives no `user_id` and no `retrieval_token`, so the token is
unreachable; the token is the only copy of the credential, and its TTL is
`temp_password_ttl_seconds`, 24 hours by default (`config.py:369`). The invariant "an approval creates a
user, forces a password change and mints exactly one usable token, or creates nothing" exists nowhere
except as the statement order of a route handler, which is exactly the kind of rule that breaks silently
when someone reorders two lines.

**Recommendation** — Move the whole sequence into a service method —
`AuthService.approve_registration_request(request_id, admin_id, db)` — that owns the ordering and exposes
`_generate_temp_password` only internally; the route then parses, delegates and responds. Put the Redis
write *after* the database commit and make it the last step, so a failure before it leaves no token, and
delete the token if the route's response construction fails. Move the `db.commit()`/`db.rollback()` calls
out of the ten route bodies and into the service methods that own the corresponding unit of work, so the
transaction boundary is decided in one layer. This is a mechanical move with no schema change; the
approval endpoint's request and response shapes are unaffected.

### TOPO-007 — The migration entry surface is outside both automated quality gates

**Severity** — LOW

**Zone** — Entry surfaces: what is constructed when a surface loads, and what is deferred

**Observation** — The entry surfaces are: `uvicorn src.mkobi.main:app` (request-serving;
`docker/Dockerfile:127`, `:179`, `docker-compose.override.yml:109`), `alembic upgrade head` (schema
mutation, one-shot; `docker-compose.yml:60`, `Makefile.ps1:256`), `python -m mkobi.db.starter
--recreate-test-db` (one-shot, `starter.py:423-430`), and the `rqworker` CLI (work-consuming;
`docker-compose.yml:174`). `alembic/env.py` is the load-time surface of the second of these: it imports
every ORM model, resolves the database URL from three sources, and acquires and releases the project's only
concurrency lock. Both automated gates exclude it. `Makefile.ps1:222` runs `ruff check src/ tests/` and
`Makefile.ps1:230` runs `mypy src/`; `alembic/` is outside `src/`, and `pyproject.toml:169` additionally
sets `exclude = ["alembic/"]` for mypy. The `check` aggregate (`Makefile.ps1:241-249`) inherits both
omissions. A secondary load-time effect sits on every surface: `Settings.__init__` calls
`_ensure_upload_dir()` (`config.py:570`, `:584-587`), which creates a directory on the filesystem during
module import, and `SecretsFileSource.__call__` (`config.py:60-83`) enumerates the whole process
environment and stats every `*_FILE` variable — so importing `mkobi.config` touches both the filesystem
and the environment before anything has been asked of the process.

**Evidence** — Static: the two gate invocations at `Makefile.ps1:222` and `:230` read against
`pyproject.toml:169`; `alembic/env.py` appears in neither path. Runtime confirmation that the load-time
filesystem/env scan fires on a surface that has nothing to do with uploads: `docker logs mkobi-app-1`
contains, at the head of every process start, the unformatted line
`Failed to read secret file .: [Errno 21] Is a directory: '.'` — emitted before `setup_logging()` runs
(`app.py:39-43`), so it bypasses the structured log format. It comes from
`LOGGING__LOG_FILE=` (set to the empty string at `docker-compose.override.yml:82`), which the `_FILE`
suffix heuristic in `config.py:65-66` misreads as a Docker-secrets pointer to `LOGGING__LOG`, then tries
to `read_text()` on `Path("")` → `Path(".")`.

**Consequence** — The once-only guard for the whole schema-mutation surface (TOPO-004) is implemented
entirely in a file no lint or type check reaches, and a typo in it fails at container start with a
traceback from Alembic rather than at review time. The load-time side effect is currently a one-line
warning on every boot of every surface, including `alembic upgrade head`, which never uploads anything —
noise that trains operators to ignore the startup preamble where the real preconditions are logged.

**Recommendation** — Add `alembic/env.py` to both gates: `ruff check src/ tests/ alembic/` and
`mypy src/ alembic/env.py` (keeping the mypy `exclude` off that one file, since it is hand-written and
small). Narrow the secrets heuristic from a bare `_FILE` suffix to an explicit allowlist or a
`__`-delimited `*_FILE` pattern, and skip empty values, which removes the spurious warning from every
surface. The `_ensure_upload_dir()` call in `Settings.__init__` is defensible for a single-process
deployment but should move into the lifespan if the process ever runs more than one worker
(TOPO-005), since four workers racing to `mkdir` the same path is a latent failure on a read-only root.

### TOPO-008 — Nothing in the deployment gates traffic on the application's boot preconditions

**Severity** — LOW

**Zone** — Startup order, and the interval in which the process answers before it can serve

**Observation** — Inside the process the ordering is correct and fail-fast: `lifespan` awaits
`starter.startup()` (`app.py:112`) before `yield`, and `DatabaseStarter.startup` raises
`DatabaseNotFoundError` on an unreachable database (`starter.py:94`, `:109`) and `SchemaNotFoundError`
on a missing revision (`starter.py:161-164`), both of which propagate out of the lifespan and abort the
boot. Nothing serves before the preconditions complete — uvicorn does not accept requests until the
lifespan startup returns. The gap is between the process and its caller. `nginx` declares
`depends_on: - app` in short syntax (`docker-compose.yml:229-230`), which waits only for the app
*container to start*, not for it to be ready. The dev tier sets `healthcheck: disable: true`
(`docker-compose.override.yml:110-112`), so the dev deployment has no readiness signal at all. The
production healthcheck (`docker-compose.yml:135-140`) uses `interval: 30s` with
`start_period: 40s`, so for the first 40 seconds Docker reports the container healthy without a single
successful probe result.

**Evidence** — Runtime, dev tier: `docker restart mkobi-app-1` followed by a client polling
`http://127.0.0.1:8010/health` every ~150 ms recorded 224 consecutive refusals before the first answer —
`FIRST_ANSWER_MS=40258 status=200 body={"status":"healthy","database":"connected"}`. The app's own log
attributes almost none of that window to its preconditions: `Initializing application...` at 09:56:20.046
and `Application initialized successfully` at 09:56:21.423 — **1.38 seconds** of actual precondition work;
the remaining ~39 s is uvicorn and the dev-tier reloader. So the preconditions are fast, and the window a
caller experiences is an order of magnitude larger, which is exactly the kind of gap a readiness gate
exists to close.

**Consequence** — During any restart or rollout of the `app` service, a caller reaching the deployment —
directly, or through `nginx`, which will return 502 for the whole of that window because it does not wait
for readiness — is refused for roughly 40 seconds while the application's own preconditions would have
been satisfied in under 1.4. In the production tier the same window is additionally masked for the first
40 s by `start_period`, so an orchestrator that trusts the health status will route traffic to a
container that has never answered a probe.

**Recommendation** — Change `nginx`'s dependency to the long form
(`app: {condition: service_healthy}`) so the reverse proxy starts only after the app has answered
`/health`, and reduce the production healthcheck's `start_period` to 10 s with `interval: 5s` so the
40-second pre-verdict window disappears. Re-enable the dev healthcheck (or add `interval: 5s` with
`retries: 12`) so `.\Makefile.ps1 up --wait` gates on real readiness rather than on container start.
None of this changes application behaviour; it changes only when traffic is admitted.

## Distribution

The findings fall almost entirely on the **request-serving process**, and within it on the
background-processing path around it. Seven of the eight touch `src/mkobi/workers/` or
`src/mkobi/core/task_queue.py` or the lifespan in `src/mkobi/app.py`; two touch `src/mkobi/api/routes/`
and one touches `alembic/env.py`. The `db`, `redis` and `frontend` containers are uninvolved, and
`rq-worker` is affected only in the sense that it is the component that is running and idle.

- **Background work path** — TOPO-001, TOPO-002, TOPO-003 (the serving process carries the queue,
  the outcome maps, and the whole failure-reporting path).
- **Startup path** — TOPO-004, TOPO-005, TOPO-007, TOPO-008 (`lifespan`, `DatabaseStarter`,
  `alembic/env.py`, compose definitions).
- **Entry layer** — TOPO-006 (one admin route).
- **Tier skew** — the production definition is the one with 4 workers, the RQ worker and a 40 s
  `start_period`; the dev tier that is actually exercised has 1 worker, an inert RQ worker and no
  healthcheck, so TOPO-005 and TOPO-008 are observable only as static proofs plus the dev-tier
  measurement in TOPO-008.

## Cross-Finding Analysis

Four findings share one cause: **the system was migrated from a single-process, in-process work model
toward a durable external worker, and the migration was completed on the deployment side but not on the
code side.** `docker-compose.yml:169` ships a Redis-backed `rq-worker`; `core/task_queue.py:60-66` still
documents `enqueue_with_worker` as "the integration point for background worker migration" and delegates
to the in-process queue; `rq_worker_wrapper.py:1-5` still describes itself as the worker bootstrap; and the
one place that documents what in-process work costs — `TaskQueue.shutdown()` — is never called. That
single unfinished migration produces TOPO-002 (the deployed worker is inert), TOPO-003 (work and its
outcome are per-process and the loss is unreported), and it is why TOPO-001's compensating write was
never exercised: the failure path of the *only* code path that actually runs has no test. TOPO-005 is
the same asymmetry seen from the other side — the deployment was scaled horizontally, and the code inside
was written assuming one process.

TOPO-004, TOPO-007 and TOPO-008 are independent of that and of each other.

## Roadmap

1. **Close the failure-reporting gap first (TOPO-001).** It is a single control-flow fix, it is the only
   finding a user can see directly today, and it is the cheapest to verify: the uploaded-file state must
   become `failed` with an `error_code` on the same request. Must be true before step 2, because step 2
   changes *which* process runs the job and therefore re-tests the same failure path.
2. **Then decide the work-submission mechanism (TOPO-002, TOPO-003).** This is one decision, not two:
   moving to RQ closes both, and so does deleting the RQ surface. Must be complete before step 3, because
   the elected-loop design in step 3 depends on knowing how many processes can run a sweep.
3. **Then make N-process behaviour safe and observable (TOPO-005),** together with the readiness gate in
   TOPO-008 — the loop lease and the health signal are one change to the same `/health/detailed`
   component map. Requires step 2 to be settled so the loop is not the last thing standing between the
   deployment and its declared topology.
4. **Then the schema-bootstrap guard (TOPO-004) and the gate coverage that would have caught it
   (TOPO-007)** — in that order, since widening the gates before the guard exists would only make the
   missing guard more visible without changing its behaviour.
5. **The entry-layer move (TOPO-006) is independent** and can run in parallel with any of the above; it
   touches no lifecycle code.

## Rollout Safety

Steps 1 and 2 change observable behaviour. **Step 1** alters the state a client polls for: rows that today
sit at `uploaded` after a failure will begin reporting `failed` with a populated `error_code`. Anything
that treats `uploaded` as "still in flight" must handle `failed` — the frontend already renders terminal
states from this row, but the upload polling code should be re-read before shipping. The fix also makes
previously-dead code execute, so any handler that assumed `_process_csv_file_async` only ever returns on
success must be re-checked; the exception still propagates exactly as before, so callers see no change
there. Revert by restoring the `raise`; the failure path returns to its current behaviour with no data
migration. **Step 2** is the larger blast radius: moving submission to RQ changes where processing runs,
so the temp-file path must be identical from both processes (it is — both mount `app_data` at
`/app/data`, `docker-compose.yml:200-201`), the worker must run as a user that can write there
(uid 100 `app` in the prod image, `docker/Dockerfile:172`), and the healthcheck on `rq-worker` must change
from a Redis ping to a worker-heartbeat check, because a Redis ping cannot distinguish a live worker from
a dead one. Stage it by running the RQ path beside the in-process one for one deployment and comparing
`processing_logs` outcomes before removing the in-process path; the `processing_logs` table is the
reconciliation surface for the comparison. Do not ship steps 1 and 2 in the same release.

Steps 3-5 change no request-path behaviour; the loop lease adds a Redis key with a TTL and the
`/health/detailed` response gains a component entry, which is additive but is a public endpoint — check
that no consumer asserts an exact key set on `components`.

## Appendices

**A. Per-tier component inventory as derived from what each tier actually starts.**

| Component | Dev (`docker-compose.override.yml`) | Prod (`docker-compose.yml`) | Test (`docker-compose.test.yml`) | Lifetime |
|---|---|---|---|---|
| `db` / `test-db` | unconditional | unconditional | unconditional | long-lived |
| `redis` / `test-redis` | unconditional | unconditional | unconditional | long-lived |
| `migrate` / `test-migrate` | one-shot, `alembic upgrade head` | one-shot | one-shot | runs once, exits |
| `app` | 1 process, `--reload` | 4 processes, `--workers 4` | `tail -f /dev/null` (no app) | long-lived |
| `rq-worker` | unconditional, **receives no work** | unconditional, **receives no work** | absent | long-lived, idle |
| `frontend` | unconditional (Vite) | absent (built into image) | absent | long-lived |
| `nginx` | absent | `profiles: [production]` | absent | long-lived |

**B. Method.** Dev tier brought up with the documented commands and driven live: authenticated
`POST /api/v1/auth/login` → `POST /api/v1/upload/{dashboard_id}` (HTTP 201) against the seeded dashboard
`test_media_dash`; the resulting work record, the Redis keyspace, the RQ worker's registry hash and
`state` field, and the app and worker container logs were all read back. Startup window measured by
`docker restart mkobi-app-1` with a ~150 ms `GET /health` poll (225 attempts, first answer at 40258 ms).
Route surface read from the running instance's `/openapi.json` (57 operations; no `/api/v1/processing-logs`
prefix is present — the router is included at `app.py:254` and its paths are served under
`/api/v1/admin/logs`, so it is reached, not orphaned). Import graph, gate coverage and unreachability
established statically.

**C. Checked and not filed.** `api/routes/filters.py` is a documented placeholder, not dead code
(its own docstring records the removal). No lower-layer module imports `mkobi.api` — the dependency
direction is clean. `_verify_role_privileges` (`starter.py:373-388`) is a warn-only check, but
`select rolcreatedb from pg_roles` returns `f` for `mkobi_app` in the running tier, so it fires nothing
today. The advisory lock is genuinely held by the process that runs the migration (correct holder), it
simply is not held on the path that drops the database (TOPO-004). The SPA mount at `/` answers unknown
non-`api/` paths with `index.html`, but this is documented intended behaviour of `SPAStaticFiles` and was
not filed.

**D. Limits of this report.** The production tier was not started: it requires a populated `.env` with
real secrets and a prior `npm run build`, neither of which is available here. TOPO-005 (four workers) and
part of TOPO-008 (the production `start_period`) are therefore established from the shipped
`docker/Dockerfile:179` and `docker-compose.yml:135-140` plus the dev-tier measurement, not from an
observed four-process boot; the residue is a *lower* bound on the findings, not a higher one — fewer
observed effects cannot raise a severity. The destructive branch of `recreate_test_database` was not
observed executing, because the only running tier that arms `RECREATE_TEST_DB` is the test tier, whose
harness bypasses the lifespan (`conftest.py:559`) and whose app container runs `tail -f /dev/null`; the
finding rests on the static proof in TOPO-004 plus the reachability shown by
`docker-compose.test.yml:93,147`. The `dev` tier's reload behaviour is a dev-only artifact and is
excluded from the 40 s figure's attribution to the application's preconditions, which the log timestamps
pin at 1.38 s.
