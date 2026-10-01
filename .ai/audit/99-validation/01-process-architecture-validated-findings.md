---
phase: 01-process-architecture
executed: 2026-09-30
executor: validator
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 5
  LOW: 1
---

# Phase 01 — Validated Findings

## Summary

All eight findings in `.ai/audit/01-process-architecture/findings.md` were re-derived from the executing path
rather than from their quoted evidence, and all eight are substantiated. TOPO-001 was reproduced independently
in this environment: a 3-row CSV uploaded to `a5214e7a-…` failed with `ColumnNotFoundError: "TVR" not found`,
`app` logs show `Processing log updated: … status=processing` at 10:17:35 and no subsequent status write, the
`processing_logs` row reads `status=uploaded, error_code=NULL, message='File uploaded successfully, awaiting
processing. mode=overwrite'`, and `/app/data/tmp_uploads/` is empty. TOPO-002 re-derived at runtime: after the
same upload `rq:queue:default` does not exist (`EXISTS` → 0), the worker hash reads `state=idle, queues=default`,
and the worker's entire log holds only `started with PID 1`, `*** Listening on default...` and registry-cleaning
lines. TOPO-008 re-measured on a `docker restart mkobi-app-1` with a ~150 ms `GET /health` poll: **289 attempts,
first answer at 57 443 ms**, against 1.07 s of application precondition work in the same run. Every band survives
re-grading against the audited phase's own rubric, with one exception recorded as a re-grade: TOPO-008 moves LOW →
MEDIUM, because the rubric's LOW band is defined as *no runtime consequence today* and this one has a measured
one. Eight defects in the audit itself were found, two of them MEDIUM: a claim about the dependency-injection
layer that cites a docstring example as executing code, and a recommendation that turns a green gate red if
executed as written. Two of the input's own claims were refuted outright — that the DI layer runs a query, and
that `start_period` reports a container healthy before its first successful probe.

Each finding below carries the six fields the shared template mandates plus **Verdict**, which the template does
not enumerate and the validation output contract requires; recorded as VAL-008.

## Findings

### TOPO-001 — A failed background job is recorded as still awaiting processing until the process restarts

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — Termination: what an in-flight operation leaves behind

**Observation** — Re-derived from the executing path. `data_worker.py:582` is the `else` of `if db_session is not
None:` (`:552`), so `:582-620` is the branch every production upload takes. Its `except` handler ends at `:603`
with `raise`, which propagates out of `async with session.begin()` (`:585`) and `async with get_session()` (`:584`)
and out of the function; the `return` at `:587` closes the other path. Sixteen lines that follow (`:605-620`) —
the independent `_update_processing_log_status(..., FAILED, ...)` call — are therefore unreachable on both paths,
and the comment at `:604` states the opposite of what the code does. The `PROCESSING` write at `:390-396` passes
`session=session`, so it is inside the same transaction and is rolled back with everything else. The only other
component that ever moves such a row is `mark_orphaned_uploaded_logs_failed()` (`app.py:116`), which runs once
per process start and only touches `UPLOADED` rows older than one minute.

**Evidence** — Reproduced in this environment. Authenticated as `admin@example.com` against the dev tier, uploaded
a 3-row CSV to `POST /api/v1/upload/a5214e7a-4884-4d2c-a7c9-98f27d42e0a8` (HTTP 201,
`task_id=b130b0cf-8892-42a3-ac67-47c8b84747b0`). The job failed with
`polars.exceptions.ColumnNotFoundError: "TVR" not found`. App log, in order:
`Processing log updated: task_id=b130b0cf-… status=processing` (10:17:35), `Processing failed: task_id=… code=PROCESSING_FAILED`
(10:17:35), and nothing after. `psql -c "select id, status, error_code, message, started_at, finished_at from
processing_logs"` returns `b130b0cf-… | uploaded | | File uploaded successfully, awaiting processing. mode=overwrite`
with null `started_at` and null `finished_at` — the `PROCESSING` write is demonstrably rolled back.
`docker exec mkobi-app-1 ls -la /app/data/tmp_uploads/` returns an empty directory: the file the row still names
was deleted at `:594-602` before the re-raise. Static unreachability proof: `:603` precedes `:605-620`, and no
`return` exists between them.

**Consequence** — Unchanged from the input and re-derived as true. A user is told, by the upload response and by
every subsequent `GET /api/v1/upload/status/{task_id}` poll, that the file is awaiting processing, while the file
no longer exists and the work record is untouched. The operator sees a clean `Processing failed` log line and a row
that contradicts it. The row is corrected only at the next process start, and only once the row is more than one
minute old. Nothing in the running system distinguishes "still working" from "died an hour ago".

**Recommendation** — Executable as written. Target `data_worker.py:582-620` exists and is the production branch;
moving the `FAILED` write after the `async with session.begin()` block exits removes the effect outright, and the
report's second shape (a `finally` outside the transaction) reaches the same place. The named remediation blocker
is correct and I re-derived it independently, with one strengthening: the input lists three test files, and the
population is larger. Twelve `process_csv_background(` call sites exist under `tests/`, and **every one** passes a
`db_session` — `async_db_session` in `test_upload_api.py` (3), `test_e2e_upload.py` (3),
`test_filter_values_consistency.py` (3), `test_filter_persistence.py` (2), and `mock_session` in
`test_file_cleanup.py` and `test_data_worker.py` (8). No shipped test can reach `:582`. The suite therefore cannot
fail on this defect in either branch, and a fix needs a test that omits `db_session`.

### TOPO-002 — The deployed RQ worker has never received work; every submission goes to the serving process's memory

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM

**Zone** — The periodic loop and the work-submission mechanisms inside the request-serving process

**Observation** — Re-derived from the executing path. Two submission mechanisms exist and only one is reachable.
`TaskQueue` (`core/task_queue.py:18`) is an `asyncio.Queue` plus three in-process dicts, instantiated as the
module-level singleton `default_queue` (`:159`). The Redis/RQ queue is constructed in exactly one place,
`rq_worker_wrapper.py:104`, inside `start_rq_worker`, whose only callers are its own `__main__` guard and
`tests/test_rq_worker_wrapper.py:99`. A repo-wide search for `from mkobi.rq_worker_wrapper|import mkobi.rq_worker_wrapper`
outside that test returns nothing. No `rq.Queue(...).enqueue(...)` call exists anywhere under `src/`: the nine
matches for `Queue\(|enqueue\(|\.enqueue` are `task_queue.py:28,33,66,76,159,181,190`, `app.py:129` and
`rq_worker_wrapper.py:104`, and none is an RQ enqueue. The only submission call site in the product is
`services/file_processing.py:366` — a bare `await enqueue_job(process_csv_background, …)` — which routes to
`default_queue.enqueue` (`task_queue.py:181`). `TaskQueue.enqueue_with_worker` (`:55`), documented at `:69` as
"the integration point for background worker migration", has no caller. The `rq-worker` service is declared at
`docker-compose.yml:169-221` and overridden at `docker-compose.override.yml:118-152`, holds the same `app_data`
volume as `app` (`:143-146`), and `override:123` launches it with the bare `/app/.venv/bin/rqworker` CLI — the
same command `docker inspect mkobi-rq-worker-1 --format '{{json .Config.Cmd}}'` returns. The declared retry entry
point is a declared entry surface that is never executed.

