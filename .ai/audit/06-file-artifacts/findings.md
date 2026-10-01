---
phase: 06-file-artifacts
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 9
by-severity:
  CRITICAL: 0
  HIGH: 3
  MEDIUM: 4
  LOW: 2
baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268
baseline-dirty: true
---

# Phase 06 — Findings

## Summary

The stored-file path was examined end to end: the three identities an accepted
upload carries, the area it lives in and what bounds that area, reconciliation
between the store and the records in both directions, every removal operation
and what a failed removal leaves behind, the one-time secret held in Redis, and
the built interface bundle as a served artefact. All eight blocks were reached at
runtime against the dev stack (`.\Makefile.ps1 up`, project `mkobi`): artefacts
were uploaded over HTTP with deliberately disagreeing names and content, the
loader and the queue were driven directly, the bundle was exercised in three
presence states through the real ASGI app, and the reclaimer was run four times
concurrently over the shared volume. The most consequential thing found is that
the caller's filename alone decides how a stored artefact is parsed while its
bytes decide only whether it is accepted: a plain CSV renamed `.csv.gz` is
admitted, stored under a false gzip claim, and the resulting failure is a
`BaseException` that every handler in the chain misses — which permanently kills
the queue consumer in the process that served the upload, so a quarter of the
upload surface stops working and never recovers. Nine findings, three of them
HIGH; no CRITICAL band is claimed, because nothing here exposes credential
material or destroys content that a durable record names.

## Findings

### ART-001 — A renamed upload kills the only process that reclaims artefacts, and the volume of damage grows with each incident

**Severity** — HIGH

**Zone** — "1. The accepted artefact's identity: what it is called, what its name claims, and what its bytes are"

**Observation** — Three identities exist for an accepted upload and no component
reconciles them. The name the caller supplied decides the stored name and the
parser: `process_upload_with_session` derives the stored extension from the
caller's filename (`services/file_processing.py:208-212`, via
`detect_file_type`, `data/loaders/loader.py:44-67`) and writes
`{log.id}{ext}`, and `CSVLoader` then chooses between `gzip.open` and a plain
read purely from the stored name (`data/loaders/loader.py:295-302` and
`:211-215`). The bytes decide admission only:
`validate_mime_type` detects from content and accepts anything in
`MimeTypeEnum` (`services/file_processing.py:85-94`), and that set contains
`application/gzip` *and* `text/csv`, so a real CSV body satisfies it under the
name `data.csv.gz`. Nothing compares the two verdicts. The failure the mismatch
produces is `pyo3_runtime.PanicException`, whose MRO is
`PanicException -> BaseException -> object`: it is not an `Exception`, so it is
missed by `CSVLoader.load_csv`'s handler (`loader.py:164`), by
`_process_csv_file_async`'s two handlers (`workers/data_worker.py:556` and
`:588`), by `TaskQueue.process_next` (`core/task_queue.py:96`) and by the
`queue_worker` loop in the lifespan (`app.py:131-141`). That loop is created
once and never supervised, so the task ends and the process stops consuming its
queue for the remaining life of the container. The reverse mismatch is benign:
Polars transparently decompresses gzip bytes under a `.csv` name, so the
one-way failure is specifically the false *gzip* claim.

**Evidence** — Reproduced in the `app` container against the running stack.
Four-case loader probe (`CSVLoader().load_csv` on each): `p1.csv.gz` holding a
plain CSV body → `RAISED pyo3_runtime.PanicException mro=['PanicException',
'BaseException', 'object']`; the same bytes as `p1.csv` → `LOADED shape=(3, 2)
cols=['category', 'sales']`; real gzip as `ok1.csv.gz` → loaded. End to end over
HTTP, `POST /api/v1/upload/{id}` with `("disguised.csv.gz", plain_csv, "application/gzip")`
returned **201** and the file was stored as
`/app/data/tmp_uploads/2b29529f-….csv.gz`; libmagic had detected
`text/csv` for those bytes, which is allowed. Consumer-death probe using the
verbatim `app.py` loop shape around a real `TaskQueue`: after one poisoned job
`consumer_task_done_after_first_job: True`,
`consumer_raised: pyo3_runtime.PanicException`, and a second enqueued job was
never processed (`second_job_processed: False`). Production multiplicity is
`CMD ["uvicorn", …, "--workers", "4"]` (`docker/Dockerfile:179`).

**Consequence** — One upload named `*.csv.gz` whose body is not gzip disables
background processing in the uvicorn process that served it, for the life of that
process. Because the deployment runs four worker processes behind one container,
a quarter of subsequent uploads are enqueued into a queue nobody drains, and the
proportion only recovers if that worker is restarted. Each incident also leaves
its artefact on disk (the unlink that would have run lives inside the handler
that was missed) with the record left at `uploaded`, which is the same state
Phase 01 filed for lost jobs. The uploader receives 201 and has no signal that
anything failed.

**Recommendation** — Decide the stored extension from the detected content
rather than from the caller's filename, so the stored name cannot claim a type
the bytes do not support: have `validate_mime_type` return the detected type and
pass it to `process_upload_with_session` instead of calling `detect_file_type`
on the filename. Independently, make the loader boundary total — `CSVLoader`
should translate any reader failure, including `BaseException`, into the
`ValueError` its own docstring promises, and `app.py` should wrap the
`queue_worker` body in `BaseException` (or supervise the task) so one job can
never end the consumer. Remediation blocker: `tests/test_data_service.py:641-657`
asserts that a name/content mismatch is rejected with "Detected MIME type", and
it passes only because its sample body (`"This is not gzipped content but
claims to be gzip"`) is detected as `text/plain`; a comma-containing body takes
the admission path instead. That test encodes the intent and must be re-pointed
at the sample that actually matters.

### ART-002 — Neither direction of store-versus-record divergence is detectable, because the record never names the artefact

**Severity** — HIGH

