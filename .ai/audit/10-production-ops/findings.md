---
phase: 10-production-ops
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 16
baseline: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
baseline-dirty: "src/mkobi/config.py, tests/test_config.py modified; 19 .ai/ files deleted; .ai/audit/* and .tmp/ untracked"
baseline-final: eeb9a5e1ae4df195b9a4fa4f7c19b8834f8307d8
by-severity:
  CRITICAL: 0
  HIGH: 5
  MEDIUM: 11
  LOW: 0
---

# Phase 10 — Findings

## Summary

This phase examined the deployed composition as a running thing: effective per-service runtime posture
after every layer merged, the external-input inventory that decides artifact content, what can prevent a
change from landing, the service set the deployment path actually enables, restart and one-shot-step
behaviour, the health contract an observer can act on, the Redis key inventory and marker lifetimes, the
nginx fronting tier, backup and restore, the operator's signal stream, and the operational claim corpus.
Evidence came from the resolved production compose (secrets reduced to booleans, never printed), from the
running dev stack (`-p mkobi`), and from throwaway `docker run` probes against `mkobi-app`.

The single most consequential thing found is that **the deployed task-queue topology is not the one the
corpus describes**: the `rq-worker` service starts, registers itself in Redis, is health-checked, and has
never received a single job (Redis holds only `rq:workers`, `rq:workers:default` and `rq:worker:<id>` — no
queue list, ever), while production processing runs on four independent in-memory `asyncio.Queue`
instances inside the uvicorn workers. Second, the client bundle that nginx serves lives in an
unversioned host directory outside every image, so the documented image rollback cannot restore it.
Third, `redis_data` — the only record that a token was revoked or a user was deactivated — is the one
durable state with no backup and no export path anywhere.

**Independent verification of the phase-02 remediation claims (`044e630`, `8505a62`) is in Appendix A:
all four of CFG-001, CFG-004, CFG-005 and CFG-006 are genuinely closed.**

## Findings

### OPS-001 — The only record that a token was revoked or a user deactivated lives in an unbacked volume that no export path covers

**Severity** — HIGH

**Zone** — The shared transient store: every key it holds, every marker's lifetime, and what its loss stops

**Observation** — Redis carries five distinct kinds of key in db 0: `blacklist:<jti>` and
`refresh_token_blacklist:<jti>` (written by `revoke_token` / `revoke_refresh_token`,
`src/mkobi/core/security.py:474`, `:487`), `user_tokens_revoked:<user_id>` (written by
`revoke_all_user_tokens`, `security.py:535-538`), `temp_pwd:<token>` (`core/temp_password_store.py:10,41`),
and bare rate-limit keys (`login_attempts:`, `refresh:`, `register-request:`, `client-errors:`,
`api/routes/auth.py:314,566`, `client_errors.py:49`). Four of these five encode **negative**
authorisations: `user_tokens_revoked:<user_id>` is written only by
`admin.py:176` on deactivation and is the sole mechanism that enforces deactivation — `admin.py:163-171`
issues only `db.flush()` through `user_repo.update`, and neither the repository nor `get_db_dependency`
commits, so the `is_active=false` row never reaches disk and the Redis marker is the whole effect. The
volume backing all of this, `redis_data`, is not read, dumped, exported, copied or scheduled anywhere in
the repository: `Makefile.ps1`'s `backup` target touches `postgres_data` only, and no `redis` command,
no `SAVE`, no `BGSAVE`, no `redis-cli --rdb` appears in any file.

**Evidence** — `grep -rn` over `Makefile.ps1`, `docker/*.yml`, `docker/scripts/` finds no reference to
`redis_data` outside `docker-compose.yml:160` (the volume declaration) and `:274` (the top-level
declaration). Live inventory: `docker exec mkobi-redis-1 redis-cli info keyspace` →
`db0:keys=3,expires=1`; `redis-cli --scan` returns only `rq:workers`, `rq:workers:default`,
`rq:worker:06aedb00192a44a2bc90c2891a7f3d53` — after a full dev-stack lifetime, not one revocation,
rate-limit or temp-password key has ever been created, because no authenticated call had been made in
that interval. `docker volume ls` confirms `mkobi_redis_data` is a real named volume.

**Consequence** — Losing `redis_data` (host loss, `.\Makefile.ps1 fullclean` / `nuke`, VM reset, or a
volume-level incident) silently re-admits every revoked access token, every revoked refresh token and
every deactivated account, with no error and no signal: `is_token_revoked` / `is_user_tokens_revoked`
return `False` for keys that no longer exist, so an attacker holding a blacklisted refresh token can mint
new access tokens through `/api/v1/auth/refresh` (which consults only `is_refresh_token_revoked` and
`is_user_tokens_revoked`, `auth.py:341,368`) and a deactivated user whose access token has not yet
expired is admitted. The protection exists and the system believes it is in force; the store that holds
it is the one piece of durable state the backup procedure never touches.

**Recommendation** — Add a Redis persistence artifact to `Invoke-Backup`: `redis-cli --rdb` (or
`BGSAVE` + copy of `dump.rdb`) into the same stamped `backups/` directory, and a matching
`Invoke-RestoreRedis`. `redis:7.4-alpine` is already started with a `/data` volume and no `--save`
override, so `dump.rdb` is being written by default — the backup simply never reads it. Small effort;
do it before anything that widens reliance on the marker.

### OPS-002 — The RQ worker runs, registers and is health-checked, and has never received a job; production processing runs on four per-worker in-memory queues

**Severity** — HIGH

**Zone** — Service coverage and provenance: what the deployment defines, starts, and actually runs

**Observation** — `docker/docker-compose.yml:176-233` defines `rq-worker`, builds it from the `prod`
target, runs `/app/.venv/bin/rqworker --url redis://redis:6379/0`, gates it on `redis: service_healthy`
and `migrate: service_completed_successfully`, and gives it a healthcheck. Nothing ever enqueues to it.
`src/mkobi/core/task_queue.py:159-192` holds a module-global `default_queue = TaskQueue()` built on
`asyncio.Queue`; `enqueue_job()` (`:162-187`) puts into it, and `app.py:129-143` starts an in-process
`queue_worker()` loop that drains it. No module in `src/` imports `rq` except `rq_worker_wrapper.py`,
which no compose service invokes (the service runs the `rqworker` CLI directly). Every uvicorn worker
process re-imports the app module, so each of the production `--workers 4` processes constructs its own
`default_queue`.

**Evidence** — Live, after ~3 h of `mkobi-rq-worker-1` uptime: `docker logs` shows
`*** Listening on default...` at 13:58:22 followed by nothing but
`Worker 06aedb00...: cleaning registries for queue: default` every ~13 min. Redis holds no queue key
(`redis-cli keys 'rq:*'` → `rq:workers`, `rq:workers:default`, `rq:worker:<id>` only; there is no
`rq:queue:default` list). `docs/11-guides/docker.md:361` states the opposite of what is deployed:
"the RQ worker is the production implementation of the task queue. The in-memory `asyncio.Queue` is used
when it is not running."

**Consequence** — A `POST /api/v1/upload/{dashboard_id}` enqueues into whichever uvicorn worker happened
to accept the connection. Only that worker's in-memory loop executes it; there is no shared queue, no
durability and no retry. If that worker is respawned — and uvicorn 0.49.0's supervisor kills and
replaces any child that does not answer the parent ping within `timeout_worker_healthcheck` (default 5 s,
`uvicorn/config.py:219`) — or if the container restarts, the enqueued task is gone and the
`processing_logs` row stays at `UPLOADED`/`PROCESSING` until `mark_orphaned_uploaded_logs_failed()`
(`app.py:116`) runs at the *next* startup. Nothing observes the loss: the worker's healthcheck is a bare
`Redis(...).ping()` against `redis` (`docker-compose.yml:217-226`), which stays green while the worker
executes nothing, and there is no queue-depth signal anywhere (see OPS-007).

**Recommendation** — Pick one queue and make the topology match it. The smallest change that removes the
false topology is to have `enqueue_job()` dispatch through `rq.Queue` when `rq` is reachable and fall
back to the in-memory queue otherwise — the `enqueue_with_worker` stub at `task_queue.py:55-76` is
already the designated integration point, and `rq_worker_wrapper.py` already implements the retry-then-
`sys.exit(1)` startup contract the compose service lacks. If the in-memory queue is the intended
production path, delete the `rq-worker` service rather than shipping a worker that never works.