**Evidence** — Static, as described above. Runtime, in this environment and after the upload of TOPO-001:
`docker exec mkobi-redis-1 redis-cli EXISTS rq:queue:default` → `0`, and the full keyspace is `rq:workers`,
`rq:workers:default`, `rq:worker:3d593384c6744fcfb1244dc582809b1a`, `login:127.0.0.1`,
`upload:13a1f341-f73d-4522-aee9-9b1e9d632736` — no queue key, because nothing ever enqueued. The worker hash reads
`state=idle, queues=default, pid=1`, `birth=2026-09-30T10:15:01Z`, `last_heartbeat=2026-09-30T10:28:31Z`. Its
complete log, from container start to now, is three lines plus periodic registry sweeps: `started with PID 1,
version 2.9.1` (10:15:01), `*** Listening on default...` (10:15:01), and
`cleaning registries for queue: default` at 10:15:01, 10:28:32 and 10:42:02. **No job line in 27 minutes of
uptime**, while the app container in the same window processed a job that failed.

**Consequence** — Unchanged from the input and re-derived as true, with one correction of the input's own framing.
The input's Rollout Safety describes the healthcheck as one that is "carried" by the service; the base file declares
one at `docker-compose.yml:205-214`, but `docker-compose.override.yml:151-152` sets `healthcheck: disable: true`
and `docker inspect mkobi-rq-worker-1 --format '{{.State.Health.Status}}'` returns `NO_HEALTHCHECK` in the tier
that actually runs. The substance is unchanged and slightly worse: a container, a Redis service, a mounted volume
and a documented retry entry point exist solely to consume a queue nothing writes to, and in the running tier the
component is not even monitored. The declared benefit of the Redis path — durability across restart and horizontal
scale, documented at `core/task_queue.py:4,23,60-61` and in `docs/11-guides/task-queue-migration.md:83-90` — is
absent: work is only as durable as the process that accepted it. An operator reading `docs/10-deployment/deployment.md:192`,
which describes `rq-worker` as the component that performs background task processing, has no accurate picture of
where processing work runs.

**Recommendation** — Substantiated but **unusable as written**: it offers two mutually exclusive alternatives
("Either (a) … or (b) …") and the choice between them is architectural, not clerical. This is the distinct outcome
the output contract reserves for a recommendation that names alternatives, and it is recorded as such rather than
counted as a failure. Both alternatives are individually executable and both targets exist — `rq.Queue(...).enqueue`
is a valid call, `process_csv_background_sync` exists at `data_worker.py:871`, and `task_queue.py:69` documents the
RQ-compatible signature. What a reader cannot do from this report is start. Recorded as VAL-005, LOW.

### TOPO-003 — Accepted work and its outcome are held only in the serving process, and the shutdown report that would announce the loss never runs

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM

**Zone** — Shared state across processes, and what is per-process by construction

**Observation** — Re-derived from the executing path. `TaskQueue` holds the payload queue (`:28`), the status map
(`:29`), the result map (`:30`) and the error map (`:31`) in process memory; `default_queue` (`:159`) is a
module-level singleton. `TaskQueue.enqueue` mints `task_id = str(uuid.uuid4())` at `:44`, which is *not* the
`processing_logs` id the job updates, and the single call site discards it: `services/file_processing.py:366` is a
bare `await enqueue_job(...)` with no assignment, while `enqueue_job` (`:181`) returns the in-memory id. The three
accessors `get_status` (`:107`), `get_result` (`:122`) and `get_error` (`:133`) therefore have no reachable caller:
a repo-wide search for `get_status|get_result|get_error|\.shutdown\(\)|TaskQueue` over `src/` and `tests/` returns
only the definitions, plus the two unrelated HTTP handlers `upload.py:260` (`get_status_endpoint`) and
`upload.py:317` (`get_result_endpoint`), both of which read the database. `TaskQueue.shutdown()` (`:144`) has no
caller: the lifespan's `finally` block (`app.py:156-180`) cancels the cleanup task, cancels the queue worker,
disposes the engine and shuts the starter down, and never touches the queue.