**Zone** — "3. Reconciliation between stored artefacts and stored records, in both directions, and what is exempt"

**Observation** — `ProcessingLog` has columns for status, message, timestamps and
error code and **no column for a file name or path**
(`db/models/processing_logs.py:30-72`). The only link between a record and an
artefact is the convention that `ProcessingLog.id` is the stem of
`{id}.csv` or `{id}.csv.gz`, and three components apply three different rules to
that convention without any of them enforcing agreement: the producer writes
`{log.id}{ext}` (`services/file_processing.py:235`), `find_task_file` globs
`f"{task_id}.csv*"` and raises on multiple matches
(`services/file_processing.py:299-307`), and `cleanup_task_files` globs
`f"*{task_id}*.csv*"` (`services/file_cleanup.py:36`). Of the three selectors
only the producer and the age sweep are reachable from the deployed API:
`find_task_file` is called from `DataService.trigger_processing`
(`services/data_service.py:279`) and no route calls `trigger_processing`, and
`cleanup_task_files` has no caller in `src/` at all. Direction one (an artefact
no record names) is therefore covered only by
`cleanup_stale_temp_files`, which is a 24-hour age sweep that cannot distinguish
an orphan from an upload still in flight and runs only during process startup
(`db/starter.py:180`). Direction two (a record naming an artefact that is not
there) has no detector: the only component that would notice is the unreachable
`find_task_file`, and the two status surfaces read the database only. The caller
cannot see the gap either — `ProcessingLog` has nowhere to keep the name, and
`get_processing_status` fills the response's `filename` field from `log.message`
(`services/data_service.py:336`, and the same substitution at `:306`).

**Evidence** — Read at runtime: `GET /api/v1/upload/status/2b29529f-…` returned
`{"filename": "Worker restart: orphaned UPLOADED entry detected", …,
"message": "Worker restart: orphaned UPLOADED entry detected"}` — the field
named `filename` carries the status sentence, and the name the uploader
supplied (`disguised.csv.gz`) exists nowhere after the 201 response. The same
moment the store held two artefacts and the table held three records, with no
field in either that relates them; the file for task `9f87bd09-…` had already
been consumed and removed, and nothing in the system could report that. Grep for
`trigger_processing` returns the protocol declaration
(`interfaces/service_interfaces.py:404`), the implementation
(`services/data_service.py:255`) and tests only — no route.

**Consequence** — The store and the records cannot be compared in either
direction, by any component, today. An artefact lost to a crash between the
rename and the commit, to volume eviction, or to an operator's `rm` leaves a
record that still reads `completed` or `failed` and no signal anywhere; the
dashboard continues to serve whatever aggregates were last committed. An
artefact stranded the other way leaves a record that never leaves `uploaded`
while the file sits on the volume, and no component can say so. The one code
path built to resolve a task's artefact by name is unreachable, so the design's
own retry mechanism cannot work even if a route is added without also changing
the retention model.

**Recommendation** — Pick one of the two coherent models and make it explicit,
because the current mix is what makes both directions undetectable. If the
artefact is scratch space (the design intent of deleting it on every path), then
remove the two name-based selectors rather than leave them disagreeing, and add
one reconciliation pass at startup that walks the area, derives the record id
from each name, and reports — not deletes — any artefact whose record is
absent, terminal, or older than the sweep threshold. If a task must be
re-runnable, store the artefact name on `ProcessingLog` (one nullable column, one
migration) and make `find_task_file` the only selector. Do not add a third
glob. Whichever is chosen, populate `ProcessingStatusResponse.filename` from a
real name or drop the field; returning `log.message` under that key is the
symptom that made the gap visible.

### ART-003 — The in-flight area is bounded by age only, and shares its volume with the application log

**Severity** — MEDIUM

**Zone** — "2. Residence of an accepted artefact, and what bounds it"

**Observation** — The control inventory, classified by what each control actually
bounds: *bytes, per request* — `config.max_file_size`
(`UPLOAD__MAX_FILE_SIZE_MB`, default 100 MB), enforced twice, on the declared
`Content-Length` and again on cumulative streamed bytes
(`api/routes/upload.py:129-141` and `:181-196`); *count, per caller per hour* —
the upload rate limiter, `max_attempts=100, ttl=3600` keyed on
`f"upload:{current_user.id}"` (`api/routes/upload.py:148-152`); *time* — the
startup sweep at `STALE_FILE_THRESHOLD_HOURS`, default 24
(`services/file_cleanup.py:46-106` via `db/starter.py:180`); *nothing* — the
in-flight `upload_{uuid4}_{name}` files between the `finally` in the route
(`upload.py:226-231`) and the rename, and the count and total size of the area at
any instant. There is no count bound and no byte bound on the area: the rate
limiter's 100 requests per hour multiply against a 100 MB per-request ceiling,
and the sweep is time-based only, so a time bound does not bound a rate. The area
is `/app/data/tmp_uploads` on the `app_data` named volume
(`docker/docker-compose.yml:113` and `:132`), and that same volume carries
`/app/data/logs/app.log`, opened by a `RotatingFileHandler` of 10 MB × 5 backups
(`core/logging_config.py:111-122`, wired at `docker/docker-compose.yml:114`).
The container is `read_only: true` with no tmpfs, so the volume is the only
writable space, and `/app/data/uploads` — created in all three image stages
(`docker/Dockerfile:95`, `:117`, `:143`) — is written by no code in the project.

**Evidence** — Read from the running container: `UPLOAD__TEMP_DIR =
'/app/data/tmp_uploads'`, `stale_file_threshold_hours = 24`, `max_file_size =
104857600`; `ls -la /app/data/tmp_uploads` and `ls -la /app/data` confirm the
uploads, logs and tmp_uploads directories are siblings on the one volume.
Admission controls were read, not exercised — they belong to Phase 05.