### OPS-003 — The production SPA is served from an unversioned host directory, so the documented image rollback cannot restore the client bundle

**Severity** — HIGH

**Zone** — Service coverage and provenance: what the deployment defines, starts, and actually runs

**Observation** — Two different artefacts carry the same output. The `prod` Dockerfile stage builds the
bundle itself (`Dockerfile:10-22` `frontend-builder`, then `:166`
`COPY --from=frontend-builder /app/frontend/dist ./frontend/dist`), and `app.py:331-382` mounts
`frontend/dist` for single-container serving. Separately, `docker-compose.yml:246-247` mounts
`../frontend/dist:/usr/share/nginx/html:ro` into `nginx`, and `nginx.conf:49-53` serves the SPA from
`/usr/share/nginx/html`. That host directory is neither tracked in git nor ignored:
`git ls-files frontend/dist` returns 0 files and `.gitignore` contains no `dist` rule (the generic
`dist/` rule at `.gitignore:15` is rooted, so it does not match `frontend/dist/`). Nothing in the
deployment path creates it — `docker-compose.yml:235-237` states "nginx requires a prior frontend build
(npm run build in /frontend)" and no compose step, Makefile target or documented command in
`docs/10-deployment/deployment.md:163-174` performs one. It currently holds a bundle dated 18/06/2026.

**Evidence** — `git ls-files frontend/dist | Measure-Object -Line` → `0`. Resolved production volumes:
`{"type":"bind","source":"C:\py_dev\mkobi\frontend\dist","target":"/usr/share/nginx/html","read_only":true}`.
`.\Makefile.ps1 help` lists no `fe-build` target and no target invokes `npm run build`;
`Makefile.ps1:378` (`nuke`) runs `docker builder prune -af` and `docker image prune -af`, neither of
which touches the host `frontend/dist`. `docker-compose.yml` has no `image:` key on any built service, so
the app image is also untagged (`mkobi-app:latest`, recreated in place).

**Consequence** — Rolling the application back to a previous image restores the API and the baked-in
`/app/frontend/dist` inside that image, but nginx keeps serving the same host directory, so the client
bundle does not move. A rollback that is supposed to restore a whole-stack known-good state restores
only the server half of it, and the served bundle is not reproducible from version control by any means.
The same gap means the deployment can start successfully with a stale or absent bundle: if
`frontend/dist` does not exist on the host, Docker creates an empty directory and nginx returns 404 for
`/` while its own healthcheck (`wget --spider -q http://localhost/`) follows `try_files` … and fails,
whereas nothing at all examines whether the bundle matches the source that was just built.

**Recommendation** — Make nginx consume the artefact the build produced. Either drop the
`../frontend/dist` bind mount and add an nginx stage to the Dockerfile that copies
`--from=frontend-builder /app/frontend/dist`, so the bundle is versioned with the image and rolls back
with it; or, if the bind mount is deliberate, add a `fe-build` target and a `preflight` check that fails
the deployment when the host bundle is absent or older than the frontend sources. Do not ship both.

### OPS-004 — The health contract an observer acts on cannot see the dependency that decides every authenticated request

**Severity** — HIGH

**Zone** — The health contract an observer can act on