**Evidence** — Static, as described. Runtime, in this environment: a full shutdown was produced by this
validator's own `docker restart mkobi-app-1` at 10:40:42. The complete log sequence is `Shutting down
application...` → `Stale processing cleanup task cancelled` → `Task queue worker cancelled` → `Database engine
disposed cleanly` → `Database engines disposed` — byte-for-byte the sequence the input recorded, with no loss line
between them. A `Select-String` for `TaskQueue shutting down` over the container's entire log history returns
nothing.

**Consequence** — Unchanged from the input and re-derived as true. Two of the three things a caller could want to
know about submitted work — its in-process status and its outcome — are unreachable by construction, and the third
(the database row) is wrong after a failure per TOPO-001. At termination the queue worker task is cancelled
mid-`await` inside `TaskQueue.process_next` with no drain and no compensating action; anything still in `_queue` is
discarded with the process and the operator is told nothing, because the one function written to say so is never
called.

**Recommendation** — Executable. The first half names an existing target (`get_task_queue().shutdown()` at
`app.py:129`'s import path, `finally` at `:156-180`) and closes the documentation/behaviour gap in isolation. The
second half is correctly made conditional on TOPO-002's decision. Ordering constraint: the shutdown call must
precede the `queue_worker_task.cancel()` at `app.py:169-175` or it reports on a queue whose consumer is already
gone. The input's roadmap places this at step 2, which is consistent.

### TOPO-004 — The only path that drops and recreates the whole store takes no guard, and the one guard in the system is entered after the store is gone

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH, at the top of the band and one setting from CRITICAL

**Zone** — The schema and reference-data bootstrap gate, and whether any of its steps can destroy a schema

**Observation** — Re-derived from the executing path. Four paths can mutate the schema. (1) The `migrate` one-shot
(`docker-compose.yml:55-80`, `command: ["alembic","upgrade","head"]`, `restart: "no"`), ordered ahead of `app` by
`depends_on: migrate: condition: service_completed_successfully` (`:87-89`). (2) `AUTO_MIGRATE` inside the
application process, `db/starter.py:153-154`, set to `"false"` in every compose tier
(`docker-compose.yml:197`, `override:113`, `override:145`, `docker-compose.test.yml` carries none).
(3) The ad-hoc CLI `python -m mkobi.db.starter --recreate-test-db` (`starter.py:423-430`). (4) The in-process
`DatabaseStarter.startup()`, which reaches `recreate_test_database()` whenever
`env == TEST or config.recreate_test_db` (`starter.py:184-185`) — a condition that is an `or`, not an `and`, so
`ENV=test` alone arms it. `recreate_test_database` (`:190-292`) issues `SELECT pg_terminate_backend(pid) … WHERE
datname = :db_name` on the admin engine opened at `admin_database_url` (`:200`, `isolation_level="AUTOCOMMIT"`,
`:210`), then `DROP DATABASE IF EXISTS` (`:250-252`) and `CREATE DATABASE` (`:253-255`). It takes **no** lock of
any kind. The project's only concurrency guard is `pg_advisory_lock(42)` — `MIGRATION_ADVISORY_LOCK_KEY = 42` at
`alembic/env.py:58`, acquired at `:115-117` and released at `:123-127` — and `recreate_test_database` reaches it
only at `:310`, by calling `_apply_migrations`, which is **after** the drop. The guard is a plain blocking acquire
with no timeout and no `try_lock`/`skip` variant, so it serialises migration but never protects the drop.

**Evidence** — Static, as described. The test tier is armed with both triggers: `docker-compose.test.yml:129`
(`ENV: test` on `test-app`) and `:147` (`RECREATE_TEST_DB: "true"`). The test harness is the only current consumer
of the destructive method: `tests/conftest.py:433` calls the same `recreate_test_database()` from a session-scoped
fixture, so two independent, uncoordinated creators of `bidb_test` exist in the same tier. The application's own
copy of this path is never executed by the harness: `conftest.py:559-560` builds the client with
`httpx.ASGITransport(app=app)`, which does not emit ASGI lifespan events, so `DatabaseStarter.startup()` never
runs in a single test. The input's `ENV: test` anchor is off by one line (`:93` is `test-migrate`'s block; the
`test-app` trigger is `:129`); the substance and the reachability are unchanged, and the corrected anchor is used
here. Recorded as VAL-003, LOW.

**Consequence** — Unchanged from the input and re-derived as true, with the blast radius now bounded exactly. The
store is one setting away from being destroyed by every process that starts, and in the test tier both triggers
are already set. In the production tier the same flag would be acted on by each of the four uvicorn workers
described in TOPO-005, in parallel and unguarded. The once-only guarantee for the destructive step comes from
neither declared ordering nor the guard — it comes only from the fact that no deployment currently sets the flag on
a tier that runs the lifespan, and from the accident that `test-app` runs `tail -f /dev/null` rather than the
image's own `CMD` (`docker/Dockerfile:151`, `["pytest","tests/","-v"]` — itself a correction: the input calls
`Dockerfile:151` "the app image's own CMD", and `:151` is the **test** target's CMD, the app target's being
`:179`). That accident is the whole of the protection. Recorded as part of VAL-003, LOW; it does not
change the finding, which rests on the unguarded drop itself.

**Recommendation** — Executable, and the input's own ordering is right: the guard must land before the gate
coverage widens, or the widened gate simply reports the same missing guard more loudly. Target
`starter.py:240-256` exists; the named pattern check (`bidb_test` or `bidb_test_<worker>`) is a strictly stronger
control than the boolean it replaces and is the change this phase's own rubric would grade highest. Dependencies:
dropping `RECREATE_TEST_DB` from `docker-compose.test.yml:147` requires `conftest` to assert it created the
database it is about to use, which is a change to `conftest.py:433`'s fixture. Roadmap position 4 is correct.

### TOPO-005 — Production starts four uvicorn workers from one image entry, and every one of them runs the boot preconditions and its own copy of the periodic loop

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM

**Zone** — Component inventory, and the topology that differs between deployment tiers

**Observation** — Re-derived from the executing path. The production image's `CMD` is
`["uvicorn","src.mkobi.main:app","--host","0.0.0.0","--port","8000","--workers","4"]` (`docker/Dockerfile:179`).
The dev tier replaces it with a single reloading process and no `--workers`
(`docker-compose.override.yml:109`), so the running topology the project exercises is 1 process and the shipped
topology is 4. Each worker independently executes the whole `lifespan`: `starter.startup()` (`app.py:112`, which
runs `ensure_admin_user` with a bcrypt hash, `cleanup_old_logs` and `cleanup_stale_temp_files` against the shared
`app_data` volume), `mark_orphaned_uploaded_logs_failed()` (`app.py:116`), and
`start_stale_processing_cleanup_task` (`app.py:120-125`) — a `while True` loop with a 300-second cadence,
started unconditionally, with no election, lease or leader check of any kind. The loop's only evidence of running
is the line it writes for itself (`data_worker.py:917-921` at start, `:287-292` only when it marks rows, guarded
by `if count > 0` at `:287`). No counter, timestamp, health field or metric exposes it:
`/health/detailed` builds a `components` map (`app.py:296`) and adds exactly two entries — `database` (`:310`)
and `static_files` (`:315`). The in-process work queue is likewise per-worker (`core/task_queue.py:159`).

**Evidence** — Static, as described; a search for any leader-election or Redis-lock primitive in `app.py` /
`data_worker.py` returns nothing. Runtime, dev tier: `docker inspect mkobi-app-1 --format '{{json .Config.Cmd}}'`
returns the single-process command the input quoted. Its log shows the loop starting exactly once,
`Starting stale processing cleanup task (interval=300s, timeout=30m)` at 10:15:32 (one instance, from this
validator's own restart), with no further output from it, because `cleanup_stale_processing_logs` logs only when
`count > 0`. The input quotes the start line as `Started stale processing cleanup task (interval=300s, timeout=30m)`;
the emitted text is `Starting …` — a cosmetic drift in a quote, recorded as part of VAL-003.

**Consequence** — Unchanged from the input and re-derived as true, with one present-state correction that
*reduces* the effect. The input's sharpest claim — that at four replicas a worker restarting alone would flip
sibling workers' in-flight `UPLOADED` rows to `FAILED` — does not survive: `mark_orphaned_uploaded_logs_failed`
carries a one-minute cutoff (`data_worker.py:312`), and an upload is consumed within a second of submission by
the in-process loop, so a sibling worker's rows are not still `UPLOADED` when another worker restarts. The
remaining effect stands in full: the sweeps, the retained-log `DELETE`, the admin bcrypt hash and the temp-file
sweep all multiply by the replica count, and because the loop emits nothing when it has nothing to do, a loop
that has died is indistinguishable from a loop with no work.

**Recommendation** — Executable, with the same alternatives problem as TOPO-002's: it offers a Redis lease *or*
dropping `--workers 4` (`if the four workers are not wanted at all`). Recorded, LOW, alongside VAL-005. The
primary direction is sound and the input's justification for it is correct — the Redis dependency is already a
hard requirement of the request path (`get_redis_client_dependency`, `api/deps.py:122`), so the lease adds no
new failure mode. The named target `/health/detailed` already carries a `components` map, so the signal has an
existing home. The input's Rollout Safety is right to flag that this is a public endpoint whose exact key set
must be checked.

### TOPO-006 — The admin approval route sequences four cross-store effects, one of them non-transactional, with a rollback that cannot undo it

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM, with one sub-claim refuted

**Zone** — Entry-layer discipline and dependency direction

**Observation** — Re-derived from the executing path.
`approve_registration_request_admin_endpoint` (`api/routes/admin.py:279-345`) is the request-entry module and it
owns the whole approval rule. In one handler body it (1) calls `auth_service._generate_temp_password()` — a
private method of the service, reached from the transport (`:306`); (2) creates the user via
`auth_service.create_user` (`:307`); (3) sets `force_password_change` via `auth_service.user_repo.update`
(`:315-317`); (4) writes the temporary password to **Redis** via `temp_password_store.store` (`:321`), an
immediate, non-transactional `SET` with a 24-hour TTL (`core/temp_password_store.py:41`; `config.py:369`); (5)
updates the registration request's status (`:324`); and only then (6) calls `await db.commit()` at `:330`. The
`except` handler at `:338-343` calls `await db.rollback()`, which reverses (2), (3) and (5) but not (4). The
transport module owns the commit boundary directly in **ten** places — `admin.py:330`, `admin.py:386`,
`dashboards_access.py:205`, `dashboards_crud.py:139`, `dashboards_filters.py:64`,
`dashboards_filters.py:106`, `dashboards_graphs.py:98`, `graphs.py:122`, `graphs.py:372`,
`graphs.py:467` — and the input's count of one rollback (`graphs.py:383`) is correct *as a count of rollbacks in
the same file as a commit*, but the pattern returns **eleven** rollback sites across `api/routes/`
(`admin.py:188,235,340,392`, `dashboards_access.py:216`, `dashboards_graphs.py:109,121`, `graphs.py:127,134,383,471`).
The input's substantive point survives intact: `dashboards_filters.py:68-79` and `:114-127` commit at `:64` and
`:106` and have no corresponding `rollback` in either `except` block. The dependency direction itself is clean —
a repo-wide search for `from mkobi.api|import mkobi.api` outside `api/` and `app.py` returns **no** matches — so
the violation is entirely in what the transport does, not in what it imports.

**Evidence** — The call sequence and the commit/rollback placement read directly from `admin.py:305-345`. The ten
`db.commit()` sites above are the complete set returned by a search for `db\.commit\(\)` over
`src/mkobi/api/routes/*.py`; the eleven `db.rollback()` sites likewise. **The input's final claim is refuted**:
"`api/deps.py:112-113` runs `db.execute(select(User))` in the dependency-injection layer." Lines 112-113 are
inside a **docstring example** in `get_db_dependency` (`deps.py:109-114`); the function's body is
`async with get_session() as db: yield db` (`:115-116`). The dependency-injection layer executes no query of its
own. Recorded as VAL-001, MEDIUM — it is a claim about the executing path sourced from a documentation line, which
is the specific defect the output contract calls a wrong approval.

**Consequence** — Unchanged from the input for the Redis/db half and re-derived as true. If step (4) succeeds and
step (5) or the commit fails, the handler rolls back the database work, returns HTTP 500, and leaves a live
retrieval token in Redis holding a temporary password for a user that no longer exists. The client receives no
`user_id` and no `retrieval_token`, so the token is unreachable by any client; it is the only copy of the
credential and it lives for `temp_password_ttl_seconds`, 24 hours by default (`config.py:369`). The invariant "an
approval creates a user, forces a password change and mints exactly one usable token, or creates nothing" exists
nowhere except as the statement order of a route handler. One correction of scale: because `TempPasswordStore.store`
fails open — it catches every exception and logs a warning (`core/temp_password_store.py:47-48`) rather than
raising — the window in which (4) succeeds and (5) fails is narrow, and a Redis outage cannot produce this state at
all. The finding is a transaction-boundary defect, not a credential-leak defect, and should be triaged as one.

**Recommendation** — Executable and the smallest change in the report. Target
`AuthService.approve_registration_request(request_id, admin_id, db)` names a class and a method that do not yet
exist, which is what a recommendation that adds a method should do; `_generate_temp_password` is currently private
(`auth_service.py`) and reached only from the transport, so making it internal to the service is the whole of that
half. Ordering within the move is right and load-bearing: putting the Redis write *after* the commit is what makes
the invariant hold, and the input says so. Independent of every other step, as the roadmap states. One dependency
the input does not name: the route currently has direct access to `auth_service.user_repo`
(`admin.py:315`), so the service method needs the repository to reach the user's `force_password_change` — either
the service keeps that access, or the route stops reaching through it. Both are in the same move.

### TOPO-007 — The migration entry surface is outside both automated quality gates

**Severity** — LOW

**Verdict** — confirmed; band upheld at LOW

**Zone** — Entry surfaces: what is constructed when a surface loads, and what is deferred

**Observation** — Re-derived from the executing path. The entry surfaces are: `uvicorn src.mkobi.main:app`
(request-serving; `docker/Dockerfile:127`, `:179`, `docker-compose.override.yml:109`), `alembic upgrade head`
(schema mutation, one-shot; `docker-compose.yml:60`, `Makefile.ps1:256`), `python -m mkobi.db.starter
--recreate-test-db` (one-shot, `starter.py:423-430`) and the `rqworker` CLI (work-consuming;
`docker-compose.yml:174`). `alembic/env.py` is the load-time surface of the second: it imports every ORM model
(`:29-32`), resolves the database URL from three sources (`:45`, `:79`, `:98`), and acquires and releases the
project's only concurrency lock (`:115-117`, `:123-127`). Both automated gates exclude it: `Makefile.ps1:222`
runs `ruff check src/ tests/` and `Makefile.ps1:230` runs `mypy src/`; `alembic/` is outside `src/`, and
`pyproject.toml:169` additionally sets `exclude = ["alembic/"]` for mypy. The `check` aggregate
(`Makefile.ps1:241-249`) inherits both omissions. A secondary load-time effect sits on every surface:
`Settings.__init__` calls `_ensure_upload_dir()` (`config.py:570`, `:584-587`), which creates a directory on the
filesystem during module import, and `SecretsFileSource.__call__` (`config.py:60-83`) enumerates the whole
process environment and stats every `*_FILE` variable.

**Evidence** — Static, as described. The runtime confirmation re-derived in this environment:
`docker logs mkobi-app-1` contains, at the head of every process start and again after the restart this validator
performed, the unformatted line `Failed to read secret file .: [Errno 21] Is a directory: '.'`, emitted before
`setup_logging()` runs (`app.py:39-43`) and therefore outside the structured log format. It comes from
`LOGGING__LOG_FILE=` (set to the empty string at `docker-compose.override.yml:82`), which the `_FILE` suffix
heuristic at `config.py:65-66` misreads as a Docker-secrets pointer to `LOGGING__LOG`, then `read_text()`s at
`Path("")` → `Path(".")`.

**Consequence** — Unchanged from the input and re-derived as true, with the gate consequence now **measured**
rather than asserted. I ran both tools against the excluded path in this environment: `ruff check alembic/` reports
**4 errors** (`alembic/versions/20250915_0004_…py:1,3,10,12` — `UP035` deprecated import, `UP007` `Optional`/
`Union`) and `mypy --no-incremental alembic/env.py` reports **Success: no issues found in 1 source file**. So the
type-check half of the recommendation is genuinely free, and the lint half would turn a green gate red on four
pre-existing violations in one hand-written migration file. That is not an argument against the recommendation; it
is an ordering fact the input's Roadmap does not carry, and it is recorded with the recommendation below.

**Recommendation** — Substantiated but **not executable as written**, and the defect is specific:
`ruff check src/ tests/ alembic/` fails today on four pre-existing `UP007`/`UP035` violations, so widening the
gate in that form is a one-commit change that lands red. The executable form is narrower and the input's own
rationale already points at it: add `alembic/env.py` to the **mypy** path (verified clean) and to the **ruff** path,
and either fix or exclude `alembic/versions/` — the four errors are in a revision file, not in the entry surface
the finding is about. Recorded as VAL-002, MEDIUM. The `_FILE`-heuristic half of the recommendation is executable
as written and should be taken independently of the gate change: narrowing the suffix match to an allowlist, or
skipping empty values, removes the warning from every surface including `alembic upgrade head`. The
`_ensure_upload_dir()` half is correctly deferred behind TOPO-005's decision.

### TOPO-008 — Nothing in the deployment gates traffic on the application's boot preconditions

**Severity** — LOW → MEDIUM

**Verdict** — confirmed; **re-graded LOW → MEDIUM**; one mechanism claim refuted, one remedy shown not to address the measured window

**Zone** — Startup order, and the interval in which the process answers before it can serve

**Observation** — Re-derived from the executing path. Inside the process the ordering is correct and fail-fast:
`lifespan` awaits `starter.startup()` (`app.py:112`) before `yield` (`:146`), and `DatabaseStarter.startup` raises
`DatabaseNotFoundError` on an unreachable database (`starter.py:94`, `:109`) and `SchemaNotFoundError` on a
missing revision (`starter.py:161-164`), both of which propagate out of the lifespan (`app.py:147-155`) and abort
the boot. Nothing serves before the preconditions complete — uvicorn does not accept requests until the lifespan
startup returns. The gap is between the process and its caller. `nginx` declares `depends_on: - app` in short
syntax (`docker-compose.yml:228-229`), which waits only for the app *container to start*, not for it to be ready.
The dev tier sets `healthcheck: disable: true` (`docker-compose.override.yml:110-112`), so the dev deployment has
no readiness signal at all, which I confirmed at runtime: `docker inspect mkobi-app-1 --format
'{{.State.Health.Status}}'` returns `NO_HEALTHCHECK`.

**Evidence** — Runtime, re-measured in this environment on the same command the input used.
`docker restart mkobi-app-1` followed by a client polling `http://127.0.0.1:8010/health` every ~150 ms recorded
**289 attempts before the first answer — `FIRST_ANSWER_MS=57443`**, `body={"status":"healthy","database":"connected"}`.
The app's own log timestamps bracket the precondition work precisely: `Initializing application...` at
`2026-09-30T10:15:31.047413292Z` and `Application initialized successfully` at `2026-09-30T10:15:32.121260342Z` —
**1.074 seconds** — against a 57-second refusal window. The input's sample (40 258 ms, 224 attempts) and mine
(57 443 ms, 289 attempts) differ by run, not by method; both show a window one to two orders of magnitude larger
than the preconditions.

**The input's `start_period` mechanism claim is refuted by direct experiment.** The report states that with
`interval: 30s` and `start_period: 40s` "for the first 40 seconds Docker reports the container healthy without a
single successful probe result", and builds a remedy on it. Two probes settle it against this environment's
Docker Engine 29.8.0:

- `docker run -d --health-cmd "curl -sf http://localhost:8000/health || exit 1" --health-interval 30s
  --health-start-period 40s --health-retries 3 mkobi-app:latest sleep 60` — a probe that always fails.
  At t=8 s and t=28 s, `.State.Health.Status` is **`starting`**, not `healthy`, and the probe log shows five
  consecutive `ExitCode: 1` results. The container is never reported healthy without a successful probe.
- The same container with `--health-cmd "exit 0"` reports **`healthy` at t=8 s**, i.e. a successful probe inside the
  start period promotes the container immediately.

Docker's own documentation agrees: the health status "is initially `starting`", and "if a health check succeeds
during the start period, the container is considered started". `start_period` suppresses failure *counting*; it
does not manufacture a healthy verdict. The input's Consequence sentence — "an orchestrator that trusts the health
status will route traffic to a container that has never answered a probe" — does not hold.

**Consequence** — The finding survives, and its band rises. The measured effect stands: during any restart or
rollout of `app`, a caller reaching the deployment is refused for **57 seconds** in this run while the
application's own preconditions were satisfied in 1.07. `nginx` will return 502 for the whole of that window
because it does not wait for readiness. The input's second-order effect — the 40-second `start_period` masking —
is refuted, so the window is *not* double-masked; it is a single 57-second gap. Against the audited rubric this
is MEDIUM, not LOW: the LOW band is defined as "documentation-only drift about topology or lifecycle with **no
runtime consequence today**", and this has a measured runtime consequence today. The MEDIUM band covers "a
defect an operator cannot distinguish from normal behaviour" and "a divergence between tiers that nothing
documents as intentional" — the dev tier has no healthcheck at all, the production tier has one, and nothing
documents either as deliberate. Re-grade recorded here, not applied silently.

**Recommendation** — The input's **primary** recommendation is executable and correct: change `nginx`'s dependency
to the long form (`app: {condition: service_healthy}`, `docker-compose.yml:228-229`) so the reverse proxy starts
only after the app has answered `/health`. Its **secondary** recommendation — reduce the production healthcheck's
`start_period` to 10 s "so the 40-second pre-verdict window disappears" — is built on the refuted mechanism and
achieves nothing: `start_period` was never creating a pre-verdict window. Drop that half. The input's third
recommendation, re-enabling the dev healthcheck so `.\Makefile.ps1 up --wait` gates on real readiness, is correct
and is the only one of the three that changes what this validator measured. Recorded as VAL-006, LOW.

## Distribution

The findings fall on three components, and one of them carries most of the weight. The **request-serving
process** carries six of the eight (TOPO-001, -002, -003, -005, -006, -008) plus the gate finding that describes
it (TOPO-007); the **schema bootstrap** carries one (TOPO-004); the **work-consuming `rq-worker`** carries one
(TOPO-002). No finding lands on `db`, `redis` or `frontend` as subjects — they appear only as participants in
TOPO-004's blast radius and TOPO-005's replica count.

- **Background work path** — TOPO-001, TOPO-002, TOPO-003. The serving process carries the queue, the outcome
  maps and the whole failure-reporting path.
- **Startup and bootstrap path** — TOPO-004, TOPO-005, TOPO-007, TOPO-008. `lifespan`, `DatabaseStarter`,
  `alembic/env.py`, and the compose definitions that govern when traffic is admitted.
- **Entry layer** — TOPO-006, one admin route.
- **The inert `rq-worker`** — TOPO-002, the only component in the report that is running, declared, and reached by
  nothing.

## Cross-Finding Analysis

Three findings share one cause, and the input names it correctly: **the system was migrated from a single-process,
in-process work model toward a durable external worker, and the migration was completed on the deployment side but
not on the code side.** `docker-compose.yml:169` ships a Redis-backed `rq-worker`;
`core/task_queue.py:60-66` still documents `enqueue_with_worker` as "the integration point for background worker
migration" and delegates to the in-process queue; `rq_worker_wrapper.py:1-5` still describes itself as the worker
bootstrap; and the one place that documents what in-process work costs — `TaskQueue.shutdown()` — is never called.
That single unfinished migration produces TOPO-002 (the deployed worker is inert) and TOPO-003 (work and its
outcome are per-process and the loss is unreported). The input further claims it explains why TOPO-001's
compensating write was never exercised, and I re-derived the stronger form: no shipped test reaches the production
branch at all, so the defect is untestable by the suite as written rather than merely untested. TOPO-005 is the
same asymmetry seen from the other side — the deployment was scaled horizontally and the code inside was written
assuming one process.

The input's claim that TOPO-004, TOPO-007 and TOPO-008 are independent of that and of each other **re-derives as
partly wrong, and this is a cross-phase merge candidate.** TOPO-004's guard is the advisory lock in
`alembic/env.py`; TOPO-007 is that the guard's file is outside both quality gates; and TOPO-008's remedy is to
gate traffic on `/health`. The three are not independent in their *remedies* — TOPO-004's recommendation and
TOPO-007's recommendation touch the same file, and TOPO-007's own Consequence already names TOPO-004. The input
gets the dependency right in its Roadmap (step 4 sequences TOPO-004 before TOPO-007 "since widening the gates
before the guard exists would only make the missing guard more visible without changing its behaviour") while its
Cross-Finding Analysis calls them independent. The finding-level verdict is unaffected; the grouping is recorded
as VAL-007, LOW, and the dependency is restated in the roadmap below.

## Roadmap

Ordered as the input orders it, with three corrections the validation established. Each step names what must be
true before the next begins.

1. **Close the failure-reporting gap (TOPO-001).** Executable, two lines, and the cheapest to verify: the uploaded
   file's state must become `failed` with a populated `error_code` on the same request. Must be true before step 2,
   because step 2 changes which process runs the job and therefore re-tests the same failure path. **Correction to
   the input:** the test that proves it must *omit* `db_session`. All twelve shipped call sites pass one, so the fix
   ships with a test that exercises the same branch the fix did not change unless a `db_session=None` driver is
   added.
2. **Decide the work-submission mechanism (TOPO-002, TOPO-003).** One decision, not two: moving to RQ closes
   both, and so does deleting the RQ surface. Must be complete before step 3, because the loop-lease design in
   step 3 depends on knowing how many processes can run a sweep. **Correction to the input:** this is the step the
   report leaves as a choice, and step 2 cannot start until the choice is made elsewhere. It is the critical-path
   item of the whole roadmap.
3. **Make N-process behaviour safe and observable (TOPO-005), together with the readiness gate (TOPO-008).** The
   loop lease and the health signal are one change to the same `/health/detailed` component map. Requires step 2
   to be settled. **Correction to the input:** the readiness half of this step is the `nginx`
   `condition: service_healthy` change plus re-enabling the dev healthcheck; the `start_period` reduction the input
   bundles here achieves nothing and should be dropped.
4. **The schema-bootstrap guard (TOPO-004) and the gate coverage that would have caught it (TOPO-007)** — in that
   order, unchanged. **Correction to the input:** widening the ruff gate is a two-part change, not a one-line one.
   `mypy src/ alembic/env.py` is clean and can go in immediately; `ruff check … alembic/` must first fix or exclude
   the four pre-existing `UP007`/`UP035` violations in `alembic/versions/`, or the gate lands red.
5. **The entry-layer move (TOPO-006)** is independent and can run in parallel with any of the above. One dependency
   the input does not name: the service method it proposes needs the repository to set `force_password_change`,
   which the route currently reaches directly.
6. **(new, from the validation) The `_FILE`-suffix heuristic in `config.py:65-66`.** Independent of every step,
   two lines, and it removes a spurious warning from every surface of every tier. It is TOPO-007's secondary
   recommendation and it has no reason to wait behind the gate change.

## Rollout Safety

Steps 1, 2 and 6 change observable behaviour. **Step 1** alters the state a client polls for: rows that today sit
at `uploaded` after a failure will begin reporting `failed` with a populated `error_code`. Anything that treats
`uploaded` as "still in flight" must handle `failed` — the frontend already renders terminal states from this row
(`services/file_cleanup.py:141,154` reads `[COMPLETED, FAILED]` as terminal), so the upload polling code should be
re-read before shipping rather than assumed. The fix also makes previously-dead code execute, so any handler that
assumed `_process_csv_file_async` only ever returns on success must be re-checked; the exception still propagates
exactly as before, so callers see no change there. Revert by restoring the `raise`; the failure path returns to its
current behaviour with no data migration.

**Step 2** is the larger blast radius and the input's own staging advice is correct: moving submission to RQ
changes where processing runs, so the temp-file path must be identical from both processes (it is — both mount
`app_data` at `/app/data`, `docker-compose.yml:200-201`), the worker must run as a user that can write there
(uid 100 `app` in the prod image, `docker/Dockerfile:172`), and the healthcheck on `rq-worker` must change from a
Redis ping to a worker-heartbeat check, because a Redis ping cannot distinguish a live worker from a dead one. The
input's staging plan — run the RQ path beside the in-process one for one deployment and compare `processing_logs`
outcomes before removing the in-process path — is sound, and `processing_logs` is the right reconciliation
surface. **Correction:** in the dev tier `rq-worker` has no healthcheck at all
(`docker-compose.override.yml:151-152`, confirmed at runtime), so a heartbeat check must be *added*, not
*changed*, there. Do not ship steps 1 and 2 in the same release.

**Step 6** changes only what is logged, and the warning it removes is the input to every boot's startup preamble.
Revert is a one-line revert of the suffix match.

Steps 3, 4 and 5 change no request-path behaviour. The loop lease adds a Redis key with a TTL; the
`/health/detailed` response gains a component entry, which is additive but is a public endpoint — check that no
consumer asserts an exact key set on `components`. Step 3's `nginx` change alters when the proxy starts serving,
so a failed app healthcheck now blocks `nginx` from starting at all where it previously started and 502'd; that is
the intended effect, and the revert is the short-form `depends_on`.

## Appendices

**A. Coverage ledger.** Blocks of `.kilo/commands/audit/phases/01-audit-process-architecture.md` and the item
count each reached under validation.

| Block | Zone | Examined | Reached |
|---|---|---|---|
| 1. Component inventory / tier topology | TOPO-005 | 7 components × 3 tiers, derived from what each tier starts | 7 of 7 enumerated; 3 of 3 tiers |
| 2. Entry surfaces / deferred work | TOPO-007 | 5 declared entry surfaces, all load-time behaviour | 5 of 5; 2 of 2 load-time side effects |
| 3. Startup order / pre-serve interval | TOPO-008 | 1 interval measured live; 3 declared edges | 1 of 1 measured; 3 of 3 edges |
| 4. Termination / what in-flight work leaves | TOPO-001, TOPO-003 | 1 stop signal observed mid-operation; 1 unreconciled work record | 1 of 1 observed (own restart); 1 of 1 |
| 5. Periodic loop / work-submission mechanisms | TOPO-002, TOPO-005 | 2 submission mechanisms; 1 periodic loop | 2 of 2 with a reached/un-reached verdict; 1 of 1 |
| 6. Schema bootstrap gate | TOPO-004 | 4 schema-mutating paths; 1 guard | 4 of 4; 1 of 1 — **destructive branch not observed executing** |
| 7. Shared state / per-process by construction | TOPO-003 | 3 shared surfaces classified; 4 per-process structures | 3 of 3; 4 of 4 |
| 8. Entry-layer discipline / dependency direction | TOPO-006 | 11 transport modules; 1 back-import sweep | 11 of 11 mapped; 0 back-imports, 0 cycles |
| 9. Route surface assembly / reachability | *(no finding filed)* | `/openapi.json` read live | 60 operations over 43 paths, 1 namespace collision check |

**B. What could not be settled, and why.**

- **The production tier was not started.** It requires a populated `.env` with real secrets and a prior
  `npm run build`, neither available here. TOPO-005's four-process boot and TOPO-008's production-tier behaviour
  are therefore established from the shipped `docker/Dockerfile:179` and `docker-compose.yml:135-140` plus the
  dev-tier measurement, not from an observed four-process boot. The residue is a *lower* bound.
- **The destructive branch of `recreate_test_database` was not observed executing.** The only running tier that arms
  `RECREATE_TEST_DB` is the test tier, whose harness bypasses the lifespan (`conftest.py:559-560`, `httpx.ASGITransport`)
  and whose `test-app` runs `tail -f /dev/null` rather than the image's own CMD. The finding rests on the static
  proof plus the reachability shown by `docker-compose.test.yml:129,147`. The input's stated limits are correct
  and complete on this point.
- **The startup-window measurement is a sample.** Two independent measurements exist — the input's 40 258 ms over
  224 attempts and this validation's 57 443 ms over 289 attempts, both with a ~150 ms poll. The rate is
  ~180 ms per attempt in both. The window's magnitude is dev-reloader-dominated and the app's own preconditions
  were 1.07 s in this run against the input's 1.38 s.
- **`start_period` semantics were settled, not left open.** Two throwaway containers on this host's Docker Engine
  29.8.0 established both cases directly; see TOPO-008.

**C. Namespace ruling (block 7).** Phase 01 declares its prefix in its own report-output contract
(`01-audit-process-architecture.md:134`): `TOPO-`, "check for a collision before minting an identifier; report the
collision rather than creating a second namespace". **Declared:** `TOPO-`. **Minted:** `TOPO-001` … `TOPO-008`,
contiguous, no gaps, no duplicates. **In-source markers:** a repo-wide search for `TOPO-\d` returns 35 matches, all
of them inside `.ai/audit/01-process-architecture/findings.md` — **zero** in `src/`, `tests/`, `alembic/`,
`docker/`, `docs/` or any configuration file. **Compound form:** the shared template's front-matter `phase:` value
is `NN-phase-name` and enumerates no prefix, so the compound resolves as `<phase-dir>/<PREFIX>-<NNN>`; this report
therefore carries `TOPO-` under `.ai/audit/99-validation/`. **Reuse across phases:** none — phase 02 declares and
mints `CFG-`, and the two sets are disjoint, with the phase-02 validation (`CFG-001`…`CFG-010`) also ruling
`CFG-` as its own. **Ruling:** reuse the declared namespace. There is no in-source provenance to migrate and none
to retire, because no marker was ever written into shipped code, configuration, tests or documentation.

**D. Template conformance (block 8), as the input stands.** The shared template
(`.ai/audit/templates/audit-findings.md`) mandates six front-matter fields and, per finding, "all five fields"
while enumerating six. The input sets all six front-matter fields and the values are honest: `phase:
01-process-architecture` names the phase that wrote it, `executor: auditor`, `executor` is not `validator`, and
`findings: 8` with `by-severity: HIGH 2 / MEDIUM 4 / LOW 2` agrees with the eight bodies — the tally check the
sibling phase-02 validation failed. **Every** finding carries all six mandated fields, none omitted, none renamed.
**Every** zone is the block title of the audited phase's own file quoted verbatim, with no paraphrase and none
absent: block 1 → TOPO-005, block 2 → TOPO-007, block 3 → TOPO-008, block 4 → TOPO-001, block 5 → TOPO-002,
block 6 → TOPO-004, block 7 → TOPO-003, block 8 → TOPO-006. The reserved empty-state string does not apply — the
input has findings and does not pad. All seven template sections are present. One template defect is recorded once
here and not re-recorded per report: the template says "No finding without all five fields" and then enumerates
six.

## Validation-Level Findings

Defects in the audit itself, on the validation scale. Separate section because the two scales share a `Severity`
column. None of these changes a finding's verdict or band; each corrects something a reader would otherwise act on
wrongly.

### VAL-001 — TOPO-006 asserts that the dependency-injection layer executes a query; the cited lines are a docstring example

**Severity** — MEDIUM

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — TOPO-006's Observation ends: "`api/deps.py:112-113` runs `db.execute(select(User))` in the
dependency-injection layer." Lines 112-113 are inside the `Example:` block of `get_db_dependency`'s docstring
(`deps.py:109-114`). The function's body is `async with get_session() as db: yield db` (`:115-116`) — it yields a
session and executes nothing. The DI layer runs no query of its own.

**Evidence** — `deps.py:101-116` read directly. A repo-wide search for `db.execute` in `deps.py` returns only the
docstring occurrence.

**Consequence** — A wrong approval: a claim about the executing path sourced from a documentation line, presented
as a fact about what the layer does. A reader who accepts it will add the DI layer to the set of places that must
be de-commissioned, and will find nothing there. The finding's substance — the route owning the commit boundary
and the non-transactional Redis write — is unaffected and re-derives from `admin.py:305-345` alone.

**Recommendation** — Strike the sentence. The finding stands on the ten `db.commit()` sites, the eleven
`db.rollback()` sites and the `admin.py:321`/`:330`/`:340` ordering.

### VAL-002 — TOPO-007's primary recommendation turns a green gate red if executed as written

**Severity** — MEDIUM

**Zone** — "5. Whether the Recommendation Can Be Carried Out"

**Observation** — TOPO-007 recommends `ruff check src/ tests/ alembic/` and `mypy src/ alembic/env.py`. I ran both
against the excluded paths. `mypy --no-incremental alembic/env.py` returns **Success: no issues found in 1 source
file** — that half is free. `ruff check alembic/` returns **4 errors**, all in one revision file:
`alembic/versions/20250915_0004_*.py:1,3,10,12` (`UP035` deprecated `typing` import, `UP007` `Optional`/`Union`).

**Evidence** — The two commands above, run in the app image through the documented compose entry point
(`docker compose -p mkobi -f docker/docker-compose.yml -f docker/docker-compose.override.yml --env-file .env run
--rm --no-deps app …`), exit code 1 for ruff, 0 for mypy.

**Consequence** — A recommendation the reader must repair before acting: taken literally it is a one-commit change
that lands the lint gate red, and a team under delivery pressure will revert the gate change rather than fix four
style violations in a file the finding is not about. The finding itself is correct and its band is right.

**Recommendation** — Split the change. Add `alembic/env.py` to the mypy path now. For ruff, add `alembic/env.py`
specifically, and either fix the four `UP007`/`UP035` violations or add `alembic/versions/` to the exclude list
alongside the existing `pyproject.toml:169` mypy exclusion — the entry surface the finding is about is
`alembic/env.py`, not the generated revisions.

### VAL-003 — Three quotes and one line anchor in the input do not match the artefacts they name

**Severity** — LOW

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — Four small mismatches, none load-bearing. (a) TOPO-005 quotes the loop's start line as
`Started stale processing cleanup task (interval=300s, timeout=30m)`; the emitted text is `Starting …`
(`data_worker.py:917-919`). (b) TOPO-004 cites `docker-compose.test.yml:93` as the `ENV: test` trigger on
`test-app`; line 93 is `test-migrate`'s, and `test-app`'s is `:129`. (c) TOPO-004 calls `docker/Dockerfile:151`
"the app image's own `CMD`"; line 151 is the **test** target's `["pytest","tests/","-v"]`, the app target's being
`:179`. (d) TOPO-006's rollback count reads as one; the pattern returns eleven across `api/routes/`, of which
`dashboards_filters.py` has none in either `except` block — which is the point the finding makes, and it survives.

**Evidence** — Each line read directly at the anchor named; (a) from this validator's own restart log at 10:15:32,
(b)–(d) from the two compose files, the Dockerfile and the two route modules.

**Consequence** — Drift with no remediation consequence today: every underlying claim re-derives as true, so no
reader is misled about the system. Recorded because (b) and (c) are the kind of anchor a remediator opens, and both
name a different service or image stage than the sentence around them claims.

**Recommendation** — Correct the four, as listed.

### VAL-004 — TOPO-004's stated trigger distance understates present state

**Severity** — LOW

**Zone** — "3. The Grade against the Audited Phase's Own Rubric"

**Observation** — The input's Consequence reads "The store is one setting away from being destroyed by every
process that starts. **In the test tier it is already armed**". Both halves are true and the second makes the first
retrospective: `docker-compose.test.yml:129` and `:147` set both triggers today, so the setting is not one step
away, it is set, and what keeps the drop from firing is the accident that `test-app` runs `tail -f /dev/null`
rather than the image's CMD.

**Evidence** — `docker-compose.test.yml:126-152` read directly; `Dockerfile:151` read directly.

**Consequence** — The finding's blast radius is correctly stated and its band is unaffected — in fact the
observation makes the case for CRITICAL rather than weakening it, which is why the band is recorded as upheld at
the top of HIGH with the proximity noted. Recorded because "one setting away" understates present state: the armed
condition is the current state of the test tier.

**Recommendation** — Re-word to "armed in the test tier today; the only thing preventing the drop is that
`test-app` runs `tail -f /dev/null` rather than the image's `CMD`".

### VAL-005 — Two recommendations offer alternatives where the contract expects one executable action

**Severity** — LOW

**Zone** — "5. Whether the Recommendation Can Be Carried Out"

**Observation** — TOPO-002's recommendation offers "Either (a) point the upload path at `rq.Queue(...).enqueue(…)`
… or (b) delete the `rq-worker` service, the Redis queue wiring and `rq_worker_wrapper.py`". TOPO-005's offers a
Redis lease "If the four workers are not wanted at all, drop `--workers 4`". Both name real targets and both
alternatives are individually executable; neither tells a reader which to do.

**Evidence** — `.ai/audit/01-process-architecture/findings.md:118-124` and `:259-266`.

**Consequence** — No remediation consequence: the input's Cross-Finding Analysis and Roadmap both resolve the first
decision into a single step (roadmap step 2), so the ambiguity does not propagate. Recorded because a
recommendation carrying alternatives is substantiated-but-unusable on its own terms, and a reader who takes the
finding without the report has no starting instruction.

**Recommendation** — State the chosen option in the Recommendation itself, with the alternative as a recorded
rationale for the choice. TOPO-002's own analysis already prefers (a).

### VAL-006 — TOPO-008's remedy is built on a `start_period` mechanism that does not exist

**Severity** — LOW

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — TOPO-008 states that with `start_period: 40s` "for the first 40 seconds Docker reports the
container healthy without a single successful probe result", and recommends reducing `start_period` to 10 s "so the
40-second pre-verdict window disappears". Direct experiment on this host's Docker Engine 29.8.0 refutes both: a
container whose probe always fails reports `starting` at t=8 s and t=28 s under `start_period: 40s`, and a
container whose probe succeeds reports `healthy` at t=8 s under the same `start_period`.

**Evidence** — Two `docker run` probes with `--health-start-period 40s --health-interval 30s --health-retries 3`,
inspected at t=8 s and t=28 s; probe log shows five consecutive `ExitCode: 1` in the failing case. Docker's
`HEALTHCHECK` documentation: the status "is initially `starting`", and "if a health check succeeds during the start
period, the container is considered started".

**Consequence** — The measured 57-second window stands and the finding is re-graded up for it (see TOPO-008), but
half the recommendation would achieve nothing, and the Consequence sentence about an orchestrator routing traffic
to a never-probed container does not hold. A reader who applied only the `start_period` half would believe the
problem was fixed.

**Recommendation** — Drop the `start_period` reduction. Keep the `nginx` long-form `depends_on` change and the
dev-healthcheck re-enable; those two are what the measurement supports.

### VAL-007 — The Cross-Finding Analysis denies a dependency the Roadmap relies on

**Severity** — LOW

**Zone** — "6. Cross-Phase Conflict, Ownership and Merge"

**Observation** — Recorded in full under Cross-Finding Analysis above. TOPO-004, TOPO-007 and TOPO-008 are called
independent there; TOPO-004's guard lives in the file TOPO-007 is about, and the Roadmap sequences them on the
dependency that sentence denies.

**Evidence** — `.ai/audit/01-process-architecture/findings.md:434` against `:449-451`; `alembic/env.py:115-117`
against `Makefile.ps1:222,230` and `pyproject.toml:169`.

**Consequence** — Drift with no remediation consequence today, because the Roadmap carries the correct order and is
the operative section. Recorded because a reader triaging by cause rather than by roadmap would batch the three
together and run the gate change first.

**Recommendation** — Replace "independent" with the dependency the Roadmap already states.

### VAL-008 — The shared template says "five fields" and enumerates six

**Severity** — LOW

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — `.ai/audit/templates/audit-findings.md:24` reads "No finding without all five fields", and
`:28-45` then enumerates six: `Severity`, `Zone`, `Observation`, `Evidence`, `Consequence`, `Recommendation`. The
input report carries all six in all eight findings and this validation adds a seventh, `Verdict`, which the
template does not enumerate and this phase's output contract requires.

**Evidence** — The template read directly at both anchors. The sibling phase-02 validation recorded the same
template defect as its own VAL-009; it is recorded once here rather than duplicated per report. The `VAL-` prefix
is shared across the set by the output contract, so the two reports' identifier spaces overlap at `VAL-001`–`VAL-009`;
this is a property of the contract, not a defect in either report, and it is noted rather than resolved because the
namespace ruling is block 7's and was made per report.

**Consequence** — A report written strictly to the template's count would drop one mandated field; the count is
wrong, not the field list. No reader is misled about the system.

**Recommendation** — Correct "five" to "six" in the template. Not repaired here: this phase never repairs a shared
artefact from inside a per-phase run.

## Residual

*Fixed residual footer, carried by every validated report in this set.*

- **Blocks examined:** 9 of 9 declared blocks of the audited phase, each reached by at least one finding or by an
  explicit clean verdict (block 9: read, no finding filed).
- **Findings adjudicated:** 8 of 8. Disposition tally — 7 confirmed, 1 re-graded (TOPO-008, LOW → MEDIUM), 0
  re-typed, 0 merged, 0 not substantiated, 0 unsettled. Every finding's verdict matches its row above.
- **Validation-level findings:** 8 (VAL-001 … VAL-008), of which 2 MEDIUM and 6 LOW. The `VAL-` prefix is
  shared with the sibling phase-02 report by the output contract, so the two identifier spaces overlap.
- **Claims left unsettled, with reason:** the production tier was not started (real secrets and a prior
  `npm run build` unavailable), so TOPO-005's four-process boot and TOPO-008's production-tier behaviour rest on
  the shipped definitions plus the dev-tier measurement; and the destructive branch of `recreate_test_database` was
  not observed executing, because the only running tier that arms it bypasses the lifespan. Both residuals are
  limits on the input's evidence, not on its verdicts, and both are lower bounds. No other claim was left open.