**Consequence** — Occupancy of the in-flight area is bounded by nothing but wall
time. Sustained uploading at the permitted rate fills the shared volume, and
because the application log lives on that volume, exhaustion does not stop one
upload: `RotatingFileHandler` can no longer rotate or write, `logging` swallows
the `OSError` through `handleError`, and the process continues serving with no
file log at all, while `upload_dir.mkdir` and `file_path.replace` start raising
`OSError` into 500s. The 24-hour threshold then means every stranded artefact is
retained for at least a day after the disk pressure that stranded it.

**Recommendation** — Put a byte ceiling on the area itself, not only on the
request: before accepting, compare the directory's current size against a
configured budget and return `ErrorCode.FILE_TOO_LARGE` (or a dedicated code)
when the budget is exceeded. Move `LOGGING__LOG_FILE` off the artefact volume —
a dedicated volume or stdout-only shipping — so artefact pressure cannot silence
observability. Run the sweep on the existing periodic task rather than only at
startup so the area is bounded while a long-lived process runs, and drop the
never-written `/app/data/uploads` from the image stages once the intent is
settled.

### ART-004 — The artefact is destroyed on every terminal path, including the failure path and before the work derived from it is committed

**Severity** — HIGH

**Zone** — "4. Removal of an artefact, and the record of a removal that failed"

**Observation** — The removal inventory per audience. The uploader has none: no
endpoint deletes an upload, a task, or a processing record. The administrator has
none. The system has four: the route's `finally` unlinks the in-flight file
(`api/routes/upload.py:229-231`); the worker unlinks the accepted artefact on the
success path, *inside* the transaction, before the status write and before the
commit (`workers/data_worker.py:532-534`); the worker unlinks it again on every
failure path, inside the handler that runs before the re-raise
(`workers/data_worker.py:561-571` and `:593-602`); and
`cleanup_stale_temp_files` deletes by age at startup. The consequence of the
second and third is that the only copy of the uploaded data is removed whether
the run succeeded or failed, and on the success path it is removed before the
transaction that stores what was derived from it commits. There is no reverse
path: `DataService.trigger_processing`, the only component built to re-run a
task, depends on the artefact still being present, which the two unlinks make
impossible for any task that has reached a terminal state — and it has no route.

**Evidence** — Read at `workers/data_worker.py:526-543`: `_store_aggregates` is
awaited, then `if file_path.exists(): file_path.unlink`, then the `COMPLETED`
status update, all inside the `async with session.begin()` block opened at
`:585`; the commit happens on block exit. The failure path at `:593-602` unlinks
and then `raise  # Re-raise inside transaction block triggers rollback`, so the
source file is destroyed on the rollback path too. Observed during the
end-to-end probe: the artefact for task `9f87bd09-…` was gone from
`/app/data/tmp_uploads` after the worker ran, while the record for that task
never received a `FAILED` write.

**Consequence** — A failed ingestion is not re-runnable from anything the system
holds. The uploaded bytes are gone, the aggregates were rolled back, and the
operator's only recourse is to ask the uploader for the file again — the retry
path in the code cannot work for any task that has already run. On the success
path the removal is ordered before the commit, so a crash or a commit failure in
the window between the `unlink` and the commit destroys the source while leaving
no aggregates and no `FAILED` record, and nothing reports the loss. The set of
accepted artefacts is not append-only, but neither is the removal of one
recorded: there is no record that the file was ever there.

**Recommendation** — Move both unlinks out of the transaction and after it: on
the success path, commit first and unlink after commit returns; on the failure
path, keep the file when the failure is retryable and unlink only when it is not,
recording which. If a task is meant to be re-runnable, that means keeping the
artefact past the terminal state and giving it an explicit retention and an
explicit user-initiated removal; if it is not, delete `trigger_processing` and
`find_task_file` so the codebase stops implying a retry that cannot work. This
is adjacent to, not a duplicate of, Phase 05's DP-001: DP-001 is the ordering of
the *rename* against the *record commit* on the acceptance path, whereas this is
the ordering of the *unlink* against the *derived-data commit* and the
unconditional removal on the failure path. They should be remediated in the same
commit to the worker's ordering, not merged into one finding.

### ART-005 — A failed removal is a log line and nothing else, and the reclaimer that could retry it never runs again

**Severity** — MEDIUM

**Zone** — "4. Removal of an artefact, and the record of a removal that failed"

**Observation** — Every removal-failure path in the project terminates in a log
call and nothing else. `cleanup_stale_temp_files` wraps each file in
`except Exception as e: logger.error("Error processing file %s: %s", …)`
(`services/file_cleanup.py:100-101`); `cleanup_task_files` does the same
(`:42-43`); the worker's error-path unlink logs
`logger.warning("Failed to clean up temp file: …", exc_info=True)`
(`workers/data_worker.py:565-570`, `:594-600`). There is no table, no column, no
counter and no metric: nothing reads those lines, nothing aggregates them, nothing
alerts on them, and no retention attaches to them beyond whatever the log
rotation provides. The retry that would exist in any case does not: the sweep
that can pick a failed removal up again is invoked exactly once, from
`DatabaseStarter.startup()` (`db/starter.py:180`), so a removal that fails
because the volume was momentarily full, the file was busy, or permissions were
wrong is never retried until a human restarts a process. The one function whose
entire job is removing a specific task's artefact has no caller in `src/`.

**Evidence** — The four handlers are at the lines cited; there is no other
`unlink`/`rmtree` in the project outside tests
(`grep 'unlink|rmtree|shutil\.' src/`). Runtime: the four-sweeper reproduction in
the appendix produced `ERROR … Error processing file
/app/data/tmp_uploads/upload_deadbeef-…_leftover.csv: [Errno 2] No such file or
directory` — a benign collision logged at ERROR, indistinguishable in shape from
a genuine `EACCES`. Remediation blocker: `tests/test_upload_api.py:731`
(`test_cleanup_task_files_called_during_processing`) is named for a function no
production path calls; its body drives `process_csv_background` and asserts on
the directory, so the test documents a call that does not exist. Either the
function is meant to be the reclaimer — in which case the worker should call it
and the test's intent becomes true — or it is meant to be gone, in which case the
test name and docstring are the defect.

