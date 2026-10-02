# Code Context — Audit Phase `10-production-ops`

## 1. Scope and method

| Item | Value |
|---|---|
| Report decomposed | `.ai/audit/99-validation/10-production-ops-validated-findings.md` (1241 lines) |
| Finding-ID prefix actually used | **`OPS-`** — `OPS-001` … `OPS-016`, no gaps |
| Report-level defects | **`VAL-10-001` … `VAL-10-006`** (phase-qualified, deviating from the flat `VAL-`; ruling in Appendix E) |
| Total items | 16 findings + 6 validation defects = **22 sections below** |
| Upstream provenance | `.ai/audit/10-production-ops/findings.md` (16 raw findings) |
| Sibling plans read | `01`…`08` + `09` (landed mid-audit) — frontmatter and scope-ruling rows only |
| Written by | Phase-1 (code-context) auditor. No production code, audit file, or existing plan was modified. Docker state was inspected read-only. |

**HEAD-vs-worktree split.** The brief named `cea2d06`; HEAD is now **`ab76989`**. A peer committed
`ab76989 fix(worker): give the aggregate rebuild a declared lock and a bounded wait` *during this
audit*, absorbing the four dirty files the brief described (`src/mkobi/config.py`,
`src/mkobi/workers/data_worker.py`, `tests/test_data_worker.py`,
`docs/06-backend/configuration.md`) plus the untracked `src/mkobi/db/advisory_lock.py` and
`tests/test_advisory_lock.py`. The working tree is now **clean of all code modifications**. Remaining
untracked files are the eight sibling plans, `_code-context/`, and two `.ai/tasks/*.yaml`.

**Method split — verified at runtime vs read.**

| Verified at runtime (read-only) | Read from source/docs only |
|---|---|
| 13 `${VAR:?}` failures with no `--env-file` (VAL-10-004/005) | `nginx.conf` log targets, `client_max_body_size` (nginx never started — profile-gated) |
| `app` healthy, `ReadonlyRootfs=false`, `CapDrop=[ALL]`, `Memory=1 GiB`, `User=app`, `LogDriver=json-file` | `prod`-tier behaviour at `--workers 4` (no `prod` build run) |
| `rq-worker` healthy, `CapDrop=<no value>`, `SecurityOpt=<no value>`, `Memory=512M` (OPS-014) | uvicorn respawn-loop source path (OPS-011) |
| Redis: 5 keys, **no `rq:queue:default`**, lease + `rq:queues` present | `cp` / `pg_restore` failure induction (not re-induced) |
| `/data/dump.rdb` present, 673 B, `appendonly no` (OPS-001) | `backup`/`restore` exit chain (logic is dispositive) |
| `/app/data/logs/` **empty** in the running dev app | `rehearse-restore` absence; absence of `/metrics` |
| `uv --version` → `Permission denied`, exit 127 (OPS-015c) | disk-budget arithmetic (no numbers ship today) |
| Dev stack: 6 services, `migrate` `Exited (0)`, no `nginx` |  |

The running dev stack is **stale relative to HEAD** (containers 3–25 h old, `app` built before
`ab76989`); runtime facts are reported as observed and flagged where that matters.

---

## 2. Per-finding context

### OPS-001 — Redis volume holds the only revocation record, no export path
**Verdict: substantiated** (mechanism refined).

- Anchors: `redis_data` declared at `docker-compose.yml:175` (mount) and `:308` (top-level) —
  report cited `:164`/`:278`; volume name `mkobi_redis_data` confirmed via `docker volume ls`.
  `Invoke-Backup` (`Makefile.ps1:279-290`) touches `postgres_data` only.
- **Refinement the report does not carry:** `/data/dump.rdb` **exists** (673 B, written
  `Oct 1 19:03`); `redis:7.4-alpine` ships default `save` directives, so a point-in-time RDB is
  produced without any explicit command. The defect is that **nothing exports it** and
  `Invoke-Backup` ignores it — not that no persistence command exists. OPS-001's own recommendation
  (`BGSAVE` + `docker compose cp`) targets a file already present.
- **Key inventory is incomplete.** Live `keys '*'` → `rq:worker:7e8a32ba…`, `rq:workers`,
  `rq:workers:default`, `rq:queues`, `mkobi:reconciler:stale_processing:lease`. Two of the five
  classes are absent from OPS-001's inventory: the reconciler lease (phase 02/03 subject) and
  `rq:queues` (RQ 2.x registry).
- Seams: `Makefile.ps1:279-290` + `:308-320` (`prune-backups` filters `*.dump` only — the report
  states this dependency; confirmed at `:314`); `docs/10-deployment/deployment.md:356` volume table.

### OPS-002 — RQ worker registered and health-checked, never received a job
**Verdict: already-fixed (code); documentation now stale in the opposite direction.**

- `src/mkobi/core/task_queue.py` is now **79 lines and RQ-only**: `DEFAULT_QUEUE_NAME = "default"`
  (`:26`), `get_rq_queue()` → `rq.Queue(...)` (`:29-49`), `enqueue_job` → `queue.enqueue` (`:52-79`).
  There is **no module-global `default_queue`, no `asyncio.Queue`, no `enqueue_with_worker`, no
  in-process drain loop**. `app.py:129-143` is now lease acquisition + orphan repair, not a drain
  loop. Every symbol OPS-002/TOPO-002 named as an anchor is **gone**.
- The fallback VAL-10-001 warned about is absent: `enqueue_job` raises `AppException(FILE_PROCESSING_ERROR)`.
- **New doc defects created by the fix** (phase 10 owns these per plan 02 row at `:2896`):
  `docs/10-deployment/deployment.md:215` still says rq-worker "Runs
  `/app/.venv/bin/rqworker --url redis://redis:6379/0`" — both compose files now run
  `["/app/.venv/bin/python", "-m", "mkobi.rq_worker_wrapper"]` (`compose.yml:196`,
  `override.yml:132`). `docs/11-guides/docker.md:614` healthcheck table still says
  `Redis(...).ping()` / "disabled in the dev override" — both tiers now run the registry probe.
  `docs/11-guides/docker.md:621-622` itself defers that row to
  `task-queue-migration.md#decision-record` — phase 10's, per plan 05 `C05-9`.
- **Load-bearing test contract the report never mentions:**
  `tests/test_config.py:1215-1270` `TestRqWorkerComposeWiring` reads both compose files **as text**
  and asserts `mkobi.rq_worker_wrapper` present, `rqworker` absent, `disable: true` absent,
  `Redis(` absent, `redis-cli` absent. `_rq_worker_block` (`:1236-1254`) raises
  `AssertionError: rq-worker service not found` if the key is removed. **This converts TOPO-002's
  open "route through RQ *or* delete the service" choice into a test-contract question** (see 6.1).

### OPS-003 — SPA served from an unversioned host directory
**Verdict: substantiated** (and understated — three carriers, not two).

- `../frontend/dist:/usr/share/nginx/html:ro` (`compose.yml:281`); `nginx.conf:49-53` serves it;
  `Dockerfile:170` bakes `--from=frontend-builder /app/frontend/dist ./frontend/dist` into the app
  image (report cited `:166`).
- **Third carrier the report does not name:** `app.py:391-460` `_setup_static_files()` mounts
  `Path("frontend/dist")` — i.e. the *image* copy — when it exists. With `nginx` absent (dev tier,
  or production before `--profile production`) the app serves the SPA itself; with `nginx` present it
  serves the *host* copy. The two are different artefacts under independent lifetimes.
- `Makefile.ps1` has no `fe-build` target (help `:75-81`, `:95-98`; dispatch `:389-438`).
  `git check-ignore` confirms `frontend/.gitignore:11:dist`; `git ls-files frontend/dist` → 0.