*(Co-owned with phase 07. The phase-07 validator explicitly assigned the probe-contract half to this
phase; the outage measurement is phase 07's and is cited, not re-measured.)*

**Observation** — The deployed production path places Redis on two request paths. It is the revocation
oracle for every protected endpoint (`api/deps.py:503-530` and `core/permissions.py:326-334` call
`is_token_revoked` / `is_user_tokens_revoked`) and the counter for every rate-limited surface
(`auth.py:88,314,566`, `upload.py:148`, `client_errors.py:50`). Neither health endpoint examines it.
`app.py:248-267` (`/health`) executes exactly one statement, `SELECT 1`, against PostgreSQL.
`app.py:269-307` (`/health/detailed`) builds a `components` map from exactly two probes — `database` and
`static_files` — and `docs/05-health/health-api.md:118-128` publishes that two-component set as the
component-level overview an operator is told to use ("Admin dashboards: use `/health/detailed` for a
component-level status overview"). Redis appears in neither the handler nor the document.

**Evidence** — `app.py:283-304`: the only two `components[...]` assignments are `database` and
`static_files`. Live: `GET http://localhost:8010/health/detailed` →
`{"status":"healthy","components":{"database":{"status":"connected","type":"postgresql"},"static_files":{"status":"unavailable","path":"frontend/dist"}}}`
— and the dev stack's own Redis holds no application keys at all, so that `healthy` verdict is being
produced by a system with no revocation state in existence. Phase 07 measured the consequence with Redis
paused: `/health` still returned 200 `{"status":"healthy"}` in 0.014–0.019 s while `/auth/me` with a
valid bearer returned 401 after 58.8–59.4 s.

**Consequence** — Every consumer of the health contract consumes a verdict that cannot distinguish
"working" from "refusing every authenticated request". The consumers are: the Docker `HEALTHCHECK` at
`Dockerfile:176-177` and `docker-compose.yml:142-147` (`curl -f /health`, so `unhealthy` is unreachable
during a Redis outage); `nginx` (`depends_on: app: condition: service_started` — already TOPO-008); and
the four documented integrations at `health-api.md:177-184`, of which the uptime-monitor rule is
"alert on non-200 responses". During a total authenticated outage the container stays healthy, nothing
goes unhealthy, and no alert expression can fire.

**Recommendation** — Add a `redis` component to `/health/detailed` that reports the store's reachability
with a short, bounded timeout (do not inherit `redis-py`'s library-default retry budget — the ~11
attempts ≈ 55 s that phase 07 identified — set `socket_connect_timeout` explicitly and pass
`socket_timeout`). Keep `/health` cheap and additive: return 200 while Redis is degraded but add a
`"redis": "degraded"` field, and reserve 503 for it only once the rate limiter's own
`RATE_LIMITER_FAIL_CLOSED=true` policy is in force, so the two tiers agree on what unhealthy means.
Then update `health-api.md`'s component table, which currently enumerates two components.

### OPS-005 — `backup` reports success unconditionally after the dump step, `restore` never examines what it restored, and there is no rehearsal path

**Severity** — HIGH

**Zone** — Evidence that a restore works

**Observation** — `Makefile.ps1:279-290` (`Invoke-Backup`) checks `$LASTEXITCODE` only after
`pg_dump`, then runs `docker compose ... cp db:/tmp/mkobi.dump $dest`, **does not check its exit code**,
does not test that `$dest` exists or is non-empty, and then unconditionally prints
`Write-Host "Backup created: $dest"` in green. `Makefile.ps1:292-306` (`Invoke-Restore`) checks the
`cp`, then runs `pg_restore -U postgres -d bidb --clean --if-exists` **without checking its exit code**,
never reads the result, and follows it with `rm -f /tmp/mkobi-restore.dump`. The script's last statement
is `exit $LASTEXITCODE` (`Makefile.ps1:441`), which by then holds the exit status of the trailing
`docker compose exec ... rm -f` — zero. No target, script, test or scheduled job anywhere in the
repository restores a dump that was taken at a different time than the database it restores into, and no
`RPO`, `RTO` or recovery objective is stated in any document (`grep -rn 'RPO|RTO|recovery objective'`
over `docs/` returns only the two words inside vendored `docs/STRUCT.md` TypeScript listings).

**Evidence** — Static read of `Makefile.ps1:279-306` and `:441`. The failure premise is live:
`docker compose -p mkobi ... cp db:/tmp/does-not-exist.dump <path>` exited **1** with
`no container found for service "db"` — a copy failure of exactly the shape `Invoke-Backup` would
convert into a green "Backup created:" line. `.\Makefile.ps1 help` (`:90-93`) documents `backup`,
`restore <file>` and `prune-backups` and nothing else; there is no verification or rehearsal target.

**Consequence** — There is no evidence, at any point, that a backup taken by this procedure can be
restored. A backup run whose copy-out failed is indistinguishable from a successful one at the terminal
and in any log. A restore run whose `pg_restore` failed is likewise indistinguishable from a successful
one, and reports exit status 0 to whatever invoked it. An operator following the documented recovery
path has no way to learn that recovery did not happen until a user reports missing data.

**Recommendation** — Make both entry points prove their own result: after the `cp`, assert
`Test-Path $dest` and a non-zero length and re-run `pg_restore --list` against the copied file before
printing success; after `pg_restore`, check `$LASTEXITCODE` and report the pg_restore output, and only
then remove the in-container copy. Add one `rehearse-restore` target that restores the newest dump into a
throwaway database created by the target itself and asserts the alembic revision plus a row count — it
will not prove recoverability from a real loss, but it will make the copy and the artifact's integrity
non-vacuous.

### OPS-006 — `nginx`'s access and error streams are written to a tmpfs on a read-only root: absent from `docker logs`, absent from the filesystem, gone on every recreation

**Severity** — MEDIUM

**Zone** — Signals produced, signals consumed, and the log paths that bypass the structured output

**Observation** — `docker/nginx/nginx.conf:10-11` sets `access_log /var/log/nginx/access.log` and
`error_log /var/log/nginx/error.log` — file paths, not `stdout`/`stderr`. `docker-compose.yml:249-256`
sets `read_only: true` on `nginx` and supplies `/var/log/nginx` as a `tmpfs`, alongside `/tmp`,
`/var/cache/nginx` and `/var/run`. Neither the compose file nor the image's `log` driver configuration
sends those two files anywhere. The application's own streams behave differently: `logging_config.py:102-109`
configures a `StreamHandler` on `ext://sys.stdout`, so every application and `uvicorn.access` record
reaches `docker logs app`.

**Evidence** — `nginx.conf:10-11` (file targets) vs `nginx.conf` has no `access_log ... /dev/stdout`
anywhere; `docker-compose.yml:251-256` (`read_only: true` + `tmpfs: [/tmp, /var/cache/nginx, /var/run, /var/log/nginx]`).
No `logging:` driver block and no volume maps `/var/log/nginx` out of the container in any compose file.

**Consequence** — The fronting tier's request and error streams reach no collector and no operator. They
are not in `docker logs nginx`, they are not on any host path, and they are destroyed whenever the
container is recreated — which `docker compose up -d` does on every configuration change, on every
image rebuild, and on every host reboot under `restart: unless-stopped`. If a request fails at the edge
rather than in the app — a 413 from `client_max_body_size`, a 502 while the app restarts, an upstream
timeout — the only record of it existed on a tmpfs and is gone.

**Recommendation** — Point both directives at the container's standard streams
(`access_log /dev/stdout;`, `error_log /dev/stderr warn;`) and drop `/var/log/nginx` from the tmpfs list,
so the edge tier's output lands in the same place as the application's and is collected by whatever
already reads `docker logs`. Trivial effort, and it removes a whole class of "the 502 left no trace".

### OPS-007 — The system exposes no metrics surface at all, so no alert expression can be evaluated against it

**Severity** — MEDIUM

**Zone** — Signals produced, signals consumed, and the log paths that bypass the structured output

**Observation** — Beyond `/health` and `/health/detailed` (OPS-004), the deployed system emits no
machine-readable series: there is no `/metrics` route (no Prometheus, OpenTelemetry or statsd exporter in
`src/`), no `/api/v1` route returns counters, and no alert rules, dashboards or collectors are shipped
in the repository. The signals that do exist are two boolean HTTP probes and a log stream. Conditions
with no signal at all include: in-memory queue depth and task loss (OPS-002); whether the RQ worker has
executed anything (OPS-002); `migrate` completion and alembic revision drift (see OPS-010 on the
one-shot step's completion condition); backup age and last-success; and the `redis_data` state that
OPS-001's entire recovery story depends on.

**Evidence** — `grep -rn 'prometheus|/metrics|opentelemetry|alertmanager'` over `src/`, `docs/`,
`docker/`, `Makefile.ps1` returns two hits, both incidental: `docs/STRUCT.md:1888` (a vendored
TypeScript `PrometheusMetrics.d.ts` declaration in a generated structure dump) and
`docs/11-guides/extend-graphs.md:72` (the word "metrics" in the sense of chart measures). No exporter,
no `/metrics` route in `app.py:236-246`'s router list.

**Consequence** — The absence of a metrics surface is itself the finding, not a gap in an inventory. An
operator's only inputs are a health verdict that is blind to the auth-path dependency (OPS-004) and a
log stream that is duplicated five ways and lives on a volume (OPS-008). Every condition listed above is
silent: nothing distinguishes a quiet system from a broken one, and no alert can be written because
there is no series for one to be written over.

**Recommendation** — Do not adopt a full metrics stack for a single-host Compose deployment. Ship the
three counters that would have caught the findings in this phase as fields in
`/health/detailed`: `redis` reachability and `redis_ping_ms`; `migrate`'s alembic revision (`alembic_version`
is already readable by the app's `mkobi_app` role via `SELECT version_num FROM alembic_version`); and the
in-memory queue's `qsize()` plus the count of `processing_logs` rows stuck in `UPLOADED`/`PROCESSING`
beyond `stale_processing_timeout_minutes`. That is a single endpoint, no new dependency, and it turns
three silent conditions into observable ones. State the RPO/RTO in `docs/10-deployment/deployment.md`
alongside it.

### OPS-008 — Under the production `--workers 4`, five independent rotating file handlers write the same file, duplicating every record and rotating it out from under each other

**Severity** — MEDIUM

**Zone** — Signals produced, signals consumed, and the log paths that bypass the structured output

**Observation** — `logging_config.setup_logging()` (`core/logging_config.py:111-123`) is called at
`app.py:39` — module scope — and installs a `RotatingFileHandler` at `LOGGING__LOG_FILE`
(`maxBytes=10MB`, `backupCount=5`). Under `uvicorn --workers 4` (`Dockerfile:179`) uvicorn 0.49.0 uses
the `spawn` start method (`uvicorn/_subprocess.py:spawn = multiprocessing.get_context("spawn")`), so each
of the 4 workers is a fresh interpreter that re-imports the app module and calls `setup_logging()` again;
the parent has already called it once. Five `RotatingFileHandler` instances therefore hold the same path
with independent rotation state and no lock.

**Evidence** — Measured with a throwaway `docker run` on `mkobi-app` at `--workers 2` with
`LOGGING__FILE=/tmp/probe.log` and `LOGGING__JSON_LOGGING=true`: every lifecycle record appears once per
process — `"Configuring CORS with allowed origins"` ×3 (parent + 2 workers), `"DB connection attempt
N/5 failed"` ×2 each, `"Shutting down application..."` ×2 — and all of them, including full Python
tracebacks, land in `/tmp/probe.log` as JSON from all three processes. `uvicorn/_subprocess.py:19`
confirms `spawn`. uvicorn source: `Config.configure_logging()` at `uvicorn/config.py:284` runs before
`load_app()` at `:481`, so the child's app import — and therefore `setup_logging()` — is what installs
its handler.

**Consequence** — In production every record is written to `/app/data/logs/app.log` five times, and each
of the five writers rotates independently: when one rolls the file to `app.log.1`, the other four keep
appending to the renamed inode and their next rotation deletes a `.1` that another writer is still
appending to. Records are duplicated, interleaved and lost. At `LOGGING__LEVEL=WARNING`
(`.env.production:31`) the duplicated records are the WARNING/ERROR ones — including every multi-
kilobyte `logger.exception` traceback, of which the probe produced two identical copies each. The
volume's ceiling is 5 × 6 × 10 MB = up to ~300 MB of `app.log*`, on the same `app_data` volume that
holds `uploads/` and `tmp_uploads/`.

**Recommendation** — Write one log stream, not five: set `LOGGING__LOG_FILE` only where a single process
owns it, and let the workers inherit it. The smallest correct change is to remove the file handler when
the process is a uvicorn worker child (or to gate it on an explicit `LOGGING__FILE_ENABLED` that only
the one-shot `migrate` service sets), leaving the console handler as the single production output —
`docker logs app` already captures it, and OPS-007's recommendation then has one place to read. If a
file is required, use a size-external rotation scheme (`logging.handlers.watchedFileHandler` is not
multiprocess-safe either; an external rotator or stdout-to-file at the container level is).

### OPS-009 — Every quality-gate invocation materialises the application's full production credential set into a throwaway container that needs none of it

**Severity** — MEDIUM

**Zone** — What can prevent a change from landing, and what the aggregate entry point omits

**Observation** — `Makefile.ps1:221-239` runs every backend gate as
`docker compose @DevCompose run --rm --no-deps app <cmd>`. The `app` service definition
(`docker-compose.yml:96-129`) is the one that carries `JWT__SECRET_KEY`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `DATABASE__PASSWORD` (as `mkobi_app`) and `CORS_ORIGINS`. A lint, a mypy run, an
ESLint-adjacent import check or a pytest shell therefore starts a container holding the signing key and
the bootstrap administrator credential in its environment. `--no-deps` means it does not need the
database to run `ruff check src/ tests/`. This sits before every verdict: `Invoke-Check` (`:241-249`)
begins with `Invoke-Lint`.

**Evidence** — `Makefile.ps1:222` (`run --rm --no-deps app ruff check src/ tests/`), `:226`, `:230`.
`docker-compose.yml:108-112` supplies `JWT__SECRET_KEY: ${JWT__SECRET_KEY:?...}` and
`ADMIN_PASSWORD: ${ADMIN_PASSWORD:?...}` to `app`. Resolved production config confirms
`app.environment.JWT__SECRET_KEY` and `ADMIN_PASSWORD` are both present on the `app` service.

**Consequence** — The credential set the runtime needs is handed to every static-analysis process,
widening the blast radius of a lint failure, an OOM kill, or a `ruff` crash dump from "the app process"
to "the app process plus every tool invocation", and making a credential rotation strictly broader than
it needs to be. The gates that matter are not automatable today (phase 09 owns that verdict and the
entry-point remediation), so this is a standing least-privilege break rather than an active incident —
which is why it is graded MEDIUM rather than HIGH.

**Recommendation** — Add a `tools` service to `docker/docker-compose.yml` that reuses the same build
target but supplies only the environment the tools need (`RUFF_CACHE_DIR`, `MYPY_CACHE_DIR`, `HOME`), and
point `Invoke-Lint` / `Invoke-Format` / `Invoke-Typecheck` / `Invoke-MigrationNew` at it. Keep `app`
alone for anything that touches the database. Trivial effort; it also removes the need for the
cache-directory workaround the dev override currently carries at lines 95-96.

### OPS-010 — The backup artifact is one database with no roles and no alembic state, and the only script that can restore the roles runs on first volume initialisation

**Severity** — MEDIUM

**Zone** — Backup: consistency, durability, and what each option changes

**Observation** — `Makefile.ps1:285` runs `pg_dump -U postgres -d bidb -F c -f /tmp/mkobi.dump`. `-d
bidb` selects one database; the cluster's globals — the `postgres` superuser and the `mkobi_app` role
with its `GRANT SELECT, INSERT, UPDATE, DELETE` on all tables and `USAGE` on all sequences
(`docker/init-scripts/01-create-app-role.sh:23-42`) — are not in the artifact. The only place those
roles are created is `/docker-entrypoint-initdb.d/`, which the official image runs **only when
`/var/lib/postgresql` is empty**; the script's own header says so ("run on PostgreSQL container
initialization (first volume start)"). `Invoke-Restore` (`:304`) therefore restores into whatever role
set the target cluster happens to have. Separately, `alembic_version` is inside the dump, but nothing in
the restore path compares the restored revision to the head the application expects — the one-shot
`migrate` service is `restart: "no"` (`docker-compose.yml:82`), so on a `docker compose restart app`
path it never re-runs, and a partial restore leaves the schema wherever the dump put it. Finally,
`$BackupDir = 'backups'` (`Makefile.ps1:37`) resolves relative to the repository root, so every
artifact lands inside the working tree the loss would take; `.gitignore:254` lists `backups/` (so
`git clean -xfd` keeps it, but a fresh clone or a repo-level replace does not), and `prune-backups`
(`:308-320`) is a manual target with no scheduler, so the nominal 7-day retention is only as real as
whoever remembers to run it.

**Evidence** — `Makefile.ps1:37` (`$BackupDir = 'backups'`), `:285`, `:304`. `docker-compose.yml:82`
(`restart: "no"`), `:31-34` (the `postgres_data` volume plus the init-scripts bind mount).
`01-create-app-role.sh:4` ("first volume start"). `pg_dump --help` inside `postgres:18-bookworm` lists
`--globals`/`--roles` as separate options that the shipped command does not pass. No cron, systemd timer,
scheduled task or CI job invokes `backup` or `prune-backups` — `Makefile.ps1` is the only entry point
and nothing else in the repository calls it.

**Consequence** — Restoring the artifact into a rebuilt cluster yields a database with no application
role, so the app and worker cannot connect until someone re-runs the init script by hand — and the
documented way to re-run it (recreate the volume) also destroys the database the restore was meant to
recover. A partial or stale-revision restore is accepted silently, and because `migrate` is one-shot and
never re-runs on a restart path, the running application can be several revisions behind its own image
with nothing reporting the gap. There is no scheduled backup, so "the backup procedure" is a thing an
operator remembers to do; and the artifacts sit inside the tree, so a repository-level loss takes them
with it.

**Recommendation** — Take the globals alongside the database: add
`pg_dumpall --globals-only -U postgres` to `Invoke-Backup` as a second stamped artifact in the same
directory, and have `Invoke-Restore` load it (`psql -U postgres -f globals.sql`) before the database
restore, so a restore into a rebuilt cluster is a complete procedure. Make `restore` end by printing the
restored `alembic_version` alongside `.\Makefile.ps1 migration-status` so the operator can see the gap
rather than infer it. Move `backup`/`prune-backups` onto the host scheduler the deployment already runs
on, and record the cadence in `docs/10-deployment/deployment.md` so the retention target stops being a
comment in `Makefile.ps1 help`.

### OPS-011 — An app lifespan failure becomes an unbounded worker respawn loop inside a container that never dies and never reaches a terminal state

**Severity** — MEDIUM

**Zone** — Restart and partial restart: ordering, address resolution, and one-shot steps

**Observation** — `app.py:147-155` re-raises any startup failure out of the lifespan. In production the
`app` command is `uvicorn ... --workers 4` (`Dockerfile:179`), so PID 1 is uvicorn's `Multiprocess`
supervisor, not a worker. `uvicorn/supervisors/multiprocess.py:keep_subprocess_alive()` polls
`process.is_alive(timeout=self.config.timeout_worker_healthcheck)` every 0.5 s and, for any child that
has died, logs `Child process [...] died` and starts a replacement immediately — no backoff, no attempt
cap, no circuit breaker. The supervisor itself never exits, so the container stays `Up` forever.
`docker-compose.yml:82` gives `migrate` `restart: "no"` and `:93` gates `app` on
`migrate: service_completed_successfully`, so once `migrate` has exited 0 nothing re-runs it: the boot
chain's one-shot gate is satisfied permanently while the thing it gated never becomes ready.

**Evidence** — Measured in a throwaway `docker run` on `mkobi-app` at `--workers 2` with the database
unreachable: `grep -c "Application startup failed"` over a 70-second window returned **4**, and the
tail showed the sequence `Application startup failed. Exiting.` → `Shutting down application...` →
`Database engines disposed` repeating indefinitely. `uvicorn/config.py:219`
(`timeout_worker_healthcheck: int = 5`); `uvicorn/supervisors/multiprocess.py:keep_subprocess_alive()`
has no sleep, counter or threshold between the kill and the respawn.

**Consequence** — A crash-looping `app` reports itself as a running container whose `HEALTHCHECK` has
gone `unhealthy` and will stay there; `restart: unless-stopped` does not act on `unhealthy`, so nothing
outside the stack notices except an operator reading `docker compose ps`. Meanwhile `db`, `redis` and
`rq-worker` keep running and `migrate` keeps reporting success, so a stack-wide health view assembled
from the boot chain looks correct. Each cycle also re-runs the full boot preconditions — the same
per-worker duplication TOPO-005 records — five times over, at roughly one cycle per 35 s per worker.

**Recommendation** — Give the failure a terminal state: pass `--workers` unchanged but have the lifespan
call `os._exit(1)` on a startup failure instead of re-raising, so the child exits, the supervisor's
`should_exit` is set and PID 1 exits non-zero, letting `restart: unless-stopped` apply its backoff and
`docker compose up --wait` fail loudly. If a crash loop is genuinely wanted for resilience, give
uvvicorn's supervisor a bounded attempt count — it has none today.

### OPS-012 — One Redis outage denies on some paths, admits on others, and the store's jobs have three different unguarded failure modes

**Severity** — MEDIUM

**Zone** — The shared transient store: every key it holds, every marker's lifetime, and what its loss stops

**Observation** — The five jobs in db 0 do not fail the same way. (i) The rate limiter catches
`Exception` and honours `fail_closed` (`core/security.py:137-151`), so `RATE_LIMITER_FAIL_CLOSED=true`
denies login, refresh, register, upload and client-error intake. (ii) The revocation *reads* in the
per-request gate are unguarded (`api/deps.py:503-530`, `core/permissions.py:326-334`): the raised
`redis.ConnectionError` surfaces as a denial. (iii) The revocation *writes* on logout are unguarded
(`api/routes/auth.py:448,459`) and, critically, ordered *before* `delete_secure_cookie(response,
COOKIE_NAME)` at `:461` — so when they raise, the cookie is never cleared and neither token is
blacklisted. (iv) `TempPasswordStore.store` catches `Exception`, logs and returns (`temp_password_store.py:47-48`),
so the credential is silently not persisted; the matching `retrieve` (`:73-75`) likewise logs and returns
`None`. (v) `revoke_all_user_tokens` on admin deactivation is unguarded (`admin.py:176`) and runs *after*
the database write (`admin.py:163-171`) with `except Exception: await db.rollback()` at `:187-188`.

**Evidence** — Static read of the six cited sites. Phase 07 measured the latency of the underlying
failure at 58.8–59.4 s per protected call, and corrected the retry arithmetic to `redis-py` 8.0.0's
library defaults — `Retry(ExponentialWithJitterBackoff(base=0.01, cap=1), retries=10)` with
`socket_timeout=socket_connect_timeout=5` — none of which any project code sets, giving ~11 attempts
≈ 55 s before the exception surfaces.

**Consequence** — During one Redis outage the same user-visible action resolves three ways: rate-limited
surfaces return 429, protected reads return 401 after ~59 s, and logout returns a 500 after ~59 s while
**leaving the session live** — the refresh cookie is still in the browser and the token is still valid
server-side, so a user who is told their logout failed is nonetheless still authenticated and has no
action that can end the session. An admin who deactivates a user during the outage gets a 500 and a
state they cannot distinguish between "deactivated" and "not deactivated". A registration that stores a
temporary password during the outage proceeds with nothing stored, and the later verification attempt
finds `None` — the failure surfaces as a user-visible verification rejection with no cause recorded
beyond one `logger.error`.

**Recommendation** — Give every job one declared failure mode and bound its latency. Set
`socket_connect_timeout` and `socket_timeout` explicitly in `core/redis_client.py` (both
`get_redis_client` and `get_async_redis_client` pass no timeout at all today) and pass
`socket_connect_timeout=1, socket_timeout=1, retry_on_error=False` for the revocation checks, so a
dependency outage produces a fast, deliberate answer instead of a 59-second hang. Move
`delete_secure_cookie` in `logout` ahead of the revocation writes so the client is always signed out
locally even when the marker cannot be written, and wrap the admin deactivation's Redis call so a
revocation failure is reported as a distinct, retryable error rather than a generic 500.

### OPS-013 — `client_max_body_size` and `UPLOAD__MAX_FILE_SIZE_MB` are coupled by nothing but a comment, and the tier that enforces the limit cannot read the setting

**Severity** — MEDIUM

**Zone** — The fronting tier: transport security, certificate lifecycle, and what is exposed

**Observation** — Two tiers declare the same limit with no shared source. `nginx.conf:18` hard-codes
`client_max_body_size 100m` (and the commented HTTPS block repeats it at `:67`). The application reads
`UPLOAD__MAX_FILE_SIZE_MB` (`config.py:381`, `max_file_size()` at `:903-905`), which
`docker-compose.yml:132` supplies as `${UPLOAD__MAX_FILE_SIZE_MB:-100}` and `.env.production:37` sets to
`100`. `nginx.conf:17` states the coupling in a comment — "must match backend max_file_size" — and
nothing enforces it: the nginx container receives no environment variable at all
(`docker-compose.yml:239-269` has no `environment:` block), and the nginx image's entrypoint does not
template `nginx.conf` (it is bind-mounted verbatim, `docker-compose.yml:246`).

**Evidence** — `nginx.conf:17-18`; `docker-compose.yml:246` (`:ro` bind mount, no template substitution);
`docker-compose.yml:239-269` (no `environment:` on `nginx`); resolved production `nginx` service has
neither an `environment` nor a `configs.template` key.

**Consequence** — The two numbers can only agree by coincidence. Raising
`UPLOAD__MAX_FILE_SIZE_MB` above 100 leaves the edge tier refusing bodies the application would accept —
a 413 for every oversized upload, on a setting the operator believes they changed. Lowering it below 100
lets nginx stream up to 100 MB into the app before the app rejects it, so the bandwidth and the disk
write are spent on a request that was always going to fail — and phase 07 has already shown what a large
rejected body does to the shared log key on this stack. Neither direction is visible to the operator as
a configuration error; both present as a mysterious 413 or a mysterious upload failure.

**Recommendation** — Pick the owning tier. Either drop `client_max_body_size` from `nginx.conf` and let
the application be the single authority (accepting that nginx's 413 will then be the limit for very large
bodies, which is a legitimate policy to state), or template the file through the nginx image's
`/etc/nginx/templates` mechanism with `${UPLOAD__MAX_FILE_SIZE_MB}` and pass the variable from compose.
Whichever is chosen, delete the "must match" comment or replace it with the mechanism that makes it
true.

### OPS-014 — The hardened runtime boundary exists on `app` alone, and the dev overlay comments describe a restriction the production file never sets

**Severity** — MEDIUM

**Zone** — Effective runtime posture per service, after every layer is merged

**Observation** — `app` is the only service carrying a runtime boundary: `read_only: true`,
`security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]` (`docker-compose.yml:134-141`). `nginx`
carries `read_only: true` plus a tmpfs list but deliberately no `no-new-privileges` or `cap_drop` —
`docs/11-guides/docker.md:380-382` explains why, and that reasoning holds. `rq-worker`, `migrate`, `db`
and `redis` carry none of the three. `rq-worker` is the service that parses attacker-supplied CSV with
Polars and writes to `app_data`; `migrate` is the step that holds the superuser credential and runs
before every gate. Meanwhile `docker-compose.override.yml:149-150` reads
`# Override production read_only for development (needs write access for processing)` immediately above
`read_only: false` — a description of an arrangement that the production definition does not have.

**Evidence** — Resolved production config: `app.read_only=True`, `rq-worker.read_only=` (unset),
`migrate.read_only=` (unset). Live confirmation that the engine applies what is declared:
`docker inspect mkobi-app-1` → `Memory=1073741824 NanoCpus=1000000000 CapDrop=[ALL]
SecurityOpt=[no-new-privileges:true] User=app` — so `deploy.resources.limits` *is* honoured by Compose
v2 for every service that declares one, and the asymmetry is in the file, not in the engine.
`docker-compose.yml:134-141` vs the absence of any `read_only` key in the `rq-worker` block at `:176-233`.
Override comment at `docker-compose.override.yml:149`.

**Consequence** — The single boundary that would blunt a parser or library escape is drawn around one of
the two services that execute the same untrusted-parsing code, and around neither of the two services
that hold the broadest credentials. Separately, the override comment tells a maintainer that `rq-worker`
is read-only in production; a maintainer who reads it will not discover that it is not, and will not
know that the dev overlay's `read_only: false` is a no-op rather than a relaxation.

**Recommendation** — Extend `read_only: true` + `cap_drop: [ALL]` + `no-new-privileges:true` to
`rq-worker` and give it the same tmpfs treatment `nginx` uses for the paths it must write, once its
`app_data` mount is accounted for. Apply `no-new-privileges` to `migrate` too — nothing in `alembic
upgrade head` needs privilege escalation. Correct the override comment in the same change so it
describes the file it sits in.

### OPS-015 — `deployment.md` describes a system that does not exist: a profile-gated worker, a registry rollback, and a migration rollback that cannot execute

**Severity** — MEDIUM

**Zone** — Operational claims as testable artefacts

**Observation** — Three documented procedures fail against the deployed host. (a) `deployment.md:188-195`
states "Services with `profiles: [production]` ... **rq-worker** — Redis Queue worker"; the deployed
`rq-worker` has no `profiles:` key and starts with the base file —
`docker compose ... config --services` returns `redis, db, migrate, rq-worker, app` with no profile at
all, and only `nginx` appears under `--profile production`. `docs/11-guides/docker.md:58-66` states the
correct arrangement ("`nginx` is the only profile-gated service in the project"), so the corpus
contradicts itself. (b) `deployment.md:306-320` is the rollback procedure: `docker images mkobi/app`,
`docker pull mkobi/app:<previous-tag>`, "ensure you have versioned tags pushed to your registry". No
compose service declares an `image:` key, no registry is named, and no push step exists — the resolved
`app` service has an empty `image`, so the only artifact that exists is the local `mkobi-app:latest`,
overwritten by the next build. (c) `deployment.md:326-338` and `:286` tell the operator to run
`docker compose ... exec app uv run alembic downgrade -1`, `alembic current`, `alembic history` and
`/bin/bash` inside `app`.

**Evidence** — (a) `docker compose -p auditverify --env-file docker/.env.production -f
docker/docker-compose.yml config --services` → `redis, db, migrate, rq-worker, app`; with
`--profile production` → `db, migrate, app, nginx, redis, rq-worker`. (b) resolved `app.image` is `''`;
`docker images 'mkobi*'` shows only `:latest` tags, all untagged-by-version. (c) Live, inside the running
container: `docker exec mkobi-app-1 sh -c 'which uv'` → no output, exit 1; `uv --version` →
`sh: 1: uv: Permission denied`, exit 127. Cause is static and identical in both the `dev` and `prod`
stages: `Dockerfile:52`/`:86` install `uv` into `/root/.local/bin` while `:122`/`:172` set `USER app`,
so the binary sits behind root-only permissions — and in production `read_only: true` would block `uv`
from syncing anyway.

**Consequence** — (a) An operator who wants to stage the worker separately cannot; it is already in the
base stack, and the doc's own `production` profile also switches on the reverse proxy as a side effect,
so following the doc to add "just the worker" adds nginx. (b) There is no image rollback: `docker pull`
of a previous tag cannot succeed because no such tag was ever published, and the local `:latest` is
overwritten in place, so the documented revert target does not exist. Combined with OPS-003 (the client
bundle lives outside any image) **neither half of the deployed system is revertible** — the
`docs/10-deployment/deployment.md:302` promise of "safely roll back to a previous stable state" is not
achievable by the procedure the same document gives. (c) The migration rollback commands exit 127 and
change nothing; an operator who runs them believes a downgrade happened. The consequence is
workaroundable (alembic can be run via the `migrate` service, and `docker compose exec app alembic ...`
uses the venv on `PATH`), which is why this is MEDIUM rather than HIGH — but the workaround is nowhere
written down.

**Recommendation** — Correct `deployment.md` to match `docker.md`, which is already right: `nginx` is the
only profile-gated service. Replace the image-rollback section with the mechanism that would make it
true — give `app` an `image: ${REGISTRY:-mkobi}/app:${TAG:-latest}` coordinate, and either add a
publish step or state plainly that rollback is `git checkout <previous-ref>` followed by a rebuild, which
is the only revert target that exists today. Replace every `uv run ...` in the operational corpus with
`alembic ...` (the venv is on `PATH` via `Dockerfile:163`) or move the migration commands onto the
`migrate` service, and add the `docker compose exec app alembic downgrade -1` form to `Makefile.ps1`
so the corrected procedure has an entry point.

### OPS-016 — Every external input that can change the built artifact without a source change is fetched by tag or by an unverified script, and no updater covers any of them

**Severity** — MEDIUM

**Zone** — What decides the artifact's content, per input class

**Observation** — The inventory: (i) five base images, all tag-pinned but none digest-pinned —
`node:20-alpine` (`Dockerfile:10`), `python:3.12-slim-bookworm` (`:28`, `:64`),
`postgres:18-bookworm` (`docker-compose.yml:17`), `redis:7.4-alpine` (`:158`),
`nginx:1.27-alpine` (`:240`); (ii) the `uv` installer, fetched at build time by
`curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh` with `UV_VERSION` pinned to `0.11.16`
(`:51-52`, `:85-86`) but **no checksum and no signature**; (iii) Debian and Debian-security packages
resolved unpinned by `apt-get install` against a configurable `DEBIAN_MIRROR` build arg (`:31-48`,
`:66-82`); (iv) `npm ci` from `frontend/package-lock.json` and `uv sync --frozen` from `uv.lock`
(`:18`, `:107`, `:136`, `:162`) — these two *are* lock-pinned and are the only inputs with integrity
guarantees. One target is built twice with different inputs: `app` uses
`target: ${DOCKER_TARGET:-prod}` with an explicit `UV_VERSION` build arg (`docker-compose.yml:88-90`),
while `migrate` and `rq-worker` use `target: prod` with **no** build args (`:59`, `:180`) — so a
`DOCKER_TARGET`-driven build produces one `app` image and two other images whose `uv` came from the
`ARG` default, which happen to agree today only because nothing overrides `UV_VERSION` at the call site.
No automated updater (no Dependabot/Renovate config, no `docker scout`/`trivy` policy, no scheduled
rebuild) covers any of these classes; the only scan tooling in the repository is the unwired
`docker/scripts/scan-images.ps1`.

**Evidence** — `Dockerfile:10,28,64`; `:31`, `:66` (`ARG DEBIAN_MIRROR`); `:51-52`, `:85-86` (the `curl |
sh` lines, no `-o` checksum file, no `sha256sum -c`); `docker-compose.yml:17,158,240`;
`docker-compose.yml:88-90` vs `:56-59` and `:177-180`. `Dockerfile:107,136,162` for the lock-pinned
inputs. `Get-ChildItem -Recurse .github` returns nothing.

**Consequence** — Three of the four unpinned classes can change the artifact with no change to the
repository and no record of what changed: a retagged `python:3.12-slim-bookworm` or `node:20-alpine`
produces a different image from an identical Dockerfile; a compromised or silently-modified
`install.sh` at that URL executes as root in the build with no verification; and the
`${DOCKER_TARGET:-prod}` / no-args split means `app` and `migrate` can be built from two different
toolchains in the same `up`. The consequence is bounded — nothing here is a secret or a privileged
action, and the lockfiles do cover the application's own dependencies — so this is a supply-chain
hygiene finding rather than an active exploit.

**Recommendation** — In priority order, and none of it needs a new tool: (1) pin the five images by
digest (`image@sha256:…`) in the compose files, which costs nothing at runtime and makes every build
reproducible; (2) replace the `curl | sh` with a checksum-verified install
(`curl -o /tmp/uv.sh … && echo "$SHA256 /tmp/uv.sh" | sha256sum -c - && sh /tmp/uv.sh`) for both
stages; (3) give `migrate` and `rq-worker` the same explicit `UV_VERSION` build arg as `app` so the
three services cannot diverge; (4) either wire `docker/scripts/scan-images.ps1` into a scheduled run or
delete it, so the repository does not carry an unwired scanner.

## Distribution

The findings concentrate on the composition between the compose file and the application, not inside
any single component. Of sixteen findings, nine name `docker/docker-compose.yml` as one of the two
subjects, and five more name `Makefile.ps1`, `docker/Dockerfile` or `docker/nginx/nginx.conf`. The
single heaviest carrier is `docker/docker-compose.yml`: it is implicated in OPS-001 (the unbacked
`redis_data` volume), OPS-002 (the worker that never works), OPS-003 (the host bind mount that defeats
rollback), OPS-009, OPS-011, OPS-013, OPS-014 and OPS-016, and the four phase-02 remediations landed in
it are all confirmed correct. The second cluster is the operational corpus: `docs/10-deployment/
deployment.md` is wrong or unusable in three places (OPS-015) and `docs/11-guides/docker.md` is wrong
about the queue (OPS-002) and wrong about the log file (OPS-008), while `docs/05-health/health-api.md`
understates the health surface (OPS-004). Two findings are properties of the deployed *runtime* rather
than of any file: the uvicorn respawn loop (OPS-011) and the Redis failure-mode divergence (OPS-012).

## Cross-Finding Analysis

Two causes account for thirteen of the sixteen findings.

**The deployed artefact has no versioned identity.** `app` and the other built services carry no
`image:` coordinate and no tag, so the local `:latest` is overwritten in place (OPS-016); the SPA that
nginx serves lives in an unversioned host directory that no build step populates (OPS-003); and the
documented rollback names a registry that has never been pushed to (OPS-015). OPS-003 and OPS-015 share
this cause, and between them they mean neither half of the system can be reverted to a previous
known-good state — which is also what makes OPS-010 and OPS-011 (no verified restore, no terminal
startup state) unrecoverable in practice.

**The operational corpus describes the intended system rather than the running one.** The RQ worker is
documented as the production queue and is not (OPS-002); `deployment.md` documents a profile-gated
worker that is unconditional, and `docker.md` contradicts `deployment.md` on the same point (OPS-015);
`docker.md` documents one rotating log file and the deployment runs five (OPS-008); `health-api.md`
publishes a two-component health surface for a three-dependency request path (OPS-004); and the health
contract, the log volume, the Redis store and the backup directory are each described as if one
component owned them, when in each case the ownership is split or absent. A reader who follows the
docs is wrong about the queue, wrong about the rollback, wrong about the logs and wrong about what
health means.

The remaining three — OPS-005, OPS-006, OPS-007 — share no cause with each other or with the two
clusters above; they are the vacuous-control, the lost-edge-log and the absent-metrics-surface cases and
each stands alone.

## Roadmap

Ordered by cause, not by severity. Each step names what must be true before the next begins.

1. **Give the artefact a revertible identity** (OPS-016, OPS-003, OPS-015). Set an `image:` coordinate
   with a tag for every built service; move the SPA into the image so nginx consumes it from a stage
   rather than a host directory, or add a `fe-build` target and a preflight check. *Before step 2:*
   there must be an artefact a rollback can select, or step 2 has nothing to restore into.

2. **Make the controls non-vacuous** (OPS-005, OPS-007, OPS-011). Add the exit-code and
   existence/verifiability assertions to `backup` and `restore`, print the restored `alembic_version`, add
   `rehearsal-restore`, add the `redis` / `alembic_version` / `stuck-processing-count` fields to
   `/health/detailed`, and give the app lifespan a terminal exit. *Before step 3:* an operator must be
   able to tell a successful recovery from a failed one, or the next step's fixes cannot be verified.

3. **Close the gap between the documented and deployed queue** (OPS-002, OPS-015). Route `enqueue_job`
   through RQ or delete the `rq-worker` service, and correct `deployment.md`'s profile and rollback
   sections against `docker.md`. *Before step 4:* the file that gates every later change should not
   describe a worker arrangement that does not exist.

4. **Close the store's failure domain and protect its contents** (OPS-001, OPS-012, OPS-004). Add
   explicit timeouts and a declared failure mode per Redis job, reorder `logout` so the cookie is always
   cleared, add the Redis persistence artifact to `backup`, and add the `redis` component to the health
   surface. *Before step 5:* the auth path must have a bounded, observable answer before wider reliance
   on it is safe.

5. **Draw the runtime boundary and shrink the credential set** (OPS-014, OPS-013, OPS-009). Extend
   `read_only`/`cap_drop`/`no-new-privileges` to `rq-worker` and `migrate`, add a `tools` service for the
   gates, and pick one owner for the upload body-size limit. Independently cheap; sequenced last only
   because each step above gives the next a way to verify itself.

6. **Restore the edge and worker log streams** (OPS-006, OPS-008). Point nginx at
   `/dev/stdout`/`/dev/stderr`, and reduce the application to one writer for `LOGGING__LOG_FILE`.

## Rollout Safety

Steps 1 and 2 change observable behaviour. Giving the built services an `image:` coordinate changes what
`docker compose up` pulls and creates: an operator who has been relying on the local `mkobi-app:latest`
being rebuilt in place must now pass `--build` (or bump the tag) for a source change to take effect —
without that, a deploy silently reuses the existing image. Moving the SPA into the image removes the
`../frontend/dist` bind mount; anyone who has been editing `frontend/dist` on the host to test a bundle
will find their edits ignored, and the container's served asset will come from the build. Both are
visible immediately on the first `docker compose up` and revert by restoring the previous compose file
and re-running the host build; neither touches data.

The backup and restore assertions in step 2 are the one step that can *destroy* something. Adding
`psql -f globals.sql` to `Invoke-Restore` writes cluster roles, and `pg_restore --clean --if-exists`
already drops objects before recreating them. Sequence it so the assertions are added and run against a
scratch database first, and confirm the `rehearse-restore` target creates and drops its own database
before anyone points it at `bidb`. Reverting is a `git checkout` of `Makefile.ps1`; the restore path
itself is unchanged, so the revert carries no additional data risk.

Giving the app lifespan a terminal exit changes a crash loop into a container exit. `restart:
unless-stopped` will then apply Docker's backoff, which means a genuinely transient startup failure
takes longer to recover from than the current 35-second respawn cycle. That is the intended trade, but
it should be verified against a real slow-start case (a large `migrate`) before it is relied on.

## Appendices

### Appendix A — Independent verification of the phase-02 remediation claims

Requested explicitly. Method: `git show` of both commits, then re-derivation of the current state from
the resolved production compose (`docker compose -p auditverify --env-file docker/.env.production -f
docker/docker-compose.yml config --format json`), extracting only `ENV`, `DATABASE__USER`, a boolean
comparing each service's resolved `DATABASE__PASSWORD` against the superuser value, the presence of
`DATABASE__ADMIN_PASSWORD`, and `RATE_LIMITER_FAIL_CLOSED` / `UPLOAD__MAX_FILE_SIZE_MB` /
`LOGGING__JSON_LOGGING`. **No secret value was read out or recorded.** Run against `HEAD` at the time of
the check (`eeb9a5e`); the two commits' diffs are unchanged by the later `config.py` work.

| Claim | Commit | Verdict | Evidence |
|---|---|---|---|
| **CFG-001** production tier label taken from `--env-file` | `8505a62` | **CLOSED** | `ENV` is now a literal `production` in the `environment:` map of `migrate`, `app` and `rq-worker` (`docker-compose.yml:64,99,190`) rather than `${ENV:-production}`. An `environment:` value containing no interpolation cannot be overridden by `--env-file`. Resolved output: `migrate ENV=production`, `app ENV=production`, `rq-worker ENV=production`, with the shipped `docker/.env.production` whose `ENV` line is commented out. `.env.production:6-7` documents the change. `db` and `redis` carry no `ENV` and do not read it; the dev overlay still flips all three to `development`, as it should. |
| **CFG-004** Postgres superuser password injected into `app` and `rq-worker` | `8505a62` | **CLOSED for both** | `DATABASE__ADMIN_USER`/`DATABASE__ADMIN_PASSWORD` were deleted from `app` and `rq-worker` (`docker-compose.yml:96-112`, `:187-204`). Resolved: `app DATABASE__USER=mkobi_app`, `rq-worker DATABASE__USER=mkobi_app`, and for both `dbPwdEqualsSuper=False` — the resolved `DATABASE__PASSWORD` is `${MKOBI_APP_PASSWORD}`, not the superuser value. `migrate` still receives the superuser credential (`DATABASE__USER=postgres`, `dbPwdEqualsSuper=True`); that is the documented least-privilege split at `deployment.md:240-251` and the one-shot step the phase-10 brief names as legitimately broadest, so it is not a residual of CFG-004. |
| **CFG-005** `.dockerignore` missed the build context | `044e630` | **CLOSED** | The four root-anchored patterns (`.env`, `.env.example`, `.env.local`, `.env.*.local`) matched nothing in this repository and did not cover `docker/.env.production`; they are replaced by `.env*` (context root) plus `**/.env*` (every depth), with `*.dump`, `backups/` and `.ai/` added. Docker's pattern matcher compares path segment-wise, so the pair covers all depths including the root. No `COPY`/`ADD` in `docker/Dockerfile` or `docker/Dockerfile.frontend.dev` names an env file, a `*.dump` path, `backups/` or `.ai/`, and `!README.md` is preserved for `Dockerfile:105,134,158`. The `.dockerignore` is at the context root (`context: ..`), which is where the engine looks. |
| **CFG-006** `RATE_LIMITER_FAIL_CLOSED` and `UPLOAD__MAX_FILE_SIZE_MB` supplied by no deployment | `8505a62` | **CLOSED, twice over** | `docker-compose.yml:127-129` (app) and `:208-210` (rq-worker) now supply both as `${VAR:-default}`; `docker/.env.production:37,44` declares the same values. Resolved with the shipped `docker/.env.production`: `app RATELIMIT=true MAXSIZE=100`, `rq-worker RATELIMIT=true MAXSIZE=100`. Closed even if the env file is not supplied, because the compose defaults alone are sufficient — the documented production command at `deployment.md:167` passes no `--env-file` and still resolves both. `migrate` supplies neither, which is correct: it serves no request and instantiates no rate limiter. |

**Two residuals found while verifying, neither of which reopens the four claims.** (i) `5f1d9ee` later
added `UPLOAD__TEMP_DIR` to `migrate` but left CFG-006 alone there, which is correct. (ii)
`docker-compose.yml:120-123`'s comment asserts that `config.py` "rejects it when `ENV=production`" for
the CORS default — that guard is `Settings.validate_cors_origins_not_placeholder`
(`config.py:596-614`), added by the same `config.py` remediation series rather than by `8505a62`, and it
is now reachable because CFG-001 pinned the tier. The comment is accurate as of `HEAD`.

### Appendix B — Commits landing during this audit, and whether they touch an audited file

The audit read the repository at `b23a9cb` and finished at `eeb9a5e`. Two further commits landed after
the work had started (`8747be7`, `eeb9a5e`) and one between (`5f1d9ee`); the working tree went from
`src/mkobi/config.py` + `tests/test_config.py` modified to clean as those edits were committed. No
finding in this report depends on a file any of these commits changed, except where noted.

| Commit | Subject | Touches a file audited here? |
|---|---|---|
| `044e630` | exclude credential env files, dumps and audit artefacts from the build context | **Yes** — `.dockerignore` (Appendix A, CFG-005) |
| `8505a62` | pin the production tier, wire the unsupplied settings, drop the superuser credential | **Yes** — `docker/docker-compose.yml`, `docker/.env.production` (Appendix A, CFG-001/004/006; OPS-009, OPS-011, OPS-013, OPS-014, OPS-016 all read the file this commit edited) |
| `2d23c27` | reject shipped credential placeholders and empty admin credentials in production | Partly — `src/mkobi/config.py`, `src/mkobi/db/starter.py`. Read for OPS-009 (the credential set a gate container receives). No effect on this report. |
| `c3c0a61` | reject the shipped `CHANGE_ME_ADMIN_USERNAME` placeholder in production | Same files. No effect. |
| `5a2cfb6` | hoist the admin credential guard so both call sites share one implementation | Same files. No effect. |
| `b23a9cb` | restrict the `_FILE` secrets source to secret fields; make the CORS wildcard refusal reachable | **Yes** — `src/mkobi/app.py` (the CORS guard removal), `src/mkobi/config.py`. The `app.py` hunk moved the production CORS check into `create_app()`; the health handlers at `app.py:248-307` that OPS-004 rests on are untouched, and the measured `/health` and `/health/detailed` responses above were taken at this commit. |
| `8747be7` | make the non-secret `_FILE` regression test discriminate against the unfixed source | No — `tests/` only. |
| `5f1d9ee` | pin the upload temp dir for the `migrate` service | **Yes** — `docker/docker-compose.yml`, `docker/docker-compose.override.yml`. Adds `UPLOAD__TEMP_DIR` to `migrate` in both files. Re-read; no finding changes. Note the `migrate` service does not mount `app_data`, so it writes that path into the container's own layer — harmless for a migration run, and not filed. |
| `eeb9a5e` | remove unread configuration fields; make the upload temp dir absolute | **Yes** — `src/mkobi/config.py`. Re-read for OPS-016 (the external-input inventory): no effect. |

### Appendix C — What was verified at runtime, and how

All runtime evidence came from the already-running `-p mkobi` dev stack and from `docker run` probes
against the local `mkobi-app` image. `.\Makefile.ps1 config` and `config-test` were **not** run and
their output never captured; every resolved-compose inspection was filtered to non-secret keys before
display, and the credential comparison in Appendix A is reported as a boolean.

| Measurement | Command | Result |
|---|---|---|
| Effective resource/security posture | `docker inspect mkobi-app-1 --format ...` | `Memory=1073741824 NanoCpus=1000000000 CapDrop=[ALL] SecurityOpt=[no-new-privileges:true] User=app` — `deploy.resources.limits` **is** applied by Compose v2; a "declared limit the engine ignores" finding would have been false and was not filed. |
| Redis key inventory | `redis-cli --scan`, `info keyspace`, `keys 'rq:*'` | 3 keys, all `rq:*` worker registrations; no queue list, no rate-limit, blacklist or `temp_pwd` key. Basis for OPS-001, OPS-002. |
| RQ worker liveness | `docker logs --tail mkobi-rq-worker-1` | `*** Listening on default...` then only `cleaning registries` every ~13 min for ~3 h. Zero jobs. Basis for OPS-002. |
| Health surface | `GET /health`, `GET /health/detailed` | `200 {"status":"healthy","database":"connected"}`; detailed returns exactly two components (`database`, `static_files`), Redis absent. Basis for OPS-004. |
| `uv` executability as the runtime user | `docker exec mkobi-app-1 sh -c 'which uv; uv --version'` | exit 1, then `Permission denied` exit 127. Basis for OPS-015. |
| Worker-process duplication of log records | `docker run --rm … LOGGING__LOG_FILE=/tmp/probe.log … uvicorn --workers 2` | `Configuring CORS…` ×3, `DB connection attempt N/5 failed` ×2 each, `Shutting down application...` ×2, all as JSON from all three processes. Basis for OPS-008. Refuted my initial hypothesis that `setup_logging()` would not run in spawn children — it does, once per process. |
| Startup-failure respawn loop | `docker run --rm … uvicorn --workers 2` (DB unreachable), `grep -c "Application startup failed"` over 70 s | **4** occurrences, repeating; no backoff, no terminal state. Basis for OPS-011. |
| `docker compose cp` failure premise | `docker compose … cp db:/tmp/does-not-exist.dump <tmp>` | exit **1**, `no container found for service "db"` — exactly the failure `Invoke-Backup` converts into a green "Backup created:" line. Basis for OPS-005. |
| `pg_restore` exit code with the shipped options | `pg_restore -d <scratch> --clean --if-exists <garbage>` (scratch DB created and dropped by the auditor) | exit 1 with and without `--exit-on-error`. Recorded as **methodology, not a finding**: the real gap in `Invoke-Restore` is the absent exit-code check and absent result inspection, not the option. |
| SPA provenance | `git ls-files frontend/dist \| Measure-Object -Line` | **0** — the served bundle is untracked and unignored. Basis for OPS-003. |
| Metrics/alert surface | `grep -rn 'prometheus\|/metrics\|opentelemetry\|alertmanager'` over `src/`, `docs/`, `docker/`, `Makefile.ps1` | 2 incidental hits in vendored/generated text; no exporter, no route, no rules. Basis for OPS-007. |

### Appendix D — Limits on this report

- **A full production stack was never stood up.** The production definition was resolved and inspected
  (`--env-file docker/.env.production`, plus `--profile production`), and every service was inspected in
  its merged form, but no production container was created — the `prod` target's build
  (`npm ci` + `vite build` + `uv sync --no-dev`) was not run, because it would have collided with the
  concurrent remediation team's use of the same Docker daemon. Claims that depend on running the `prod`
  image rather than the `dev` image — OPS-008 (the multiplier is 5 with `--workers 4`, measured at 3
  with `--workers 2`), OPS-016 (whether `uv` in the `prod` image is executable; the static cause is
  identical in both stages) — rest on the `dev` image plus source reading, and are marked as such.
- **No dependency outage was induced.** Phase 07 already paused Redis and measured the resulting latency;
  re-inducing it here would have taken the shared dev stack's authenticated path down while another team
  was working in it. OPS-004's consequence is therefore cited from phase 07 rather than re-measured, and
  OPS-012's failure modes are established from source, not from observation.
- **No backup was taken and no restore was run.** Both would have written into the repository's
  `backups/` directory and the `bidb` database, which the concurrent team owns. OPS-005 and OPS-010 rest
  on the entry-point source and on the live failure premise in Appendix C.
- **nginx was never started.** It is profile-gated and absent from the dev stack; starting it would have
  published port 80 on the host. OPS-006 and OPS-013 rest on `nginx.conf` and the resolved compose
  definition; whether an operator would notice a missing bundle depends on the healthcheck's behaviour
  against `try_files`, which is stated in OPS-003 as a consequence of the configuration rather than as
  an observation.
- **The `admin.py` deactivation write is not committed anywhere on the request path**
  (`admin.py:163-171` issues `db.flush()`; `user_repo.update` does not commit; `get_db_dependency`
  closes without committing). That is a production-code correctness question owned by another phase and
  is **not filed here**. OPS-001 relies on it only as an amplifier: whatever phase owns it, the Redis
  marker is what a deactivation actually enforces.
- **The dev stack was destroyed mid-audit by another actor** (`docker ps` at 17:0x showed `mkobi-db-1`
  gone while `mkobi_redis_data` and `mkobi_postgres_data` still existed), and was being recreated
  immediately afterwards. Every runtime measurement above was taken before that point and is internally
  consistent; nothing in the report depends on state that was destroyed. This is an artifact of the
  concurrent remediation programme, not a property of the system, and is not a finding.