**Consequence** — The only signal that a stored artefact could not be removed is
a line in a rotating log that an operator has to go looking for, with no
retention and no alert. In practice the artefact then sits on the volume until
the next process start, and if the failure was caused by the volume being full,
the artefact is what keeps it full.

**Recommendation** — Give removal outcomes a home: one nullable `cleanup_error`
column on `ProcessingLog` written when the unlink fails, surfaced in the existing
`GET /api/v1/upload/status/{task_id}` payload and in the admin log list, so the
failure is queryable rather than scrollable. Move the sweep onto the periodic
task that already exists (`start_stale_processing_cleanup_task`,
`app.py:120-125`) so a failed removal is retried within the retention window.
Resolve `cleanup_task_files` in the same change as ART-004: call it from the
worker or delete it and its test.

### ART-006 — Approval reports a retrievable one-time password whether or not the store accepted it, and the absent secret is reported exactly like a consumed one

**Severity** — MEDIUM

**Zone** — "5. A one-time secret held outside the database: how it is created, how it is collected once, and what a failure at each step leaves behind"

**Observation** — The lifecycle: `approve_registration_request_admin_endpoint`
generates a 16-character password, creates the user with its bcrypt hash, sets
`force_password_change=True`, mints `retrieval_token = str(uuid4())`, calls
`temp_password_store.store(token, password)`, marks the request `APPROVED`,
commits, and returns `{"message": "Registration request approved", "user_id": …,
"retrieval_token": …}` (`api/routes/admin.py:305-336`). `store` writes
`SET temp_pwd:<token> <password> EX <TEMP_PASSWORD_TTL_SECONDS>` (default 86400,
`config.py:464`) and **fails open**: on any Redis error it logs and returns
without raising (`core/temp_password_store.py:47-48`). The approve endpoint does
not check anything, so when the write fails the response is byte-for-byte the
same: the request is `APPROVED`, the user exists with a password hash nobody
holds, and the admin holds a token. Nothing removes the secret at any event
other than collection: not user deletion, not request rejection, not a password
change; only the 24-hour TTL. On the collection side,
`retrieve_temp_password_admin_endpoint` maps every `None` to
`ErrorCode.NOT_FOUND` with the detail "Temporary password not found or already
retrieved" (`api/routes/admin.py:417-422`), and `retrieve` returns `None` both
when the key is absent and when the Redis pipeline raised
(`core/temp_password_store.py:73-75`) — and in the second case the secret is
still in Redis, so the caller is told the token is spent while it is not.

**Evidence** — The approve handler and the retrieval handler were read at the
lines cited; the fail-open store was read at `core/temp_password_store.py:47-48`
and is Phase 04's finding, cross-referenced here for the residue rather than
re-filed. Remediation blocker: `tests/core/test_temp_password_store.py:164-181`
(`test_store_fail_open_on_error`) asserts that `store` logs and does not raise,
so the fail-open behaviour is encoded in a shipped test and that test must change
with the fix. Phase 04's `force_password_change` finding (no server-side
consumer) is what makes the residue permanent rather than self-healing.

**Consequence** — A Redis outage at the moment of approval produces a
provisioned user whose password exists only as a hash, a registration request
marked `APPROVED`, and an admin response that says a one-time password is
retrievable. The failure surfaces only as a server log line, and when the admin
does retrieve, the answer — 404 "Temporary password not found or already
retrieved" — is identical to the answer for a token that was legitimately
collected. There is no state in the system that distinguishes "the secret was
never created" from "the secret was already used", so the provisioning failure
cannot be diagnosed from the API. The symmetric case is worse in one respect:
a collection that failed on a Redis error reports the same 404 while the secret
is still present and still collectable.

**Recommendation** — Make creation and collection report their own failures:
have `store` raise (or return a bool the endpoint checks) and answer
`ErrorCode.INTERNAL_ERROR` from the approve endpoint without marking the request
`APPROVED` — which means reordering the `store` call before the status update and
committing only after it succeeds, so the record and the secret cannot disagree.
Distinguish the two `None`s in `retrieve` by letting a Redis error surface as
`SERVICE_UNAVAILABLE` rather than `NOT_FOUND`, so a transient outage is not
reported as a spent token. Persist the `retrieval_token` on the registration
request row so a failed retrieval is diagnosable and a token can be revoked.
The fail-open assertion in `test_store_fail_open_on_error` is the blocker.

### ART-007 — The interface bundle's presence changes the route table, and the health surface calls a bundle unservable "available"

**Severity** — MEDIUM

**Zone** — "6. The built interface bundle as a served artefact: what is served from disk, and what changes when it is absent"

**Observation** — `_setup_static_files` resolves `Path("frontend/dist")` relative
to the process working directory and registers a catch-all mount at `/` only when
**both** the directory and `index.html` exist (`app.py:340-344`,
`:387-391`); otherwise it logs one warning and registers nothing
(`app.py:392-397`). A matched asset is served from disk, an unmatched path
returns `index.html` for client-side routing, and an unmatched `/api/` path
raises a bare 404 so the exception handler formats it
(`app.py:361-385`). So the bundle's presence decides the route table, not just
its content: with it, `/dashboards/abc` is 200 `text/html`; without it, the same
path is 404 `application/json`. The observer disagrees with the route table.
`/health/detailed` reports `static_files.status` from
`os.path.isdir("frontend/dist")` alone (`app.py:308-313`) — it does not check
`index.html`, which is the condition the mount actually requires. `/health`, the
endpoint the container `HEALTHCHECK` uses (`docker/Dockerfile:176-177`,
`docker/docker-compose.yml:142-143`), does not mention the bundle at all.