- Seams: `compose.yml:281`, `Dockerfile:170`, `app.py:391-460`, `.gitignore` blindness,
  `deployment.md` rollback section. Plan 06 `C06-4` assigns phase 10 the compose layout.

### OPS-004 — Health contract cannot see Redis
**Verdict: merged into EXT-001 (probe half substantiated); consumer half already-fixed.**

- Probe half holds: `/health` (`app.py:297-316`) executes only `SELECT 1` and returns
  `{"status","database"}`; `/health/detailed` (`:318-379`) has **no `redis` key** (report cited
  `:248-267` / `:269-307`). **Component count is now three**, not two — `database` (`:336-346`),
  `static_files` (`:350-353`), `stale_processing_reconciler` (`:360-376`).
- Consumer half **already-fixed**: `compose.yml:274-276` `nginx → app: condition: service_healthy`
  (report recorded `service_started`); the dev override has **no** `healthcheck:` key and comments
  at `:120-122` that it inherits, so `up --wait` gates on `/health`; `Makefile.ps1:116` uses
  `up -d --wait --wait-timeout 180`. Confirmed at runtime: `app` is `Up 11 hours (healthy)`.
  Plan 07 `HO-3` states the same and forbids repeating the "disabled in dev" claim.
- **Test that pins the opposite of the probe fix:** `tests/test_health.py:217-238`
  `test_health_still_healthy_when_redis_down` asserts `/health` → 200 and
  `== {"status":"healthy","database":"connected"}` and `/health/detailed` → `"healthy"` **with
  every Redis call raising `OSError`**. Adding Redis to `/health` breaks it. This is exactly phase
  07's `DP-2` ("the fate of the exact-dict assertion"). `test_health.py:110-126` asserts component
  *presence*, not an exact set — adding `redis` is safe there (report confirmed).

### OPS-005 — `backup` reports success unconditionally; `restore` never reads its result
**Verdict: substantiated** — `Makefile.ps1` line numbers are **byte-exact** against the report.

- `Invoke-Backup` `:279-290`: `pg_dump` checked at `:286`; `cp` at `:287` unchecked, no
  `Test-Path`, no length assert; `rm -f` `:288`; `Write-Host` `:289` unconditional.
  `Invoke-Restore` `:292-306`: `cp` checked `:303`; `pg_restore --clean --if-exists` `:304` result
  never read; `rm -f` `:305`. `exit $LASTEXITCODE` `:441` carries the trailing `rm`'s zero.
- **The PowerShell binary-redirection hazard documented in `.kilo/rules/commands.md` is currently
  avoided**: `backup` uses `docker compose cp` (`:287`), not `>`/`Out-File`/`Tee-Object`. Any
  rewrite of that line to a shell redirection reintroduces host-side corruption. `Invoke-PsqlC`
  (`:272`) uses `exec -T` for text, which is correct.
- **Additional vacuous control in the same class the report does not file:**
  `Invoke-Up` (`:114-125`) detects a failed `up --wait` (`$upExit` at `:117`) and prints guidance
  at `:119-124` but **never returns non-zero**; `exit $LASTEXITCODE` at `:441` then reports success.
  This is the same defect shape as OPS-005 and is *more* consequential now that `--wait` exists.
- `Show-Help` `:90-93` documents `backup`/`restore`/`prune-backups`; no `rehearse-restore`, no RPO/RTO.

### OPS-006 — nginx access/error logs on a tmpfs, absent from `docker logs`
**Verdict: substantiated.**

- `docker/nginx/nginx.conf:10-11` — `access_log /var/log/nginx/access.log`,
  `error_log /var/log/nginx/error.log`. No `/dev/stdout` or `/dev/stderr` anywhere in the file.
- `compose.yml:285-290` — `read_only: true` plus tmpfs on `/tmp`, `/var/cache/nginx`, `/var/run`,
  `/var/log/nginx`; `nginx.conf` bind-mounted `:ro` at `:280`; `profiles: [production]` at `:296-297`.