**Evidence** — Three presence states driven through the real ASGI application
inside the container, each with a fresh `create_app()` and a fresh working
directory. *Absent*: no mount at `/`; `/health/detailed` →
`{'status': 'unavailable', 'path': 'frontend/dist'}`; `GET /` → 404
`application/json`; `GET /dashboards/abc` → 404 `application/json`. *Present but
wrong* (`frontend/dist` exists, no `index.html`): **no mount at `/`**, byte-identical
route table to the absent case, but `/health/detailed` →
`{'status': 'available', 'path': 'frontend/dist'}` and `/health` → 200
`{"status":"healthy","database":"connected"}`. *Correct* (`dist` plus
`index.html`): `/` → 200 `text/html`, `/dashboards/abc` → 200 `text/html`,
`/assets/index-xyz.js` → 200 `text/javascript`, `/assets/missing.js` → 200
`text/html` (the SPA fallback swallows a missing asset), `/api/v1/nope` → 404
JSON. The words the monitoring observer receives are therefore `available` for a
bundle that cannot be served and `available` for one that can.

**Consequence** — A deployment whose `frontend/dist` exists but lacks
`index.html` — a partial or failed `npm run build`, a host directory mounted over
the image's copy, a partially copied layer — passes `HEALTHCHECK`, reports
`static_files: available`, and serves 404 JSON for every interface path. Nothing
in the shipped health surface distinguishes that from a working bundle, so the
failure is invisible to the orchestrator and to `/health/detailed`, and it is
indistinguishable from a backend outage only by the fact that the backend is
fine. The CWD-relative resolution adds a second path to the same state: a
process started from any directory other than the image's `/app` silently loses
the mount while the directory check still passes if a `frontend/dist` happens to
exist relative to that other directory.

**Recommendation** — Make the health check ask the same question the mount asks:
report `static_files` from a single helper that returns the resolved
`index.html` and have both `_setup_static_files` and `/health/detailed` call it,
so "available" means "the mount registered". Resolve the bundle from a
configured absolute path (`FRONTEND__DIST_DIR`, defaulting to
`Path(__file__).parents[2] / "frontend" / "dist"`) rather than from the process
CWD, and add `index.html` to the container `HEALTHCHECK` path so an unservable
bundle fails the health gate. Consider refusing to start, rather than starting
with a warning, when the bundle is absent in a production tier — an operator who
wanted a headless API deployment should have to say so explicitly.

### ART-008 — Concurrent reclaimers log the loser's collision as an ERROR and each reports a partial deletion count

**Severity** — LOW

**Zone** — "7. Which process reclaims an artefact, and what two of them doing it at once produces"

**Observation** — The process set, derived rather than assumed. The `app`
container is the only process that creates, reads or removes artefacts: the route
creates them, its lifespan runs `mark_orphaned_uploaded_logs_failed`, the
age sweep and the queue consumer, and the worker removes them. The `rq-worker`
service mounts the same `app_data` volume but runs the `rqworker` CLI
(`docker/docker-compose.yml:181`), which imports no project code, and Phase 01
established that nothing ever enqueues to Redis, so it has no path to the area
today. Within `app`, `cleanup_stale_temp_files` lists the directory, then
`stat()`s and `unlink()`s each file in a `try` whose `except Exception` handler
emits `logger.error("Error processing file %s: %s", …)`
(`services/file_cleanup.py:84-101`). The producer declares
`--workers 4` (`docker/Dockerfile:179`) and uvicorn runs the application lifespan
in every worker process, so four sweepers walk the same directory at every
start. The second remover's outcome is therefore an `ERROR` line, and the
`deleted_count` each process returns — and the "Cleaned up %d orphaned temp
files during startup" line built from it (`db/starter.py:181-182`) — covers only
the files that process happened to win.

**Evidence** — Four concurrent `cleanup_stale_temp_files()` calls over the shared
volume with three stale files, run in the `app` container: three successful
deletions, and **five** `ERROR … [Errno 2] No such file or directory` lines from
the three losing sweepers; return values `[2, 1, 0, 0]`. The full transcript is
in the appendix. The aggregate happened to equal the true count here, but each
individual count is a partial view and nothing marks which files a process
believes it removed.

**Consequence** — On every restart of a four-worker `app` with N stale files
present, roughly 3N `ERROR` lines are emitted that an operator must triage as
though the disk were failing, and the startup summary line reports one worker's
partial count as if it were the total. No artefact is lost and no file is left
behind, so the runtime effect today is confined to the noise and to a misleading
count — which is why this is graded LOW rather than MEDIUM.

**Recommendation** — Treat an already-absent file as the expected outcome of a
concurrent sweep: catch `FileNotFoundError` separately and count it as "already
reclaimed" at `DEBUG`, keeping `ERROR` for genuine failures, and report the
sweeper's result as a count of files it observed rather than files it deleted. If
Phase 01's remediation replaces the in-process queue with RQ, the same race
becomes a real two-reclaimer race between the app's startup sweep and a worker
that can be running a job at that moment, so make the sweep tolerant before
wiring RQ rather than after.

### ART-009 — The declared allowed-MIME set is not the one enforced, and the two content-detection branches accept different files

**Severity** — LOW

**Zone** — "1. The accepted artefact's identity: what it is called, what its name claims, and what its bytes are"

**Observation** — `UploadSettings.allowed_mime_types` declares
`[TEXT_CSV, APPLICATION_GZIP]` (`config.py:339-342`), is exposed as
`Settings.allowed_mime_types` (`config.py:844-846`), is documented in
`docs/06-backend/configuration.md:174`, and is read by nothing: admission uses
`MimeTypeEnum.allowed_values()` (`services/file_processing.py:87`), which is the
three-member enum `[text/csv, application/gzip, application/x-gzip]`
(`models/enums.py:92-102`). The declared set and the enforced set already differ
by one member — `application/x-gzip`, the legacy alias libmagic can return, is
accepted by the code and forbidden by the configuration. Separately, the branch
taken when a type cannot be derived is a `try: import magic / except
ImportError` at module scope (`services/file_processing.py:26-70`): with
`libmagic1` installed, as both the `base` and `prod-base` image stages do
(`docker/Dockerfile:46`, `:81`), libmagic is live; without it — the Windows host
case the fallback docstring names — a hand-written heuristic decides instead. The
two branches return different verdicts for the same bytes.

**Evidence** — Branch selection measured on both sides. In the container:
`import magic` succeeds and `magic.from_buffer(b'category;sales\nA;1\n', mime=True)`
→ `text/plain`; the same bytes through the HTTP upload surface returned **415
`INVALID_FILE_TYPE`**, logged as `Invalid MIME-type detected: text/plain`. The
fallback branch would have classified those bytes `text/csv`, because
`b";" in file_buffer` (`file_processing.py:67`). Comma-delimited CSV was
`text/csv` and accepted; gzip bytes were `application/gzip` and accepted; a
256-byte-pattern binary was `image/x-tga` and rejected. On the host:
`import magic` raises `ImportError: failed to find libmagic. Check your
installation`, so the fallback branch is what runs there. The same semicolon
file is rejected in the container and accepted on the host.

**Consequence** — Two consequences, both bounded today. An operator who sets
`UPLOAD__ALLOWED_MIME_TYPES` gets no effect at all, and if they read
`docs/06-backend/configuration.md:174` to learn what is accepted they will be
told `application/x-gzip` is refused when the code accepts it. And a
semicolon-delimited CSV — a file the loader is explicitly configured to read via
`processing_configs.settings.separator` (`workers/data_worker.py:405-406`) — is
rejected at admission in the container and admitted on a host without libmagic,
so the same file behaves differently by environment rather than by
configuration.

**Recommendation** — Delete `upload.allowed_mime_types` and its documentation
row, and make `MimeTypeEnum` the single declaration, or invert it: have the
validator read `config.allowed_mime_types` so the setting becomes real. Choose
one detection implementation and make the other an explicit, tested failure
rather than a silent `except ImportError` branch — if libmagic is required, list
it as a hard startup dependency the way `main.check_dependencies` already does
for the other critical modules (`main.py:10-25`). If the fallback is kept, it
should share the enum and be exercised by a test that runs on both branches
rather than by whichever branch the host happens to provide.

## Distribution

The findings concentrate on one component: the stored-artefact area of the
`app` container and the code that names, sweeps and serves it. `ART-001`,
`ART-004`, `ART-005` and `ART-008` are all in
`services/file_processing.py` + `workers/data_worker.py` +
`services/file_cleanup.py`, and the single component carrying the most is
`workers/data_worker.py`, which owns the removal ordering, the failure-path
unlink and the single removal whose failure is only a log line. The rest fall on
distinct, non-overlapping owners.

- Upload admission and naming — `services/file_processing.py`, `api/routes/upload.py` (ART-001, ART-009)
- Background processing and removal — `workers/data_worker.py` (ART-001, ART-004, ART-005)
- Reclamation — `services/file_cleanup.py`, `db/starter.py` (ART-003, ART-005, ART-008)
- Records and reconciliation — `db/models/processing_logs.py`, `services/data_service.py` (ART-002)
- One-time secret — `api/routes/admin.py`, `core/temp_password_store.py` (ART-006)
- Interface bundle and health — `app.py`, `docker/Dockerfile` (ART-007)

## Cross-Finding Analysis

Two causes are shared, and one is not a pattern at all.

`ART-001`, `ART-004` and `ART-005` share one cause: **the worker treats the
artefact as scratch space and the rest of the system treats it as a
still-addressable object, and no artefact identity is ever written down.**
`ART-001` follows the caller's name where the content should decide, `ART-004`
destroys the artefact on every terminal path including the one where the work
was rolled back, and `ART-005` cannot record that the removal failed — all three
because there is no durable statement anywhere of what the artefact was, where
it lived, or whether it is still there. `ART-002` is the recording half of the
same cause and is listed separately only because its remediation is separable.

`ART-003`, `ART-007` and `ART-008` share a different and weaker cause: a
shipped configuration value or condition exists in two places and the two places
are checked independently — the volume and its size budget, the bundle's
presence as checked by the mount versus by the health endpoint, and the sweep run
by four processes that were each written as if there were one.

`ART-006` and `ART-009` are independent of both and of each other: one is a
fail-open store on an admin path, the other is a dead configuration key beside a
platform-dependent detector.

## Roadmap

Grouped by cause. Steps 1–3 are one change set because they edit the same
ordering in `workers/data_worker.py`; steps 4–6 can proceed in parallel with them
and with each other.

1. **Make the artefact's identity and the reader agree, and contain the failure
   mode** (ART-001). Derive the stored extension from the detected content type
   inside `process_upload_with_session`, and make `CSVLoader.load_csv` translate
   reader failures of any base class into the `ValueError` its docstring
   promises. *Before the next step:* `tests/test_data_service.py:641-657` is
   re-pointed at a comma-containing body, and a test asserts that a `.csv.gz`
   name over plain bytes is either rejected at admission or read as plain CSV —
   whichever direction is chosen.
2. **Stop destroying the source before the work derived from it is durable, and
   make the failure path keep what is retryable** (ART-004). Commit first, unlink
   after; on the rollback path retain the artefact and record that it was
   retained. *Before the next step:* decide explicitly whether a task is
   re-runnable, because that decision determines whether step 3 is a column or a
   deletion.
3. **Make store-versus-record divergence detectable in both directions**
   (ART-002, and the recording half of ART-005). Either add one nullable artefact
   name to `ProcessingLog` and make `find_task_file` the only selector, or
   declare the artefact scratch space, delete the two name-based selectors, and
   add a startup reconciliation that reports — never silently deletes — an
   artefact whose record is absent, terminal, or older than the sweep threshold.
   *Before the next step:* step 2's decision is made; if the column route is
   taken, the Alembic revision lands here and `ProcessingStatusResponse.filename`
   is populated from it.