- No `logging:` key in any compose file — confirmed at runtime: `app` uses the default
  `json-file` driver. Application stream unaffected: `logging_config.py:102-109` `StreamHandler` on
  `ext://sys.stdout` (report's line numbers exact).
- **Contested ownership:** plan 04 `C04-5` assigns `nginx.conf`'s `log_format`/`access_log` half to
  phase 12 with "phase 10 on deployed composition"; plan 04 `:585` says phase 04 "may **request** it;
  it may not edit the file". OPS-006's edit is the same directive.
- `nginx` was never started (absent from the running stack, profile-gated) — the configuration is
  dispositive; the `/dev/stdout` change needs no image rebuild (bind mount replaces the base conf).

### OPS-007 — No metrics surface
**Verdict: substantiated** (evidence anchors drifted).

- **Router count is 11, not 8**: `app.py:285-295` registers `auth, users, dashboards, graphs,
  layouts, upload, data, client_errors, processing_configs, processing_logs, admin`. The two
  health handlers (`:297`, `:318`) remain the only non-`/api/v1` paths; no `/metrics` route exists.
- `/health/detailed` now has **three** components (see OPS-004). `alembic_version` is still absent.
- No `.github` directory, no exporter, no alert rule, no collector. `docker/scripts/scan-images.ps1`
  present and wired to nothing.
- **Ordering constraint upheld and now more delicate:** the `redis` field belongs to EXT-001's single
  `app.py` edit; phase 10 must not schedule a second one. `test_health.py:217-238` must be resolved
  by `DP-1`/`DP-2` before either field lands.

### OPS-008 — N rotating handlers write one file under `--workers 4`
**Verdict: substantiated** (one imprecision; not reproducible in the dev tier).

- `app.py:44-48` calls `setup_logging(...)` at module scope; `logging_config.py:111-122` installs
  `RotatingFileHandler` `maxBytes=10*1024*1024`, `backupCount=5` — **line numbers exact**.
  `Dockerfile:183` `--workers 4` (report cited `:179`). `compose.yml:129` and `:224` set
  `LOGGING__LOG_FILE: /app/data/logs/app.log` on `app` and `rq-worker`; `migrate` (`:60-86`) sets
  none, so the report's "currently names no service at all" holds.
- **Imprecision:** `logging_config.py:165-169` and `:175-179` pin `uvicorn` and `uvicorn.access` to
  `["console"]` only. `uvicorn.error` (`:170-174`), all `mkobi*` namespaces and `root` (`:181-184`)
  use `list(handlers.keys())` = both. So `uvicorn.access` records do **not** reach `app.log`;
  "duplicating every record" is overstated. The 4 × 6 × 10 MB ≈ 240 MB ceiling is unaffected.
- **Not observable in dev, by construction:** `override.yml:92` sets `LOGGING__LOG_FILE: ""`, and
  `logging_config.py:111` gates the file handler on truthiness. Runtime confirms
  `/app/data/logs/` is **empty**. Any fix must therefore be verified on a `prod`-tier run, which no
  report in this set has produced.

### OPS-009 — Quality gates receive the full production credential set
**Verdict: substantiated** — line-exact.

- `Makefile.ps1:222,226,230,260` all run `docker compose @DevCompose run --rm --no-deps app …`;
  `Invoke-Check` `:241-249` starts with `Invoke-Lint`. The `app` environment block
  (`compose.yml:111-144`) carries `JWT__SECRET_KEY:123`, `ADMIN_USERNAME:126`, `ADMIN_PASSWORD:127`,
  `CORS_ORIGINS:138`. `migrate` (`:259-265`) and `migrate` targets likewise.
- The dependency the report states holds: `Invoke-MigrationNew` (`:260`) and
  `Invoke-MigrationStatus` (`:264`) run `alembic`, which imports `Settings`. The
  `RUFF_CACHE_DIR`/`MYPY_CACHE_DIR` workaround is `override.yml:105-106`.
- **New adjacency:** `override.yml:105-106` exists only because the dev image drops to `USER app`
  with a root-owned `/app`. Any new `tools` service inherits the same problem.

### OPS-010 — Dump has no roles and no alembic state
**Verdict: substantiated** — line-exact.

- `Makefile.ps1:285` — `pg_dump -U postgres -d bidb -F c -f /tmp/mkobi.dump`, no `--globals`/`--roles`.
- `docker/init-scripts/01-create-app-role.sh` is mounted at `/docker-entrypoint-initdb.d`
  (`compose.yml:33`) and runs only on an empty data directory — its own header says so.
  `$BackupDir = 'backups'` (`Makefile.ps1:37`); `prune-backups` `:308-320`, manual, no scheduler.
  `migrate` is `restart: "no"` (`:91`).
- With CFG-004 landed, `app` and `rq-worker` run as `mkobi_app` (`compose.yml:118`, `:208`); the
  grants at `01-create-app-role.sh:23-42` are the *only* definition of runtime DB access outside
  cluster init. The artefact-completeness gap and the credential split are now load-bearing together.
- The two orderings the report adds hold: globals load **after** `pg_restore --clean --if-exists`;
  `alembic_version` must be printed from the **restored** database.

### OPS-011 — Lifespan failure becomes an unbounded respawn loop
**Verdict: substantiated**, with a new interaction.

- `app.py:170-178` re-raises `DatabaseNotFoundError` (`:170-172`), `SchemaNotFoundError` (`:173-175`)
  and catch-all `Exception` (`:176-178`). `Dockerfile:183` makes uvicorn's `Multiprocess` PID 1 at
  `--workers 4`, so `keep_subprocess_alive()` kills and replaces each dead child with no counter.
- **New interaction:** commit `b646ef1` made teardown **fail-isolated** — `app.py:179-229` wraps every
  release step in its own `try/except`. A terminal-exit remedy added to the `except` arms at
  `:170-178` executes **after** the `finally` completes, so the fail-isolated teardown still runs.
  That ordering must be preserved; a bare `sys.exit(1)` inserted *before* the `finally` would skip it.
- `compose.yml:101-102` gates `app` on `migrate: service_completed_successfully`, satisfied once and
  permanently. `restart: unless-stopped` does not act on `unhealthy`. No `--restart` backoff is
  configured, so today the loop is *fast*; a terminal exit trades that for Docker's backoff.

### OPS-012 — One Redis outage denies on some paths, admits on others
**Verdict: substantiated, with two un-filed sites now on the critical path.**

- All five filed sites hold: `core/security.py` rate limiter honours `fail_closed`;
  `core/redis_client.py:46-52` passes only `host, port, db, password, decode_responses` — **no
  timeout, no retry policy** (report's line numbers exact).
- **New site 1 — the only submission path:** `core/task_queue.py:43-48` builds
  `redis.Redis(host, port, db, password)` with **no timeout and no retry policy**. Since
  `enqueue_job` is now RQ-only, a Redis outage at enqueue time raises
  `AppException(FILE_PROCESSING_ERROR)` where the retired in-process queue previously absorbed it.
  **The TOPO-002 fix converted a Redis blip into a user-visible 500 on upload.** This is a new
  failure mode in OPS-012's exact zone, created by the fix for OPS-002.
- **New site 2 — a credential divergence:** `rq_worker_wrapper._build_redis_url()` (`:43-50`) builds
  `redis://{host}:{port}/{db}` and **omits `redis.password`**, while the producer
  (`task_queue.py:47`) passes it. With a password-configured Redis the worker and producer connect
  differently — the precise failure class `compose.yml:226-230` warns about, now on the password
  axis rather than the db axis. `check_redis_connection` (`:71`) and `check_worker_registered`
  (`:130`) also use `from_url` with no timeout.
- `RATE_LIMITER_FAIL_CLOSED` is wired `${…:-true}` on `app` (`:142`) and `rq-worker` (`:236`), and
  `docker/.env.production:49` declares it — the fail-closed arm is a **declared production policy**.

### OPS-013 — `client_max_body_size` and `UPLOAD__MAX_FILE_SIZE_MB` coupled by a comment
**Verdict: substantiated** — line-exact.

- `nginx.conf:17-18` (comment + `client_max_body_size 100m`), repeated in the commented HTTPS block
  at `:66-67`. The `nginx` service (`compose.yml:272-303`) has **no `environment:`** and mounts
  `nginx.conf` `:ro` at `:280`. Nothing templates the value.
- Application half is genuinely wired: `UPLOAD__MAX_FILE_SIZE_MB` is interpolated at `compose.yml:143`
  and `:237` and read through `config.py` (`LOGGING`-style `__` source chain, first in the tuple).
  The `nginx:1.27-alpine` `20-envsubst-on-templates.sh` entrypoint exists, so templating needs the
  file relocated to `/etc/nginx/templates/` and an `environment:` entry — no image change.

### OPS-014 — Hardened runtime boundary on `app` alone
**Verdict: substantiated** — confirmed at runtime in both directions.

- `compose.yml:150` `read_only: true`, `:152-153` `security_opt`, `:155-156` `cap_drop` on `app`
  only. The `rq-worker` block (`:191-266`) and `migrate` block (`:54-91`) declare none of the three.
- **Runtime proof:** `app` → `CapDrop=[ALL]`, `SecurityOpt=[no-new-privileges:true]`, `User=app`,
  `Memory=1073741824`; `rq-worker` → `CapDrop=<no value>`, `SecurityOpt=<no value>`,
  `Memory=536870912`. `deploy.resources.limits` **is** applied by this engine — the report's refuted
  hypothesis stays refuted, and the asymmetry is in the file.
- `app` shows `ReadonlyRootfs=false` at runtime because `override.yml:123` sets `read_only: false` —
  correct for dev; the production value is not observable without a `prod` run.
- **Report anchor correction is itself stale:** the overlay comment it relocates to `:153-154` is now
  at **`override.yml:163-164`** ("Override production `read_only` for development…"). The new
  `frontend` service (`:37-57`) and the new rq-worker healthcheck (`:168-177`) have shifted it again.
- `rq-worker` mounts `app_data` read-write (`compose.yml:241`), so `read_only: true` there needs the
  tmpfs treatment nginx uses. `migrate` writes no volume — `no-new-privileges` there is free.

### OPS-015 — `deployment.md` describes a system that does not exist
**Verdict: drifted — one sub-claim fixed, two hold, two new stale claims appeared.**

| Sub-claim | Report | Reality at `ab76989` |
|---|---|---|
| (a) profile-gated rq-worker | `deployment.md:190-193` says so | **Refuted/fixed.** `:186` "production profile; rq-worker starts either way", `:207` "nginx is the **only** service gated by `profiles: [production]`", `:212` "redis and rq-worker are **not** profile-gated". Now agrees with `docker.md:66-67`. The corpus no longer contradicts itself. |
| (b) registry rollback | `deployment.md:304-320` names `mkobi/app` | **Still holds.** `:401` `docker images mkobi/app`, `:404` `docker pull mkobi/app:<previous-tag>`. No compose service declares `image:`. |
| (c) `uv run …` inside containers | 7 lines | **Still holds.** `:283`, `:320`, `:322`, `:380`, `:419`, `:422`, `:425`, `:428`. Runtime: `uv --version` → `Permission denied`, exit 127. |
| (d) rq-worker command | *(not filed)* | **New.** `:215` still documents `/app/.venv/bin/rqworker --url …`; both tiers run `-m mkobi.rq_worker_wrapper`. |
| (e) migration advisory lock | *(not filed)* | **New.** `:316` says "`_apply_migrations()` method acquires … `pg_advisory_lock(42)`". `starter.py:352-357` states the lock is acquired **in `alembic/env.py`**; the constant `MIGRATION_ADVISORY_LOCK_KEY = 42` and the `pg_advisory_lock`/`pg_advisory_unlock` calls live at `alembic/env.py:56,58,116,125,132`. The method named in the doc is not the holder. Same claim in `docs/SPEC.md:141`. |
| volume/disk-budget section | *(handed over)* | `deployment.md:355-356` lists `app_data` and `redis_data` with no budget, no backup, no RPO/RTO. **Phase 10 owns it** (plan 06 `C06-4`, `C06-11`; plan 05 `C05-7`). |

`docker.md` corroboration: `:56-58` service tables, `:140`/`:145` nginx-waits-on-health,
`:286-287`, `:404-406` "the RQ worker is the production implementation".

### OPS-016 — Unpinned build inputs, no updater
**Verdict: substantiated** (one anchor drifted).

- Tag-pinned, no digest: `Dockerfile:10` `node:20-alpine`, `:28`/`:64` `python:3.12-slim-bookworm`,
  `compose.yml:17` `postgres:18-bookworm`, `:173` `redis:7.4-alpine`, `:273` `nginx:1.27-alpine`.
- `uv` by unverified pipe: `Dockerfile:51-52` and `:85-86`, `UV_VERSION` pinned, no checksum/signature.
  Debian packages unpinned against `DEBIAN_MIRROR` (`:31-48`, `:66-82`).
- Integrity-guaranteed classes: `npm ci` (`:18`), `uv sync --frozen` (`:107` dev, `:136` test,
  **`:166`** prod — report cited `:136`/`:162`).
- Target divergence holds: `app` uses `target: ${DOCKER_TARGET:-prod}` + `UV_VERSION` build arg
  (`compose.yml:94-99`); `migrate` (`:55-58`) and `rq-worker` (`:192-195`) hard-code `target: prod`
  with no args.
- `Get-ChildItem .github` returns nothing; `docker/scripts/scan-images.ps1` unwired.
- **The `rebuild` interaction the report notes is now sharper:** `Makefile.ps1:139-142`
  `Invoke-Rebuild` runs `build --no-cache` then `Invoke-Up`, and `Invoke-Nuke` (`:377-383`) runs
  daemon-global `builder prune -af` + `image prune -af`. Digest pins convert both into mandatory pulls.

### VAL-10-001 — OPS-002 duplicates TOPO-002
**Verdict: moot.** The code anchors are gone (`task_queue.py` is 79 RQ-only lines; no drain loop in
`app.py`). The duplication no longer exists to be merged. The *residual* is the pair of now-stale doc
rows (OPS-015(d), OPS-002) and the `TestRqWorkerComposeWiring` contract.

### VAL-10-002 — OPS-004 is a merge with EXT-001, not a co-owned cross-reference
**Verdict: upheld, and half discharged.** The probe-coverage mechanism is unchanged and remains
EXT-001's. The consumer half phase 10 retained has **already landed** (`nginx → service_healthy`,
dev healthcheck re-enabled, `up --wait`) — verified in compose and at runtime. Remaining phase-10
input to EXT-001: co-sign `DP-1`, and the 503 policy must be decided against
`RATE_LIMITER_FAIL_CLOSED=true` (`compose.yml:142`, `:236`).

### VAL-10-003 — OPS-008's writer count is four, not five
**Verdict: substantiated and currently unverifiable in dev.** The source-level claim holds
(`main.py:52-55` is the only `create_app()`; `app.py:266` the only CORS log; uvicorn's parent never
`config.load()`s). But `override.yml:92` blanks `LOGGING__LOG_FILE`, so the dev tier installs no file
handler at all and `/app/data/logs/` is empty at runtime. No `prod`-tier build has been observed in
this environment.

### VAL-10-004 — Appendix A's stated method cannot produce its output
**Verdict: substantiated, and worse than filed.** `docker compose -p mkobi -f docker/docker-compose.yml ps`
with no `--env-file` produced **13** `required variable … is missing a value` errors across
`db`, `migrate`, `app`, `rq-worker` — the report counted four. `docker/.env.production` is 49 lines
(not 44) and all five required secrets (`:10-14`) are commented out.

### VAL-10-005 — CFG-006 closed by citing an invocation that cannot start the stack
**Verdict: substantiated, and the residual has widened.** Reproduced: no `--env-file` → exit 1 with
13 interpolation errors. `deployment.md` still contains **no** `--env-file` reference, and its
production invocations (`:167`-area, `:170`) are unwired. `docs/10-deployment/security-checklist.md`
remains the third non-executing check. **Additionally:** `docker/.env.production:33` now has
`CORS_ORIGINS` **commented out**, so the compose default `["http://localhost:5173"]`
(`compose.yml:138`, `:222`) wins in production and `app.py:250-253` will refuse startup on the
placeholder-origin guard. An operator following the file's own instructions must set a fifth-and-
sixth value. CFG-001 is **half-closed**; the invocation half belongs to phase 10's OPS-015 class.

### VAL-10-006 — OPS-003's directory is git-ignored, not unignored
**Verdict: substantiated.** `git check-ignore -v` → `frontend/.gitignore:11:dist`; root
`.gitignore:13` `dist/` matches at any depth. `git ls-files frontend/dist` → 0. The consequence the
report draws (both operator recovery moves fail) is correct and now extends to three carriers.

---

## 3. Cross-cutting architecture and constraints

### 3.1 Topologies

| Tier | Compose invocation | Services | Images |
|---|---|---|---|
| Production (base) | `docker compose --env-file docker/.env.production -f docker/docker-compose.yml` | `db`, `migrate`, `redis`, `rq-worker`, `app` | `postgres:18-bookworm`, `redis:7.4-alpine`; `migrate`/`rq-worker`/`app` built |
| Production + edge | same, `--profile production` | + `nginx` (`compose.yml:296-297`) | + `nginx:1.27-alpine` |
| Development | `-f docker-compose.yml -f docker-compose.override.yml` | + `frontend` (`override.yml:37-57`) | `migrate`/`app` retarget `dev` |
| Test | `docker-compose.test.yml`, project `mkobi-test`, **no `--env-file`** (hermetic literals) | `test-db`, `test-redis`, `test-migrate`, `test-app` | `test-app` `healthcheck: disable: true` (`:156-157`) |

`Makefile.ps1:31-38` pins `-p mkobi` / `-p mkobi-test`. **No compose service declares an `image:` key** —
the only artefact coordinates are local `:latest` tags (confirmed in `docker compose ps`).

### 3.2 Dockerfile tiers

`frontend-builder` (`:10-22`, `npm ci` + `npm run build`) → `base` (`:28`, build tools) → `dev`
(`:102`) / `test` (`:132`, **copies both compose files at `:145` for `tests/test_config.py`**) →
`prod-base` (`:64`) → `prod` (`:160`, `uv sync --frozen --no-dev`, SPA `COPY --from` at `:170`,
`USER app` at `:176`, `HEALTHCHECK` at `:180-181`, `--workers 4` at `:183`).
`Dockerfile.frontend.dev` is the Vite tier. `uv` is installed into `/root/.local/bin` (`:53`, `:87`)
while the runtime user is `app` (`:122`, `:150`, `:176`) — the static cause of OPS-015(c).

### 3.3 Migration and startup ordering

`db` healthy (`pg_isready`, `compose.yml:34-39`) → `migrate` (`alembic upgrade head`, `:59`,
`restart: "no"` `:91`) → `app` **and** `rq-worker` gated on `service_completed_successfully`
(`:100-102`, `:197-201`) → `app` also waits on `redis: service_healthy` (`:109-110`, startup-ordering
only; the lease fails open per `:105-108`) → `nginx` waits on `app: service_healthy` (`:274-276`).
`Invoke-Up` (`Makefile.ps1:114-125`) does `rm -sf migrate` then `up -d --wait --wait-timeout 180`.
The advisory lock is `MIGRATION_ADVISORY_LOCK_KEY = 42` in `alembic/env.py:58`, taken/released at
`:116`/`:125`/`:132` — **not** in `starter._apply_migrations()` (`db/starter.py:352-357`).

### 3.4 Health checks and their consumers

| Service | Probe | Source | Interval/timeout/retries/start_period | Consumer |
|---|---|---|---|---|
| `db` | `pg_isready` | `compose.yml:35` | 5s/5s/5/10s | `migrate`, `app`, `rq-worker` |
| `redis` | `redis-cli ping` | `:178` | 5s/3s/3 | `app`, `rq-worker` |
| `app` | `curl -f /health` | `:158` **and** `Dockerfile:180-181` | 30s/10s/3/40s | `nginx` (`service_healthy`), `up --wait` |
| `rq-worker` | `python -c "from mkobi.rq_worker_wrapper import main; main()"` | `:251-255`, `override.yml:168-177` | 30s/10s/3/40s | nothing (`--no-deps` gate absent) |
| `nginx` | `wget --spider -q http://localhost/` | `:292` | 30s/10s/3 | nothing |
| `test-app` | disabled | `test.yml:156-157` | — | — |

`nginx.conf:43-46` proxies `/health` and `/health/detailed` unauthenticated. **`/health` executes only
`SELECT 1`** (`app.py:297-316`); `/health/detailed` reports `database`, `static_files`,
`stale_processing_reconciler` — **no `redis`, no `alembic_version`**.
The `rq-worker` probe reads the `rq:workers` registry and judges `last_heartbeat` against
`WORKER_LIVENESS_TTL_SECONDS = DEFAULT_WORKER_TTL + 60` (`rq_worker_wrapper.py:40,103-155,178-188`).
With `retries: 3 × interval: 30s` a wedged worker takes **~8 minutes** to flip `unhealthy`.

### 3.5 RQ worker and its supervision

`command: ["/app/.venv/bin/python", "-m", "mkobi.rq_worker_wrapper"]` (both tiers). Path:
`start_rq_worker()` (`:191-222`) → `check_redis_connection` (3 attempts, 2ⁿ backoff) → imports
`mkobi.workers.data_worker` for task registration → `rq.Queue(DEFAULT_QUEUE_NAME)` → `worker.work()`.
Producer: `core/task_queue.py:52-79`. Supervision: `restart: unless-stopped` (`compose.yml:244`),
`depends_on` on `redis` + `migrate`, and a healthcheck whose `timeout: 10s` exceeds
`check_worker_registered`'s unbounded `smembers`/`hget` round-trips. No `stop_grace_period`,
no `deploy.update_config`, no replica count — **a single worker instance, no scale path declared.**

### 3.6 Reconciler / lease sweepers

`core/reconciler_lease.py`: `LEASE_KEY = "mkobi:reconciler:stale_processing:lease"` (`:32`),
`DEFAULT_LEASE_TTL_SECONDS = 90` (`:37`), `acquire`/`renew_or_reelect`/`renew`/`release` (`:116`/`:142`/`:197`/`:224`).
`app.py:131-167` builds one lease per process, `ttl=min(90, interval//3)`, runs
`mark_orphaned_uploaded_logs_failed()` under the lease, then starts
`start_stale_processing_cleanup_task` (`workers/data_worker.py`). Teardown is **fail-isolated**
(`app.py:179-229`, commit `b646ef1`). Status is published on `/health/detailed`
(`app.py:360-376`). **Owner: phase 02 (process architecture) + phase 03 (concurrency).**
Live key present in `mkobi_redis_data` — a `redis_data` resident OPS-001 does not inventory.

### 3.7 Backup / restore

`Invoke-Backup` (`Makefile.ps1:279-290`) → `Invoke-Restore` (`:292-306`) →
`Invoke-PruneBackups` (`:308-320`, `-Filter '*.dump'`, 7-day cutoff, no scheduler).
`$BackupDir = 'backups'` (`:37`) is git-ignored (`.gitignore:254`).
`docker compose cp` is used in both directions, so the PowerShell binary-redirection hazard in
`.kilo/rules/commands.md` is **avoided today**; the rule becomes load-bearing if either line is
rewritten to a redirection. **No `rehearse-restore`, no globals artefact, no RPO/RTO anywhere.**
`postgres_data` is the only volume covered; `redis_data` (with a live `dump.rdb`) and `app_data`
are not.

### 3.8 Logging and its volume

`setup_logging` (`core/logging_config.py:68-187`): console handler (`:102-109`,
`ext://sys.stdout`) always; `RotatingFileHandler` (`:111-122`, 10 MB × 6) when `log_file` is truthy.
`LOGGING__LOG_FILE=/app/data/logs/app.log` on `app` (`compose.yml:129`) and `rq-worker` (`:224`);
`""` in dev (`override.yml:92`); absent on `migrate` (`:60-86`).
`uvicorn` and `uvicorn.access` are console-only (`:165-169`, `:175-179`); `uvicorn.error`, `mkobi*`
and `root` use both. Volume: `app_data` — shared with `uploads/` and `tmp_uploads/`.
**Seam with phase 06:** `config.py:186-191` explicitly names `LOGGING__LOG_FILE` as a `*_FILE`
variable that strips to `logging__log`, names no field, and is skipped with a warning — the secrets
mechanism and the log-volume question meet in one line.

### 3.9 Resource limits and disk budget

| Service | memory limit | cpus | reservation |
|---|---|---|---|
| `db` | 1G / 1.0 | | 512M (`compose.yml:41-47`) |
| `app` | 1G / 1.0 | | 512M (`:163-169`) — **runtime-confirmed `Memory=1073741824`** |
| `redis` | 256M / 0.5 | | 128M (`:182-188`) |
| `rq-worker` | 512M / 0.5 | | 256M (`:260-266`) — **runtime-confirmed `Memory=536870912`** |
| `nginx` | 128M | — | 64M (`:298-303`) |
| `migrate` | **none** | | (test: `test-migrate` 512M, `test-app` 1G) |

**No disk budget exists anywhere in the repository** — no `storage_opt`, no size limit, no quota, no
documented number. This is the hard input plan 06 `C06-4`/`C06-7` and plan 05 `C05-7` wait on.
Growth sources: `app_data/logs` (4 × 60 MB under `--workers 4`), `app_data/uploads` (retention
`stale_file_threshold_hours = 24`, `config.py:579`), `app_data/tmp_uploads`, `redis_data`,
`postgres_data`. Phase 11 owns measurement (PERF-001's 1,036.2 MB peak against the live 1 GiB
`app` limit = 101.2 %, corroborated here).

### 3.10 Secrets resolution incl. `_FILE`

Sources in `config.py`: YAML (`settings/app.yaml`) → environment with `__` nesting → Docker secrets
`*_FILE` (`config.py:147-201`, allowed-name derivation `:347`, diagnostics `:398`, docs `:824`).
A `*_FILE` naming a **secret-bearing** field is read (`:201`); one naming an **ordinary** field is
skipped with a warning (`:178-181`); one naming **no field** is skipped (`:186-191`). Precedence:
env > YAML > field default. `ENV` is a literal in the compose `environment:` map (`:63`, `:114`,
`:205`) so no env file can change the tier. **All five required secrets are commented out in
`docker/.env.production:10-14`, and `CORS_ORIGINS` is now commented out at `:33`** — the shipped
production file resolves nothing.

### 3.11 The nginx production profile

`compose.yml:272-303`; `read_only: true` with four tmpfs (`:285-290`); no `cap_drop`
**deliberately** — `docker.md:427-429` records that `nginx` uses `setuid` internally and
`no-new-privileges` would crash it. That key is therefore **never** correct for this service; OPS-014's
asymmetry is intentional here and wrong for `rq-worker`/`migrate`. It publishes `80:80`
(`:277-278`), so starting the profile has a host-visible effect — which is why nothing here started it.

### 3.12 Seam ownership map

| Seam | Files | Owner phase |
|---|---|---|
| `redis_data` backup, artefact volume, disk budget, alerts, Redis durability | `Makefile.ps1:279-320`, `compose.yml:175,308`, `deployment.md:355-356` | **phase 10** (06 `C06-4`, `C06-11`; 05 `C05-7`) |
| Sweep byte/count ceiling + alert side | `workers/data_worker.py`, `deployment.md` | phase 05 (lifetime) / **phase 10** (alert) |
| `task-queue-migration.md` substantive content | `docs/11-guides/task-queue-migration.md` | **phase 10** (05 `C05-9`) |
| `docker.md` queue section + `deployment.md` rq-worker entry | `docs/11-guides/docker.md:404,614,621`; `deployment.md:215` | **phase 10** (02 plan `:2896`) |
| Probe contract `DP-1` / `DP-2` | `app.py:297-379`, `tests/test_health.py:217-238`, `docs/05-health/health-api.md` | phase 07 code / **phase 10 co-signer** (07 `HO-3`) |
| Revocation-read guard (AUTH-008), logout ordering | `api/deps.py`, `api/routes/auth.py` | phase 04; phase 10 owns ordering only |
| `nginx.conf` `log_format` / `access_log` | `docker/nginx/nginx.conf:10-11` | phase 12 (04 `C04-5`) / **phase 10** (OPS-006) |
| Uncommitted deactivation write (TXN-001) | `db/repositories/user_repo.py`, `api/routes/admin.py` | phase 03 |
| RQ-vs-delete decision (TOPO-002) | `core/task_queue.py`, `compose.yml:191-266` | phase 01 (decision) / **phase 10** (docs) |
| `--workers 4` sizing, OOM restart | `Dockerfile:183`, `compose.yml:163-169` | phase 01 (model) / phase 11 (sizing) |
| Quality-gate entry points | `Makefile.ps1:221-249` | phase 09 |
| Reconciler / lease / in-process sweepers | `core/reconciler_lease.py`, `app.py:131-229` | phase 02 + 03 |

---

## 4. In-flight and already-landed work

### 4.1 Commits intersecting this phase (HEAD `cea2d06` → `ab76989`)

| Commit | Subject | Phase-10 touchpoint |
|---|---|---|
| `ab76989` | `fix(worker): give the aggregate rebuild a declared lock and a bounded wait` | **Landed during this audit.** `src/mkobi/db/advisory_lock.py` (new, 169 L), `workers/data_worker.py`, `config.py` (+6), `docs/06-backend/configuration.md` (+1). Adds `pg_advisory_xact_lock` for **dashboard rebuilds** — a *second* lock family beside the migration lock. Affects the reconciler/sweeper topology (3.6) and the `app_data` write profile (3.9). Does **not** touch any file this phase owns. |
| `9a77625` | `fix(rq-worker): correct the liveness diagnosis and threshold; pin the shared queue name` | **Rewrites the `rq-worker` healthcheck.** Introduces `rq_worker_wrapper.check_worker_registered` / `main` / `WORKER_LIVENESS_TTL_SECONDS`, the `DEFAULT_QUEUE_NAME` pin, and the `compose.yml:251-255` + `override.yml:168-177` probe. Direct input to `DP-1`. |
| `a92b546` | `fix(lease): re-elect the reconciler after a failed renewal instead of latching as holder` | `reconciler_lease.renew_or_reelect` (`:142-195`). Phase 02/03. Publishes into `/health/detailed`. |
| `b646ef1` | `fix(lifespan): make teardown fail-isolated so one failure cannot skip the rest` | `app.py:179-229`. **Constrains any OPS-011 terminal-exit remedy** (see OPS-011). |
| `2174895` / `cea2d06` | `fix(user): own the unit of work …` / test cleanup | `db/repositories/user_repo.py`, `services/user_service.py` — the TXN-001 amplifier OPS-001 cites. Phase 03/04. |
| `c4c0b14` | `docs(process-architecture): record the TOPO-001..TOPO-008 remediation` | The doc baseline OPS-015 (a) measured against. |
| `5b23240` | `docs(audit): add validated findings for all 16 audit phases` | The report set itself. |

### 4.2 Dirty files intersecting this phase

**None.** At the time of writing the working tree is clean of code modifications. The four files the
brief listed as dirty (`src/mkobi/config.py`, `src/mkobi/workers/data_worker.py`,
`tests/test_data_worker.py`, `docs/06-backend/configuration.md`) were committed by `ab76989` while
this audit was in flight. Untracked: the eight sibling plans, `.ai/plans/_code-context/`,
`.ai/tasks/B1-txn-001-*.yaml`, `.ai/tasks/B2-txn-005-*.yaml`, plus 34 pre-existing `.ai/` and
`frontend/coverage/` deletions inherited from the audit tooling teardown.

### 4.3 Plans that landed mid-audit

`.ai/plans/09-test-coverage-remediation-execution.md` is now present. It was absent at the start of
this audit; it is a **test-coverage** plan and files no phase-10 seam, but it is the owner of the
`Invoke-Check` gate-entry verdict that OPS-009 and OPS-004 both defer to.

---

## 5. Discrepancies and risks

### 5.1 Stale anchors (line numbers, in the report's favour or against)

| Report anchor | Actual at `ab76989` | Note |
|---|---|---|
| `docker-compose.yml:164`, `:278` (`redis_data`) | `:175`, `:308` | drift |
| `docker-compose.yml:180-237` (`rq-worker`) | `:191-266` | drift; new `deploy` block |
| `docker-compose.yml:146-151` (`app` healthcheck) | `:157-162` | drift |
| `docker-compose.yml:243-267` (`nginx`) | `:272-303` | drift |
| `docker-compose.yml:55-86` (`migrate`) | `:54-91` | drift |
| `docker-compose.yml:86` (`migrate restart: "no"`) | `:91` | drift |
| `docker-compose.override.yml:115-116` (dev healthcheck disabled) | **no `healthcheck:` key at all**; comment at `:120-122` | **claim refuted** (07 `HO-3` says the same; `9c49c20`) |
| `docker-compose.override.yml:149-150` (report's correction) and `:153-154` (corrected) | `:163-164` | correction itself stale |
| `docker-compose.override.yml:127` (bare `rqworker`) | `:132` (wrapper module) | refuted |
| `Dockerfile:166` (SPA `COPY --from`) | `:170` | drift |
| `Dockerfile:176-177` (HEALTHCHECK) | `:180-181` | drift |
| `Dockerfile:179` (`--workers 4`) | `:183` | drift |
| `Dockerfile:162` (`uv sync --frozen`) | `:166` | drift |
| `Dockerfile:172` (`USER app`, prod) | `:176` | drift |
| `app.py:248-267`, `:269-307` (health) | `:297-316`, `:318-379` | drift |
| `app.py:236-246` ("eight API routers") | `:285-295` (**eleven** routers) | drift + count wrong |
| `app.py:147-155` (lifespan re-raise) | `:170-178` | drift |
| `app.py:129-143` (in-process drain loop) | lease acquisition; **no drain loop exists** | **symbol gone** |
| `task_queue.py:159-192` (`default_queue`) | file is 79 lines; **symbol gone** | **symbol gone** |
| `task_queue.py:55-76` (`enqueue_with_worker`) | **symbol gone** | **symbol gone** |
| `rq-worker` healthcheck = `Redis(...).ping()` | registry probe (`compose.yml:251-255`) | refuted |
| `docker/.env.production:31,32,37,44` | `:36,37,42,49` (49 lines, `CORS_ORIGINS` now commented at `:33`) | drift + new gap |
| `Makefile.ps1` backup/restore/dispatch | **line-exact** | — |
| `logging_config.py:102-109`, `:111-122` | **line-exact** | — |
| `redis_client.py:46-52`, `main.py:52-55`, `app.py:39`, `app.py:217`→`:266` | **line-exact** (except the last) | — |

### 5.2 Refuted recommendations in the report

1. **OPS-004's dev-overlay disablement** — refuted. The dev `app` has no `healthcheck:` key and is
   `Up 11 hours (healthy)` at runtime. Do not carry this clause into the plan.
2. **OPS-002's premise** — refuted by the code having moved. `enqueue_job` is RQ-only; there is no
   in-process queue left to remove. VAL-10-001's "choose one" is a documentation question now.
3. **OPS-008's "every record … five times"** — overstated twice: four writers, and `uvicorn.access`
   is console-only.
4. **OPS-010's `pg_restore --exit-on-error`** — the report already corrects this; it changes *where*
   the tool stops, not whether it reports. The missing `$LASTEXITCODE` check is the whole defect.
5. **`deploy.resources.limits` "engine ignores declared limits"** — refuted again, here by direct
   `docker inspect` on both services.

### 5.3 Contested ownership

| Item | Contest | Ruling input |
|---|---|---|
| `nginx.conf:10-11` log directives | OPS-006 (phase 10) vs 04 `C04-5` (phase 12, "phase 10 on deployed composition") | 04 plan `:585` — phase 04 may request, not edit |
| `EXT-001` probe contract | 07 validator: co-owned not merged; 10 `VAL-10-002`: merge, phase 10 keeps consumers | consumers already landed; only co-signature remains |
| `docker.md:614` rq-worker row | 10 owns the queue section; 07 `HO-3` names the report's dev claim as refuted | both point at phase 10 |
| Artefact volume / disk budget | 06 `FAB-5` (ceiling) vs 10 `C06-4` (budget, compose, backup, alerts) | 10 owns the budget; 06 blocks on it |
| `tests/test_config.py::TestRqWorkerComposeWiring` | 01's TOPO-002 decision vs the test's hard `rq-worker`-must-exist assertion | **unresolved — see 6.1** |

### 5.4 Tests that will break under plausible edits

| Test | Breaks if | Owner |
|---|---|---|
| `tests/test_health.py:217-238` `test_health_still_healthy_when_redis_down` | any `redis` component on `/health`, or any 503-on-Redis-failure | 07 `DP-2`; phase 10 co-signs `DP-1` |
| `tests/test_config.py:1263-1270` `…is_not_ping_or_disabled_in_both_tiers` | the `rq-worker` healthcheck is replaced with anything containing `Redis(` or `redis-cli` | 01 |
| `tests/test_config.py:1256-1261` `…is_wrapper_module_in_both_tiers` | the `rq-worker` **service** is deleted (assertion at `:1248` fires first) | 01 |
| `tests/test_health.py:110-126` `…returns_components` | safe against an added `redis` key (presence, not exact set) | — |
| `tests/test_config.py` `TestRqWorkerComposeWiring` generally | **any** edit to the `rq-worker` block in either compose file that trips a substring | 01/10 |

### 5.5 Operational risks and the safe order

| # | Risk | Safe order |
|---|---|---|
| 1 | **A change here can take the stack down.** `compose.yml` is one file; every service is in it; `up --wait` returns 180 s after a bad edit. | Edit compose → `docker compose --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config` (resolves + interpolates) → `ps` → **then** `up`. Never `up` first. |
| 2 | **Ordering of the RQ switch is already complete on the code side but not the deployment side.** `test_config.py` pins the command; the docs still name the retired one. | Fix docs **after** the code is confirmed landed (it is), and in the same commit as any compose change, or the next agent reads a doc that matches neither. |
| 3 | **`restore` is the only destructive target in the repo** and it never reports failure. | Any change to `Invoke-Restore` must be rehearsed against a scratch database first; assertions before mutation (the report's ordering, upheld). |
| 4 | **`Invoke-Nuke` is daemon-global** (`builder prune -af` + `image prune -af`, `Makefile.ps1:381-382`). | Never invoke to test a build change; it destroys the layers OPS-003 and OPS-016 depend on, on a daemon other agents share. |
| 5 | **Adding a `redis` check to `/health` turns a Redis blip into an API outage**, because `nginx` now gates on `app: service_healthy` (`compose.yml:276`) and `up --wait` gates on it. | `DP-1` must be decided *before* any `app.py` health edit, and the `stale_processing_reconciler` component is the precedent for "report without failing". |
| 6 | **A terminal exit for OPS-011 trades a fast loop for Docker's backoff.** | Verify against a slow-but-succeeding `migrate`; place the exit so `app.py:179-229` teardown still runs. |
| 7 | **`app_data` is shared by `app` and `rq-worker` read-write**; `read_only: true` on `rq-worker` (OPS-014) needs tmpfs like `nginx`. | Do not flip `rq-worker` to `read_only` without the tmpfs mounts in the same commit. |
| 8 | **Runtime facts here are from a stale dev stack** (3–25 h old, `app` built pre-`ab76989`). | Re-run `ps`/`inspect` after any `up` before citing a runtime fact. |

---

## 6. Decision points for the Planner

Genuine technical uncertainty. Alternatives stated; **the chooser is named; none is picked here.**

| # | Question | Alternatives | Chooser |
|---|---|---|---|
| **6.1** | **`TestRqWorkerComposeWiring` turns TOPO-002's "route through RQ **or** delete the service" into a test contract.** `test_worker_command_is_wrapper_module_in_both_tiers` asserts the `rq-worker` key exists in both files (`:1248`) and contains the wrapper module. Direction B (delete the service) cannot land without editing that test — which phase 01 owns. | (a) phase 10 records the constraint and phase 01 amends the test under Direction B; (b) phase 10 treats the test as a specification of the decision and asks phase 01 to confirm Direction A before phase 10 touches `deployment.md:215`; (c) phase 10 edits nothing here and files the constraint as a note. | **Phase 01** (owns TOPO-002) with **Coordinator**; phase 10 must not decide. |
| **6.2** | **Does the `redis` health component go on `/health` (which `nginx` and `up --wait` gate on) or only on `/health/detailed`?** With `nginx → service_healthy` now live, option (b) makes a Redis blip an API outage. | (a) `/health` stays DB-only, Redis only on `/health/detailed`, documented consumer contract changed; (b) Redis on `/health` + 503, accepting the outage amplification; (c) new `/health/ready` endpoint. | **Tech Lead**, with **phase 10 as co-signer** (07 `HO-3`, `DP-1`). |
| **6.3** | **Fate of `test_health.py:217-238`.** It asserts `/health` → 200 with an exact dict while every Redis call raises. | (a) keep the test, keep `/health` DB-only, put Redis on `/health/detailed`; (b) delete/rewrite the test to allow 503; (c) parametrise it. | **Tech Lead** (07 `DP-2`), phase 10 co-signs. |
| **6.4** | **`WORKER_LIVENESS_TTL_SECONDS = DEFAULT_WORKER_TTL + 60` (~480 s) against `retries: 3 × interval: 30s`** gives ~8 min to `unhealthy`. Is that the detection window an operator wants, and does it need a `stop_grace_period` or a `healthcheck` retune? | (a) keep the proof-based threshold, retune `retries`/`interval`; (b) keep both, document the window as an SLO; (c) add a second, faster probe. | **Tech Lead** (07 `DP-1` co-signature) + **phase 10** (it owns the compose `healthcheck` block). |
| **6.5** | **Redis producer/consumer credential divergence.** `task_queue.get_rq_queue()` passes `redis.password`; `rq_worker_wrapper._build_redis_url()` does not. Not filed by the report. | (a) add the password (or a `url` property) to the wrapper; (b) centralise connection construction in one module both import; (c) declare Redis unauthenticated in production and document it. | **Coordinator** — this is a new seam in OPS-001/OPS-012's zone that no phase has filed. |
| **6.6** | **Enqueue-time failure mode after the RQ switch.** `enqueue_job` now raises `AppException(FILE_PROCESSING_ERROR)` on a Redis outage where the retired in-process queue absorbed it — a new user-visible 500 on upload. | (a) accept it as fail-loud and document; (b) add a bounded retry at the call site; (c) keep a fallback (explicitly rejected by 07's VAL-005 and 10's VAL-10-001). | **Coordinator** with phase 01 (the switch owner) and phase 05 (the upload path). |
| **6.7** | **The disk budget number** that plan 06 `C06-4` and 05 `C05-7` are hard-blocked on. No number ships today; it needs phase 11's measurement and 06's growth factor. | (a) per-directory pre-accept size check + `FILE_TOO_LARGE`; (b) dedicated log volume with its own budget; (c) both. | **Coordinator** (topology + operations) — explicitly *not* phase 10 to invent. |
| **6.8** | **Artefact volume layout: does `rq-worker` keep a read-write mount of the artefact area?** This decides whether the budget has a stable denominator and whether `app_data` splits. | (a) keep `app_data` read-write; (b) split the artefact area onto its own volume shared by `app` + `rq-worker`; (c) move removal into the API process. | **Coordinator** — interacts with 6.7 and with 06's `D-06-K`. |
| **6.9** | **`deployment.md:316` / `SPEC.md:141` name the wrong lock holder** (`starter._apply_migrations()` vs `alembic/env.py:58,116`). Is this a doc correction only, or does `alembic/env.py:116`'s f-string-in-SQL (`text(f"SELECT pg_advisory_lock({...})")`, an AGENTS.md prohibition) also need ruling? | (a) doc-only fix in phase 10; (b) doc fix + an AGENTS.md-conformance note to phase 03/08; (c) escalate as a separate finding. | **Coordinator**; phase 10 owns (a) only. |
| **6.10** | **`Invoke-Up` also reports failure without a non-zero exit** (`Makefile.ps1:114-125`, same defect shape as OPS-005 but not filed). In scope for OPS-005, or a new finding? | (a) fold into OPS-005's `backup`/`restore` exit-code fix; (b) file separately. | **Coordinator** — affects whether the plan's OPS-005 block touches `Invoke-Up`. |

---

## 7. Coverage ledger

| Finding | Verdict | Primary evidence anchor(s) |
|---|---|---|
| OPS-001 | substantiated (mechanism refined) | `compose.yml:175,308`; `Makefile.ps1:279-290,308-320`; live `/data/dump.rdb`; live `mkobi:reconciler:stale_processing:lease`; `deployment.md:356` |
| OPS-002 | already-fixed (code) / docs stale | `core/task_queue.py:26,29-49,52-79`; `compose.yml:196`; `override.yml:132`; `deployment.md:215`; `docker.md:614,621`; `tests/test_config.py:1215-1270` |
| OPS-003 | substantiated (3 carriers) | `compose.yml:281`; `Dockerfile:170`; `app.py:391-460`; `nginx.conf:49-53`; `git check-ignore` → `frontend/.gitignore:11` |
| OPS-004 | merged→EXT-001; consumer half already-fixed | `app.py:297-316,318-379,360-376`; `compose.yml:274-276`; `override.yml:120-122`; `Makefile.ps1:116`; runtime `Up 11 hours (healthy)`; `tests/test_health.py:217-238` |
| OPS-005 | substantiated (+`Invoke-Up` sibling) | `Makefile.ps1:279-290,292-306,441,114-125`; `Show-Help:90-93` |
| OPS-006 | substantiated | `nginx.conf:10-11`; `compose.yml:285-290,280`; runtime `LogDriver=json-file`; `logging_config.py:102-109` |
| OPS-007 | substantiated (anchors drifted) | `app.py:285-295,297,318`; no `.github`; `scan-images.ps1` unwired |
| OPS-008 | substantiated (imprecise; dev-unobservable) | `app.py:44-48`; `logging_config.py:111-122,165-169,175-179`; `Dockerfile:183`; `compose.yml:129,224`; `override.yml:92`; runtime empty `/app/data/logs` |
| OPS-009 | substantiated | `Makefile.ps1:222,226,230,241-249,260`; `compose.yml:111-144`; `override.yml:105-106` |
| OPS-010 | substantiated | `Makefile.ps1:37,285,304,308-320`; `compose.yml:33,91,118,208`; `01-create-app-role.sh:23-42` |
| OPS-011 | substantiated (+teardown interaction) | `app.py:170-178,179-229`; `Dockerfile:183`; `compose.yml:101-102`; `b646ef1` |
| OPS-012 | substantiated (+2 un-filed sites) | `redis_client.py:46-52`; `task_queue.py:43-48`; `rq_worker_wrapper.py:43-50,71,130`; `compose.yml:142,236`; `.env.production:49` |
| OPS-013 | substantiated | `nginx.conf:17-18,66-67`; `compose.yml:143,237,272-303,280` |
| OPS-014 | substantiated (runtime-proven) | `compose.yml:150,152-156,191-266,54-91`; `docker inspect`: `app CapDrop=[ALL]`/`rq-worker CapDrop=<no value>`; `override.yml:163-164`; `docker.md:427-429` |
| OPS-015 | drifted (1 fixed, 2 hold, 2 new) | `deployment.md:186,207,212,215,283,316,320,380,401,404,419-428`; `alembic/env.py:58,116`; `starter.py:352-357`; `SPEC.md:141`; `docker.md:56-58,66-67,140,145,286,404`; runtime `uv` exit 127 |
| OPS-016 | substantiated (one anchor drift) | `Dockerfile:10,18,28,31,51-52,64,66,85-86,107,136,166`; `compose.yml:17,94-99,173,192-195,273`; `Makefile.ps1:139-142,377-383` |
| VAL-10-001 | moot | `task_queue.py` 79 L; `app.py:129-143` no drain loop |
| VAL-10-002 | upheld, half discharged | `compose.yml:274-276`; `override.yml:120-122`; `Makefile.ps1:116` |
| VAL-10-003 | substantiated, dev-unverifiable | `main.py:52-55`; `app.py:266`; `override.yml:92`; runtime empty log dir |
| VAL-10-004 | substantiated (13 errors, not 4) | live `docker compose ps` exit 1, 13 interpolations; `.env.production:10-14`, 49 L |
| VAL-10-005 | substantiated, widened | `deployment.md` (no `--env-file`); `security-checklist.md`; `.env.production:33`; `compose.yml:138,222`; `app.py:250-253` |
| VAL-10-006 | substantiated | `git check-ignore -v`; `.gitignore:13`; `frontend/.gitignore:11` |

**Symbols the report names that do not exist today** (all in OPS-002/TOPO-002's anchor set):
`default_queue` (`task_queue.py:159`), `enqueue_with_worker` (`task_queue.py:55-76`), the
`asyncio.Queue` drained by `app.py:129-143`, the in-process drain loop itself, the bare
`/app/.venv/bin/rqworker` command (`compose.yml:185`, `override.yml:127`), the
`Redis(...).ping()` worker healthcheck (`compose.yml:221-230`), and the dev-tier
healthcheck-disable (`override.yml:115-116`). `enqueue_with_worker` remains uncalled rather than
rewritten — it is simply gone.