4. **Give removal failures a queryable home and a retry** (ART-005). One nullable
   `cleanup_error` on `ProcessingLog`, surfaced in the status payload and the
   admin log list; move the sweep onto the periodic task; resolve
   `cleanup_task_files` in the same change as step 2. *Before the next step:*
   step 3 has settled whether the artefact has a durable record to hang a failure
   on.
5. **Separate the artefact volume from the log volume, and put a byte ceiling on
   the area** (ART-003, ART-008). Move `LOGGING__LOG_FILE` off `app_data`, add a
   directory-size budget checked before accepting, treat
   `FileNotFoundError` in the sweep as the expected outcome of a concurrent run,
   and drop the never-written `/app/data/uploads` from the image stages.
   *Before the next step:* the production deployment's disk budget is known, so
   the ceiling is a number rather than a guess.
6. **Make the one-time secret's two failures distinguishable** (ART-006) and
   settle the declared MIME set (ART-009). Have `store` fail loudly and reorder
   the approve endpoint so the record and the secret cannot disagree; let a Redis
   error during collection surface as unavailable rather than as not-found; pick
   one detection implementation. *Before the next step:*
   `tests/core/test_temp_password_store.py:164-181` is changed with the store —
   it currently asserts the fail-open behaviour this step removes.

Steps 1, 2 and 6 change behaviour a caller can observe. `ART-007` (the bundle's
health words and route table) is deliberately **not** in the sequence: it is
independent of every other cause, carries no data risk, and its change — a
`FRONTEND__DIST_DIR` setting and a stricter health check — should land on its own
so that a `HEALTHCHECK` failure can be attributed to it alone.

## Rollout Safety

Steps 1, 2 and 4 change what a caller observes, and all three touch the
`workers/data_worker.py` ordering, so they belong in one change set with one
revert. The riskiest is step 2: unlinking after the commit means an artefact now
survives a run that failed, so the area's occupancy grows until the sweep
reclaims it, and a deployment that was relying on the failure path to keep the
directory small will see more files in it. That is the intended behaviour and it
is bounded by step 5's byte ceiling, which is why step 5's disk budget must be
known before step 2 ships. Step 1 changes the stored extension for mismatched
names only, so consistent uploads are byte-identical in behaviour; the risk is
limited to files that were previously stored under a false claim, and those were
either reading correctly by accident (the `.csv`-over-gzip case) or panicking.
Step 6's reordering means a Redis outage now fails an approval instead of
silently provisioning an unusable account — the correct outcome, but a visible
change in the admin's success rate during any Redis incident, and the
`force_password_change` gap Phase 04 filed still leaves a stranded account
window that this step narrows rather than closes.

What must be verified after the change set: the full suite on the `mkobi-test`
project, with particular attention to `tests/test_upload_api.py`,
`tests/test_file_cleanup.py`, `tests/test_mime_validation.py` and
`tests/core/test_temp_password_store.py`, all of which contain assertions about
the behaviour being changed; then one end-to-end upload per mismatch direction
against the dev stack, checking that the record reaches a terminal state and that
the area's contents match the records afterwards. Revert is a single revert of
the change set; the only irreversible artefact of the rollback is any upload
whose source was already deleted by the reverted-away code path, which is the
pre-existing behaviour and not a new exposure. The bundle change in
`ART-007` reverts independently, and its `HEALTHCHECK` edit is the only thing
that can turn a previously-passing container unhealthy, so it should ship with a
provisioned `frontend/dist` already in place.

## Appendices

### A. Audit baseline and concurrent-edit record

Recorded before any file was read, per the audit instruction:

- `git rev-parse HEAD` → `c3c0a61bf41cad68bf3a3ac105de91ea63c82268`
- `git status --porcelain` → dirty. Modified: `src/mkobi/config.py`,
  `src/mkobi/db/starter.py`, `tests/test_config.py`, `tests/test_starter.py`.
  Deleted (unrelated `.ai` tree): `.ai/audit/templates/audit-final-report.md`,
  `.ai/builders/**`, `.ai/models/**`, `.ai/plans/audit-fix-plan.md`,
  `.ai/structure/**`, `.ai/templates/**`. Untracked: the five prior phase
  directories under `.ai/audit/`, `.ai/audit/99-validation/`, and
  `.ai/plans/01-configuration-secrets-remediation-execution.md`.
- Nothing was edited, staged, committed, reverted or stashed by this audit.

Both modified source files are cited in this report, so their anchors were
re-verified after all evidence was gathered: `config.py:332` (`temp_dir`),
`:334` (`max_file_size_mb`), `:339` (`allowed_mime_types`), `:464`
(`temp_password_ttl_seconds`) and `starter.py:180` (the sweep call), `:395` and
`:400` (`cleanup_old_logs`) are unchanged from the values read at the start. No
anchor cited in this report moved.

### B. Block coverage record

Every block was executed; the artefact column names the evidence that exists for
it whether or not it produced a finding.

| # | Block | Reached | Evidence artefact | Finding |
|---|---|---|---|---|
| 1 | Accepted artefact's identity | yes | 3-case loader probe; libmagic verdicts; `UPPER.CSV` and mislabelled uploads over HTTP; the `MIME`-set comparison | ART-001, ART-009 |
| 2 | Residence and what bounds it | yes | control inventory classified by time/count/bytes; container `ls` of the shared volume; `RotatingFileHandler` config | ART-003 |
| 3 | Reconciliation, both directions | yes | three divergent selectors; the record model; `trigger_processing` reachability sweep; the status payload showing `filename` = log message | ART-002 |
| 4 | Removal, and the record of a failed removal | yes | the four removal sites; the per-site `except` handlers; the dead-function sweep; the four-sweeper transcript | ART-004, ART-005 |
| 5 | One-time secret outside the database | yes | approve handler; store/retrieve implementations; the TTL; the retrieval handler's single `None` mapping | ART-006 |
| 6 | Built interface bundle as a served artefact | yes | three presence states driven through `create_app()` + `TestClient`; `/health` and `/health/detailed` payloads; `HEALTHCHECK` line | ART-007 |
| 7 | Which process reclaims; two at once | yes | process inventory from the compose topology; four concurrent sweeps over the shared volume | ART-008 |
| 8 | Returning surfaces | yes | sweep for `FileResponse`/`StreamingResponse`/`Content-Disposition`/`download` across `src/`; the only `FileResponse` is the bundle's `index.html` | none — inventory empty, see D |

### C. Four-sweeper reproduction (ART-005, ART-008)

Run in the `app` container against the shared `app_data` volume: three files with
a 72-hour-old mtime, then four concurrent `cleanup_stale_temp_files()` calls.

```
STALE_FILES_BEFORE: ['11111111-….csv', '22222222-….csv.gz', '2b29529f-….csv.gz',
                     '98537fdd-….csv', 'upload_deadbeef-…_leftover.csv']
INFO  … Deleted stale temp file: …/22222222-….csv.gz (age: 72.0 hours)
ERROR … Error processing file …/upload_deadbeef-…_leftover.csv: [Errno 2] No such file or directory
INFO  … Deleted stale temp file: …/upload_deadbeef-…_leftover.csv (age: 72.0 hours)
ERROR … Error processing file …/11111111-….csv: [Errno 2] No such file or directory
ERROR … Error processing file …/11111111-….csv: [Errno 2] No such file or directory
INFO  … Deleted stale temp file: …/11111111-….csv (age: 72.0 hours)
SWEEPER_0_RETURNED: 2   SWEEPER_1_RETURNED: 1   SWEEPER_2_RETURNED: 0   SWEEPER_3_RETURNED: 0
TOTALS_RETURNED: [2, 1, 0, 0]
DIR_ENTRIES_AFTER: ['2b29529f-….csv.gz', '98537fdd-….csv']
```

Three files, three successful deletions, five `ERROR` lines from the losers.

### D. Returning-surface inventory (block 8) — empty

Swept `src/` for `FileResponse`, `StreamingResponse`, `Content-Disposition`,
`download` and `export`. The only `FileResponse` in the project is the bundle
fallback at `app.py:381`. Accepted uploads are never returned: `/upload/result/`
and `/upload/status/` answer from `processing_logs`, and `/data/aggregated`
answers from `aggregated_data`. The only component that reads a stored artefact
is the worker, and it reads it to process, not to answer a request — so no
component lets an artefact's absence decide what a caller hears. The observable
that a caller *does* get — a record left at `uploaded` for a job that will never
run — belongs to Phase 01 and is cross-referenced, not re-filed here.

### E. Excluded subtrees and their reasons (block 3)

- `platformdirs.user_cache_dir("mkobi", appauthor=False) / "uploads" / {user_id}`
  (`utils/file_utils.py:18-31`) — a second, differently-rooted temp area created
  by `get_user_temp_dir`, which has no caller in `src/`. Excluded because no
  production path writes to it. Recorded rather than filed: AGENTS.md §5 step 2
  documents the upload path as "save to a temporary folder (platformdirs)", and
  the live path uses `UPLOAD__TEMP_DIR` (or `UploadSettings.__init__`'s
  `user_data_dir("mkobi", "ZOO")/tmp_uploads`, `config.py:347-351`) instead. The
  documentation is wrong and the code should be documented, not the reverse; the
  per-cache-root question is Phase 02's, which already owns the `temp_dir` value
  and `temp_dir_prefix`.
- Files whose name does not match `*.csv*` — none in practice: admission requires
  a `.csv` or `.csv.gz` suffix and the stored extension is normalised to
  lowercase by `detect_file_type`, so every accepted artefact matches the sweep
  glob. `UPPER.CSV` was accepted and stored as `…csv` (HTTP 201, observed).
- Subdirectories — none are ever created; both sweeps glob non-recursively.
- `services/file_cleanup.py:109-165` (`cleanup_old_processing_logs`) — a second
  implementation of the log-retention rule that no production path calls;
  `db/starter.py:395-418` is the live one. Noted, not filed: it is a duplicate,
  not a divergence in effect, and the two cutoffs cannot be distinguished in a
  UTC container.

### F. Limits on this report

- The dev stack runs one uvicorn process (`--reload`,
  `docker/docker-compose.override.yml:109`); the four-process multiplicity in
  ART-001 and ART-008 is derived from `docker/Dockerfile:179` and reproduced by
  driving the same functions four times concurrently, not by observing four live
  processes. The production stack was not started.
- The dev `redis` container exited (code 0) mid-session, apparently from a
  concurrent `docker compose` action on the same `mkobi` project name, and was
  restarted with `docker start`; the login rate-limit key was deleted from it to
  continue probing. A parallel `mkobi-test` container from another process was
  running throughout. No finding depends on the state this produced.
- The three probing uploads are still present in the dev volume
  (`2b29529f-….csv.gz`, `98537fdd-….csv`) and their records are `failed` with
  "Worker restart: orphaned UPLOADED entry detected", written by the startup
  orphan sweep at 12:58:59Z rather than by the worker. The `app` process restarted
  at that moment; the cause was not established and no finding rests on it. Both
  files are inside the 24-hour sweep window and will be reclaimed at the next
  start.
- The nginx `production` profile was not started, so the two-copies-of-the-bundle
  divergence between the image-baked `frontend/dist` and the host bind mount
  (`docker-compose.yml:247`) is stated as a configuration fact, not an observed
  response difference.
- `docs/` claims about the upload path were read for divergence only
  (`docs/03-processing/processing-api.md:96`,
  `docs/11-guides/docker.md:746-751`); documentation accuracy as such is Phase
  08's.
