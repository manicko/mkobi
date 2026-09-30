---
id: mkobi-docker-taskrunner-remediation
domain: plans
tags:
  - docker
  - compose
  - tooling
  - devops
  - task-runner
related:
  - docker-guide
  - deployment
  - run-guide
---

# mkobi Docker + Task-Runner Remediation Plan

## 1. Summary

`Makefile.ps1` at the repo root was copied from an unrelated Django project (`mko-bazuna`)
and does not work for this repo: wrong compose file names, wrong service names, Django
commands (`manage.py makemigrations`), a non-existent `web` service, `locust`, `scripts/`,
`.env.dev` parsing, and `basedpyright` where this project uses `mypy`.

Underneath it, the Compose files themselves are broken in five independent ways: all three
resolve to project name `docker`, the dev profile gate silently drops `rq-worker`,
`CORS_ORIGINS:?` blocks any minimal env file, the test compose leaks shell variables into
the test stack, and backend hot reload never fires on Windows.

End state: five Compose fixes (Part A), a greenfield `Makefile.ps1` with ~30 working
targets (Part B), and removal of two stray files from version control (Part C). The work is
split into 8 tasks, each independently verifiable with `docker compose config`.

> **Status: all 8 tasks implemented and verified.** Three further items were completed
> afterwards and are documented in **§7.6**: host ports were made collision-proof so the
> stacks run in parallel with other projects (`5433`→`5434`, `8000`→`8010`, both now
> env-overridable); the missing `REDIS__HOST` in the production compose was fixed; and the six
> legacy `docker_*` volumes were deleted. Section 3.3 is complete and must not be re-run.

---

## 2. Why This Work Is Required

Every claim below was verified on this machine. Where a claim is *not* verified, it is
marked **[UNVERIFIED — confirm in Task N]**.

> **All `[UNVERIFIED]` markers are now resolved** (2026-09-30) — see §7.6.5. The marker
> convention is retained below as the standard the plan was written to.

### 2.1 Compose project name collides globally

**Defect.** `docker/docker-compose.yml` and `docker/docker-compose.test.yml` both lack a
top-level `name:` key, and `docker/docker-compose.override.yml` has none either. Without it,
Compose derives the project name from the working directory basename — `docker` (the parent
folder holding the compose file), which is the same for all three.

**Evidence.**
```
docker compose -f docker/docker-compose.test.yml config | Select-String '^name:'
  name: docker
```
Volumes created by the current (broken) stack are therefore labelled
`com.docker.compose.project=docker`: `docker_app_data`, `docker_frontend_vite_cache`,
`docker_postgres_data`, `docker_redis_data`, `docker_test_postgres_data`,
`docker_test_redis_data` (all six confirmed present).

**Failure prevented.** Any other Compose project whose base directory is also named
`docker` shares these volumes and networks. `docker compose down -v` in one deletes the
other's data. `-p mkobi` / `-p mkobi-test` make the isolation explicit and leave a
per-branch escape hatch.

### 2.2 The dev `rq-worker` never starts

**Defect.** `rq-worker` carries `profiles: [production]` in the base compose
(`docker/docker-compose.yml`, the `profiles:` key under `rq-worker`). The dev override tries
to undo this with `profiles: []` under `rq-worker`. Compose folds an empty list into the
union, so `[]` does not remove `production` — the service stays gated.

**Evidence.** The resolved dev service list omits the worker entirely:
```
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config --services
  redis
  db
  migrate
  app
  frontend            <-- rq-worker is absent
```
`src/mkobi/workers/` exists and `rq>=2.8.0` is a dependency, so the worker is required for
upload processing.

**Failure prevented.** Uploads are queued to Redis and never consumed. `dev up` reports
success while the queue silently grows.

### 2.3 `CORS_ORIGINS:?` fires before the dev override can supply a default

**Defect.** The base compose uses `CORS_ORIGINS: ${CORS_ORIGINS:?...}` on `app`
(`docker/docker-compose.yml`, `app.environment`). The dev override supplies
`CORS_ORIGINS: ${CORS_ORIGINS:-["http://localhost:3000"]}`. Compose interpolates each file
**before** merging, so the base's `:?` is evaluated first and aborts the whole command when
the variable is unset — the override default never gets a chance.

**Failure prevented.** A developer who copies `docker/.env.development` and fills in only
the documented variables cannot start the dev stack at all; the failure looks like a compose
bug rather than a missing variable.

**Why a default is safe.** Production safety is enforced in code, twice:
- `src/mkobi/config.py` — `Settings.CORS_ORIGINS_PLACEHOLDERS` = `{"*", "http://localhost:3000",
  "http://localhost:5173", "https://example.com", "https://your-domain.com"}` and
  `validate_cors_origins_not_placeholder` raises when `ENV == production`.
- `src/mkobi/app.py` `create_app()` — rejects an empty `cors_origins` and rejects `"*"` in
  production.

So a placeholder default **fails closed at application startup** in production rather than
silently serving a permissive policy. The `:?` is redundant defence-in-depth.

### 2.4 The test stack is not hermetic

**Defect.** `docker/docker-compose.test.yml` interpolates `${DATABASE__PASSWORD:-test_password}`,
`${MKOBI_APP_PASSWORD:-test_app_password}`, `${JWT__SECRET_KEY:-...}`, `${ADMIN_USERNAME:-...}`,
`${ADMIN_PASSWORD:-...}` across `test-db`, `test-migrate` and `test-app`.

**Evidence.** Compose precedence is: shell process environment > `--env-file` > the
compose file's `name:`/`x-` defaults. Because process env outranks `--env-file`, exporting
`DATABASE__PASSWORD` in the shell makes `config` emit the exported value — `--env-file`
cannot defend against it. Verified during the audit pass.

**Failure prevented.** The test DB password silently becomes whatever the developer's shell
happens to hold, so `tests/conftest.py` (which hardcodes `test_password` /
`test_app_password` via `os.environ.setdefault`) authenticates with the wrong credentials
and the whole suite fails with a confusing connection error. A `docker/.env.test` would give
false comfort — it cannot outrank the process environment.

The test database is a disposable local artifact with documented fixed credentials
(`test_password` / `test_app_password`, already stated in the file's own header comment at
lines 12–16). Hard-coded literals are correct here.

### 2.5 Backend hot reload never fires on Windows

**Defect.** `docker/docker-compose.override.yml` sets `CHOKIDAR_USEPOLLING: "true"` and
`WATCHPACK_POLLING: "true"` on the **`frontend`** service only. Both are Node/chokidar and
webpack variables; the backend is `uvicorn --reload`. Docker Desktop on Windows delivers bind
mounts over gRPC-FUSE, which emits no inotify events, so uvicorn's `StatReloadWatcher`
never sees a change.

**Failure prevented.** `dev up` appears healthy, the developer edits `src/mkobi/...`, nothing
happens, and the change is lost on restart.

**Fix.** `WATCHFILES_FORCE_POLLING: "true"` on the dev `app` service (plus an optional
`WATCHFILES_POLL_DELAY_MS`). The `frontend` polling vars are correct where they are — they
must stay, and they must **not** be moved.

### 2.6 REJECTED: `--project-directory .` — DO NOT REINTRODUCE

Research recommended `docker compose --project-directory . ...` so the root `.env` would be
auto-found. **This was tested on this machine and refuted:**

```
docker compose --project-directory . -f docker/docker-compose.test.yml config
```

`--project-directory` relocates the *base path* used to resolve relative paths in the
compose file. Every service in this repo uses `build: { context: .. }`. Under
`--project-directory .`, `..` resolves to the **parent of the repo** (`C:\py_dev`), not
`C:\py_dev\mkobi`. The build context would then be the entire parent directory.

**Rule for this repo:** always pass explicit `--env-file .env` for the dev pair, and pass no
`--env-file` for the test compose. Never pass `--project-directory`. This is recorded here
so the next reader does not "improve" the script by adding it.

### 2.7 A one-shot `migrate` service is never re-run

`migrate` is `restart: "no"` and gates `app` and `rq-worker` via
`condition: service_completed_successfully`. Compose does not re-create an already-exited
one-shot container whose definition has not changed. A new revision added under
`alembic/versions/` (there are currently 9 revisions) is therefore **never applied** until
someone manually removes the stopped container.

**Failure prevented.** `.\Makefile.ps1 up` succeeds, `alembic current` reports a revision
behind `head`, and every query fails on a missing column. This is a task-runner-only fix:
`docker compose ... rm -sf migrate` immediately before every `up` (and `rm -sf test-migrate`
for the test stack).

### 2.8 `docker compose cp` is the only binary-safe backup path

The old `Invoke-Backup` ran `docker compose exec -T db pg_dump ... > $backupFile`. PowerShell
redirection of native-command stdout corrupts binary output on Windows PowerShell 5.1 and on
PowerShell 7.0–7.3; adding `2>&1` breaks it on every version. The old `Invoke-Restore` was
worse: it passed a **host** path (`$BackupFile`) into `pg_restore` *inside* the container,
where that path does not exist.

**Fix.** Dump/restore inside the container to `/tmp`, move the file with `docker compose cp`.
Syntax verified against Compose v5.5.1:
```
docker compose cp [OPTIONS] SERVICE:SRC_PATH DEST_PATH
docker compose cp [OPTIONS] SRC_PATH|- SERVICE:DEST_PATH
```

---

## 3. Prerequisites & Migration Notes

### 3.1 Current live state (verified 2026-09-30, Compose v5.5.1)

- **No `mkobi` containers are running.** Every container on this machine belongs to another
  project: `mko-bazuna-dev-*`, `mko-bazuna-test-*`, plus `qdrant` and an orphaned `b5-pgb2`.
- Six orphaned volumes carry `com.docker.compose.project=docker`:
  `docker_app_data`, `docker_frontend_vite_cache`, `docker_postgres_data`, `docker_redis_data`,
  `docker_test_postgres_data`, `docker_test_redis_data`.
- `Makefile.ps1` is **untracked** in git (`git status` reports `?? Makefile.ps1`). The rewrite
  replaces a file that was never committed, so no `git rm` is needed.
- The working tree already contains ~19 pre-existing deletions under `.ai/` (audit templates,
  builders, plans, structure maps) plus many modified/untracked `.kilo/` files. **These are
  unrelated to this work** — see the warning in Task 8.

### 3.2 What adding `name:` costs you

A Compose project name is baked into container names, network names, and volume names.
Changing it from `docker` to `mkobi` / `mkobi-test` means the six `docker_*` volumes become
orphans that the new project will not see. The new stack starts with **empty** databases.

### 3.3 One-time cleanup sequence — THIS DELETES LOCAL DATABASE DATA

> **STATUS: COMPLETED (2026-09-30).** All six `docker_*` volumes were removed — see §7.6.3.
> This destroyed the local `bidb` and `bidb_test` databases, with explicit user approval.
> **Do not re-run this sequence.** It is retained below as a record of what was done and why.

> **WARNING.** Step 2 permanently destroyed the development database `bidb` (dashboards,
> users, `aggregated_data`) and the test database `bidb_test`.

Run from `C:\py_dev\mkobi` in PowerShell 7. Step 1 is safe and idempotent (it is currently a
no-op); step 2 is the destructive one.

```powershell
# --- Step 0 (ONLY IF the dev data still matters) — back it up first, binary-safely ---
# The stack is down, so bring up just `db` under the OLD project name, dump inside the
# container, and copy the file out with `docker compose cp` (never `>` redirection).
docker compose -p docker --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d db
New-Item -ItemType Directory -Force -Path .\backups | Out-Null
docker compose -p docker --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml exec -T db pg_dump -U postgres -d bidb -F c -f /tmp/precleanup.dump
docker compose -p docker --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml cp db:/tmp/precleanup.dump ./backups/precleanup.dump
docker compose -p docker --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml exec -T db rm -f /tmp/precleanup.dump
docker compose -p docker --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml down

# --- Step 1 — remove any container still attached to the old 'docker' project ---
docker compose -p docker --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml down --remove-orphans
docker compose -p docker -f docker/docker-compose.test.yml down --remove-orphans

# --- Step 2 — DESTRUCTIVE: remove the six orphaned volumes ---
docker volume rm docker_app_data docker_frontend_vite_cache docker_postgres_data docker_redis_data docker_test_postgres_data docker_test_redis_data

# --- Step 3 — confirm the old project owns nothing ---
docker volume ls --filter label=com.docker.compose.project=docker   # must print only "VOLUME NAME"
```

`docker volume rm` fails loudly with `volume is in use - [name]` if Step 1 was skipped or
incomplete. That failure is a safety feature — resolve it, do not force it.

`-p docker` on the command line overrides any `name:` key, so Steps 1–2 work both **before**
and **after** Task 1 lands. The sequence is therefore order-independent with respect to Task 1.

---

## 4. Task List

Tasks are ordered by dependency. All compose edits are independent of each other; only the
task-runner tasks depend on them.

---

### Task 1 — Compose project-name isolation

**Files touched**
- `docker/docker-compose.yml` — add 2 lines at the top
- `docker/docker-compose.test.yml` — add 2 lines at the top; delete 4 `container_name:` keys
- `docker/docker-compose.override.yml` — **no change** (deliberately)

**Change**

In `docker/docker-compose.yml`, insert before the `services:` key:

```yaml
name: mkobi
```

In `docker/docker-compose.test.yml`, insert before the `services:` key:

```yaml
name: mkobi-test
```

Delete these four keys from `docker/docker-compose.test.yml`:
- `container_name: test-db` (under `test-db`)
- `container_name: test-redis` (under `test-redis`)
- `container_name: test-migrate` (under `test-migrate`)
- `container_name: test-app` (under `test-app`)

Leave `docker/docker-compose.override.yml` without a `name:` key. With multiple `-f` files the
last `name:` wins, and dev and production are deliberately the same project — the override
must not fork it.

**Why remove `container_name:`** — fixed container names are daemon-global, they block a
second concurrent stack (e.g. dev on this machine and a CI/WSL stack elsewhere), and
`docker compose run` discards `container_name` silently anyway, so it buys nothing for
one-shot targets.

**Acceptance criteria**
1. `docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String '^name:'` prints `name: mkobi`.
2. `docker compose -p mkobi-test -f docker/docker-compose.test.yml config | Select-String '^name:'` prints `name: mkobi-test`.
3. With **no** `-p` flag: `docker compose -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String '^name:'` prints `name: mkobi` (inherited from the base file).
4. With **no** `-p` flag: `docker compose -f docker/docker-compose.test.yml config | Select-String '^name:'` prints `name: mkobi-test`.
5. `Select-String 'container_name'` over `docker/docker-compose.test.yml` returns nothing.
6. The resolved test service list still contains exactly `test-db`, `test-migrate`, `test-app`, `test-redis`.

**Verification command**
```powershell
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config --services
docker compose -p mkobi-test -f docker/docker-compose.test.yml config | Select-String -Pattern '^name:|container_name'
```

---

### Task 2 — Un-gate `rq-worker` in dev

**Files touched**
- `docker/docker-compose.yml` — delete the `profiles:` block under `rq-worker`
- `docker/docker-compose.override.yml` — delete the `profiles: []` line under `rq-worker`

**Change**

Delete from `docker/docker-compose.yml`, under `rq-worker` (after its `healthcheck:` block):

```yaml
    profiles:
      - production
```

Delete from `docker/docker-compose.override.yml`, under `rq-worker`:

```yaml
    profiles: []
```

Leave `nginx`'s `profiles: [production]` untouched — nginx is genuinely production-only.

**Acceptance criteria**
1. `docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config --services` contains `rq-worker`.
2. That same command contains all of `db`, `migrate`, `app`, `redis`, `rq-worker`, `frontend` — six services, and **no** `nginx`.
3. `docker compose -f docker/docker-compose.yml config --services` **without** the override still omits `rq-worker` and `nginx` (both remain production-gated at the base level for nginx only — see criterion 4).
4. `docker compose -f docker/docker-compose.yml --profile production config --services` contains `nginx` and `rq-worker`.
5. The resolved dev `rq-worker` still uses the `dev`-relevant override values: `ENV: development`, `LOGGING__LEVEL: DEBUG`, and the command `/app/.venv/bin/rqworker --url redis://redis:6379/0`.

**Verification command**
```powershell
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config --services
docker compose -f docker/docker-compose.yml --profile production config --services
```

> **[RESOLVED — verified 2026-09-30]** Criterion 3 needed the adjustment described above.
> Confirmed exactly: base-only `config --services` returns `db, migrate, app, redis, rq-worker`,
> and `--profile production` adds exactly `nginx`. `nginx` is the only remaining profile-gated
> service.

---

### Task 3 — Safe `CORS_ORIGINS` default in the base compose

**Files touched**
- `docker/docker-compose.yml` — one line, under `services.app.environment`

**Change**

Replace:

```yaml
      CORS_ORIGINS: ${CORS_ORIGINS:?CORS_ORIGINS is required in production}
```

with:

```yaml
      # Default is a known placeholder origin: src/mkobi/config.py rejects it when
      # ENV=production, so a missing value fails closed at app startup instead of
      # silently serving a permissive policy.
      CORS_ORIGINS: ${CORS_ORIGINS:-["http://localhost:5173"]}
```

`http://localhost:5173` is a member of `Settings.CORS_ORIGINS_PLACEHOLDERS`, so
`validate_cors_origins_not_placeholder` (`src/mkobi/config.py`) raises a `ValueError` under
`ENV=production`. Do not use `*`, `https://example.com`, or any non-placeholder value — those
are not all in the placeholder set, and a non-placeholder default would let a misconfigured
production deploy start.

**Acceptance criteria**
1. `docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config` succeeds and resolves `CORS_ORIGINS` to the value from the root `.env` (`["http://localhost:3000", "http://localhost:5173"]`).
2. A minimal env file containing only `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD`, `JWT__SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` no longer aborts interpolation. Verify with:
   ```powershell
   'DATABASE__PASSWORD=x','MKOBI_APP_PASSWORD=x','JWT__SECRET_KEY=x','ADMIN_USERNAME=a@b.co','ADMIN_PASSWORD=x' |
     Set-Content -Path "$env:TEMP\mkobi-min.env"
   docker compose --env-file "$env:TEMP\mkobi-min.env" -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String CORS_ORIGINS
   ```
   Expected: `CORS_ORIGINS: ["http://localhost:5173"]` and exit code 0.
3. `Select-String ':?\}' ` over the `CORS_ORIGINS` line returns nothing.

**Verification command**
Same as acceptance criterion 2.

---

### Task 4 — Hermetic test compose

**Files touched**
- `docker/docker-compose.test.yml` — 11 replacements across `test-db`, `test-migrate`, `test-app`

**Change**

Replace every `${...}` interpolation with a hard-coded literal:

| Service | Key | New value |
|---|---|---|
| `test-db` | `POSTGRES_PASSWORD` | `test_password` |
| `test-db` | `MKOBI_APP_PASSWORD` | `test_app_password` |
| `test-migrate` | `DATABASE__PASSWORD` | `test_password` |
| `test-migrate` | `DATABASE__ADMIN_PASSWORD` | `test_password` |
| `test-migrate` | `JWT__SECRET_KEY` | `test_jwt_secret_key_for_integration_tests_32_chars` |
| `test-migrate` | `ADMIN_USERNAME` | `test-admin@example.com` |
| `test-migrate` | `ADMIN_PASSWORD` | `test-password-for-integration-tests` |
| `test-app` | `DATABASE__PASSWORD` | `test_app_password` |
| `test-app` | `DATABASE__ADMIN_PASSWORD` | `test_password` |
| `test-app` | `JWT__SECRET_KEY` | `test_jwt_secret_key_for_integration_tests_32_chars` |
| `test-app` | `ADMIN_USERNAME` | `test-admin@example.com` |
| `test-app` | `ADMIN_PASSWORD` | `test-password-for-integration-tests` |

The two service-specific passwords differ on purpose: `test-app` connects as role `mkobi_app`
(→ `test_app_password`), `test-migrate` connects as `postgres` (→ `test_password`). Do not
"unify" them.

The existing header comment block already documents these fixed credentials (lines 12–16) —
update it only if it references env-file behaviour that is now gone.

**Acceptance criteria**
1. `Select-String '\$\{' docker/docker-compose.test.yml` returns nothing — no interpolation remains anywhere in the file.
2. Leaked-value test — with the variable exported in the shell, the resolved value is still the literal:
   ```powershell
   $env:DATABASE__PASSWORD = 'LEAKED_SHOULD_NOT_APPEAR'
   $env:MKOBI_APP_PASSWORD = 'LEAKED_SHOULD_NOT_APPEAR'
   docker compose -p mkobi-test -f docker/docker-compose.test.yml config | Select-String 'LEAKED_SHOULD_NOT_APPEAR'
   Remove-Item env:DATABASE__PASSWORD, env:MKOBI_APP_PASSWORD
   ```
   Expected: **no matches**, exit code 0.
3. `docker compose -p mkobi-test -f docker/docker-compose.test.yml config` contains `POSTGRES_PASSWORD: test_password` and `MKOBI_APP_PASSWORD: test_app_password`.
4. `test-db` still mounts `./init-scripts:/docker-entrypoint-initdb.d:ro`, so the `mkobi_app` role is created on first volume initialisation — required by `tests/conftest.py`, which authenticates as `mkobi_app`.

**Verification command**
Acceptance criteria 2 and 3 above.

---

### Task 5 — Backend hot reload on Windows

**Files touched**
- `docker/docker-compose.override.yml` — one line added under `services.app.environment`

**Change**

Add to the dev `app` service environment block (after `CORS_ORIGINS`):

```yaml
      # Docker Desktop's gRPC-FUSE bind mounts deliver no inotify events, so
      # uvicorn --reload never fires on Windows. watchfiles polling is required.
      WATCHFILES_FORCE_POLLING: "true"
      WATCHFILES_POLL_DELAY_MS: "400"
```

`watchfiles>=1.0.0` is already in the `dev` dependency group and baked into the `dev` build
target by `uv sync --frozen`, so no dependency change is needed.

Do **not** remove `CHOKIDAR_USEPOLLING` / `WATCHPACK_POLLING` from the `frontend` service —
those are correct where they are.

**Acceptance criteria**
1. `docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String WATCHFILES` prints both `WATCHFILES_FORCE_POLLING: "true"` and `WATCHFILES_POLL_DELAY_MS: "400"`.
2. The resolved `app` command still contains `--reload` and `--reload-exclude /app/tests/`.
3. Behavioural check (end-to-end, in Task 9's verification run): with the stack up, touch
   `src/mkobi/main.py` and confirm a "Reloading" line appears in `.\Makefile.ps1 logs app`
   within ~10 seconds.

**Verification command**
```powershell
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String -Pattern 'WATCHFILES|--reload'
```

---

### Task 6 — Rewrite `Makefile.ps1`

**Files touched**
- `Makefile.ps1` — full rewrite (the file is untracked; simply overwrite it)

**Hard constraints the implementation must satisfy**

| # | Constraint | Rationale |
|---|---|---|
| 1 | `param()` is the first statement; immediately followed by a PowerShell 7 version guard | `$PSVersionTable` is available in 5.1 too, so the guard works on any version |
| 2 | The script **NEVER** assigns `$env:COMPOSE_PROJECT_NAME` | The old file leaked it into every subsequent process. Use `-p` on each invocation instead. |
| 3 | `--project-directory` is **never** used | See §2.6 — it resolves `build.context: ..` to the repo's parent directory |
| 4 | Every `docker compose` invocation goes through an array splat | No string concatenation, no `--%` |
| 5 | Exactly one `exit $LASTEXITCODE` at the end of the script | Single exit path; failures propagate by leaving `$LASTEXITCODE` non-zero |
| 6 | Targets stay one-to-three-line `docker compose` calls | Portable dispatch table; see the two documented exceptions below |
| 7 | No `.env.dev` / `.env.test` parsing, no `$env:` seeding loop | Compose reads `--env-file` itself; the old loop was redundant and leaked |
| 8 | Only `fullclean` and `nuke` may branch (confirmation prompt) | They destroy data; the single justified exception to constraint 6 |

**Required skeleton**

```powershell
#Requires -Version 7.0

<#
.SYNOPSIS
    mkobi developer task runner (PowerShell 7+).
.DESCRIPTION
    Thin wrapper over `docker compose`. Every target is one docker compose
    invocation against an explicit project name. Run `.\Makefile.ps1 help`
    for the target list.
#>

param(
    [Parameter(Position = 0)]
    [string]$Target = 'help'
)

if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Error "PowerShell 7+ is required (found $($PSVersionTable.PSVersion)). Re-run with: pwsh -File .\Makefile.ps1 $Target"
    exit 1
}

# Unbound arguments (including flags such as -k and -v) land in $args verbatim.
# Do NOT declare them as parameters: PowerShell would try to bind them as names.

$DevProject  = 'mkobi'
$TestProject = 'mkobi-test'
$DevCompose  = @('-p', $DevProject,  '--env-file', '.env',
                 '-f', 'docker/docker-compose.yml',
                 '-f', 'docker/docker-compose.override.yml')
$TestCompose = @('-p', $TestProject, '-f', 'docker/docker-compose.test.yml')
$BackupDir   = 'backups'
$UpTimeout   = 180
```

`$args` is the correct mechanism here: with a `param()` block that declares only
`[Parameter(Position = 0)][string]$Target`, any unbound argument (including `-k`,
`--tb=short`, `--create-db`) is collected into `$args` verbatim rather than being parsed as
a parameter name. Verify with `.\Makefile.ps1 test-select -k some_test -v` in Task 9.

**Service names to use**

| Stack | Services |
|---|---|
| dev | `db`, `migrate`, `app`, `redis`, `rq-worker`, `frontend` (+ `nginx`, profile-gated) |
| test | `test-db`, `test-redis`, `test-migrate`, `test-app` |

**Endpoints and entrypoints to encode**

- ASGI app: `src.mkobi.main:app` (`src/mkobi/main.py` defines `app = create_app()`).
  `README.md:103` claims `mkobi.app:app` — that is wrong; `src/mkobi/app.py` has no
  module-level `app`. Do not use the README form.
- Migrations are **Alembic**, not Django: `alembic revision`, `alembic upgrade`, `alembic current`.
  There is no Django, no `manage.py`, no `makemigrations`, no `migrate --create`.
- Admin is bootstrapped from `ADMIN_USERNAME` / `ADMIN_PASSWORD` at startup. There is no
  `create_admin_user` command.
- Type checking is **mypy** (`[tool.mypy]` in `pyproject.toml`), not `basedpyright`.
- Lint/format: `ruff check` / `ruff check --fix`. `ruff format` is NOT used by this project;
  `ruff check --fix` handles import sorting (`I001`).
- Frontend: `npm --prefix frontend run lint|test|build|dev`.
- Inside the container use the **bare** binaries (`ruff`, `mypy`, `alembic`, `pytest`): the
  venv is already synced into the image and `ENV PATH="/app/.venv/bin:${PATH}"` is set, so
  `uv run` only adds a lockfile re-check that needs to write to a root-owned venv while the
  container runs as the non-root `app` user.

**Must NOT be reintroduced** (all foreign to this repo): `profile`, `load`, `consolidate`,
`consolidate-force`, `seed-photos-validate`, `seed-photos-cleanup`, `seed-photos-download`,
`load-catalog`, `create-admin`, `makemigrations`, `test-db` as a separate target name,
`test-clean-db`, `test-recreate`, any `PYTEST_OPTS` / `PYTEST_SKIP_MARKERS` handling, any
`.env.dev` / `.env.test` parsing.

**Test-suite semantics (verified from `tests/conftest.py` and `pyproject.toml`)**

- `tests/conftest.py` calls `DatabaseStarter(...).recreate_test_database()` in the
  session-scoped `setup_test_database` fixture, so pytest drops, recreates and migrates the
  test database itself. `--create-db` and `--reuse-db` are pytest-django flags and do not
  exist here.
- `mkobi_app` must pre-exist as a role — created by `docker/init-scripts/01-create-app-role.sh`
  on first `test-db` volume initialisation.
- `--cov-fail-under=65` sits in `addopts` without `--cov`, so the coverage gate is inert.
  `test-all` supplies `--cov` to make it live.
- `pytest-xdist` is installed but not in `addopts`. Per-worker database naming exists at
  `tests/conftest.py` (`_get_worker_db_suffix`), so `-n auto` works when requested.
- The `slow` and `fast` markers are declared in `pyproject.toml` but never applied. There is
  no `seed` marker in this project.

**Acceptance criteria**
1. `.\Makefile.ps1 help` lists every target in §5 with no reference to any dropped target.
2. `Select-String 'COMPOSE_PROJECT_NAME|Makefile.ps1' Makefile.ps1` finds no assignment of
   `$env:COMPOSE_PROJECT_NAME`.
3. `Select-String '\-\-project-directory' Makefile.ps1` returns nothing.
4. `Select-String 'manage\.py|locust|scripts/|basedpyright|mko-bazuna|PYTEST_OPTS|PYTEST_SKIP_MARKERS' Makefile.ps1` returns nothing.
5. Exactly one `exit $LASTEXITCODE` appears, on the final line.
6. `.\Makefile.ps1 test-select -k test_dummy -v` forwards both `-k test_dummy` and `-v` to
   pytest unchanged (confirmed in Task 9's run).
7. Every target in §5 executes without an unbound-variable or argument-binding error.

**Verification command**
```powershell
pwsh -NoProfile -Command "Set-Location 'C:\py_dev\mkobi'; .\Makefile.ps1 help"
Select-String 'COMPOSE_PROJECT_NAME|--project-directory|manage\.py|locust|basedpyright|mko-bazuna' Makefile.ps1
```

---

### Task 7 — Agent-instruction file references stale targets

> **Scope note.** This task is an addition to the stated scope. It is included because
> `.kilo/rules/commands.md` instructs agents to run `.\Makefile.ps1 up`, `test`, `test-all`,
> `test-recreate`, and `test-down` — targets that will not exist after Task 6 — and documents
> a `$dc` alias pinned to the foreign `mko-bazuna-test` project. Left as-is it becomes a
> standing instruction to invoke commands that now fail. **Drop this task if the doc rewrite
> is deliberately deferred.**

**Files touched**
- `.kilo/rules/commands.md` — rewrite the Makefile/command sections

**Change**

Replace the "Quick start" table and the `mko-bazuna-dev` / `mko-bazuna-test` references with
the new target names, and delete the Django-specific sections (i18n / `makemessages` /
`gettext` / `manage.py`) — none of that exists in this repo. Correct these specific claims:

| Current text | Correction |
|---|---|
| `$DevProject = "mko-bazuna-dev"` | `-p mkobi` / `-p mkobi-test` |
| `.\Makefile.ps1 test-recreate` | `.\Makefile.ps1 test-fresh` |
| "Fast test gate (skips nightly `seed` tests)" | Remove — there is no `seed` marker |
| `$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test ...'` | `docker compose -p mkobi-test -f docker/docker-compose.test.yml` |
| `uv run basedpyright <path>` | `uv run mypy <path>` |
| `make <target>` parity claim | Remove — there is no `Makefile` in this repo |

**Acceptance criteria**
1. `Select-String 'mko-bazuna|test-recreate|seed|basedpyright|manage\.py|PYTEST_OPTS' .kilo/rules/commands.md` returns nothing.
2. Every `.\Makefile.ps1 <target>` invocation in the file names a target that exists in §5.
3. The file remains English-only and under the splitting threshold.

**Verification command**
```powershell
Select-String 'mko-bazuna|test-recreate|basedpyright|manage\.py' .kilo/rules/commands.md
```

---

### Task 8 — Remove stray root artifacts

**Files touched**
- delete `C:\py_dev\mkobi\$null`
- delete `C:\py_dev\mkobi\test_write_permission.md`
- `.gitignore` — append one block

**Change**

`$null` is a 5-line file created by a mis-quoted PowerShell redirection (`2>$null` parsed as a
literal filename). Its entire content is a captured Docker CLI stderr:

```
docker: 'docker ps' accepts no arguments
```

`test_write_permission.md` is a 3-line scratch note ("This is a test file to verify write
permissions.").

Append to the end of `.gitignore`:

```gitignore
# PowerShell mis-quoted redirection artifacts and scratch files
$null
backups/
```

`backups/` is required because the new `backup` target writes there and `.gitignore` does not
currently cover it (verified: `git check-ignore backups` returns nothing).

Remove with:
```powershell
git rm --cached -- '$null' 'test_write_permission.md'
Remove-Item -LiteralPath '$null','test_write_permission.md' -Force
```

> **WARNING — pre-existing working-tree changes.** `git status` already reports ~19 deletions
> under `.ai/` (`.ai/audit/templates/*`, `.ai/builders/**`, `.ai/models/*`,
> `.ai/plans/audit-fix-plan.md`, `.ai/structure/**`, `.ai/tasks/templates/*`, `.ai/templates/*`,
> `.kilo/agents/implementor-orchestrator.md`, several `.kilo/commands/**`) plus many modified
> and untracked `.kilo/` files. **None of these belong to this work.** Do not stage them, do
> not revert them, do not `git add -A`. Stage explicitly by path:
> ```powershell
> git add -- Makefile.ps1 .gitignore
> git rm --cached -- '$null' 'test_write_permission.md'
> ```
> `.ai/plans/audit-fix-plan.md` showing as deleted while `.ai/plans/` gains this file is
> expected; do not restore it.

**Acceptance criteria**
1. `Test-Path '$null'` and `Test-Path 'test_write_permission.md'` both return `False`.
2. `git check-ignore -v '$null'` and `git check-ignore -v backups` both resolve to a rule in `.gitignore`.
3. `git status --porcelain` shows no other new deletions beyond the pre-existing ones listed above.

**Verification command**
```powershell
Test-Path '$null'; Test-Path 'test_write_permission.md'
git check-ignore -v '$null' backups
git status --porcelain
```

---

## 5. Full Target Table for `Makefile.ps1`

`@Dev` = `$DevCompose` = `-p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml`
`@Test` = `$TestCompose` = `-p mkobi-test -f docker/docker-compose.test.yml`

### Stack lifecycle (dev)

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `up` | Start dev stack and block until healthy | `docker compose @Dev rm -sf migrate` then `docker compose @Dev up -d --wait --wait-timeout $UpTimeout` | No |
| `down` | Stop and remove dev containers + network | `docker compose @Dev down --remove-orphans` | No |
| `restart` | Restart code services (keeps volumes) | `docker compose @Dev restart app rq-worker frontend` | **Yes** |
| `build` | Build dev images from cache | `docker compose @Dev build` | No |
| `rebuild` | Rebuild from scratch, then start | `docker compose @Dev build --no-cache` then `up` | No |
| `ps` | Show dev container status | `docker compose @Dev ps` | No |
| `logs [service]` | Follow logs (all services if omitted) | `docker compose @Dev logs -f --tail=200 [@args]` | **Yes** |
| `shell` | Interactive bash in a throwaway `app` container | `docker compose @Dev run --rm --no-deps app bash` | No |
| `exec [cmd...]` | Run a command in the running `app` container | `docker compose @Dev exec app @args` | **Yes** |
| `dev-watch` | Run dev stack attached, streaming all logs (Ctrl+C stops) | `docker compose @Dev up --remove-orphans` | No |

### Stack lifecycle (test)

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `test-up` | Start `test-db` + `test-redis` and wait for healthy | `docker compose @Test rm -sf test-migrate test-app` then `up -d --wait --wait-timeout $UpTimeout test-db test-redis` | No |
| `test-down` | Stop test stack, keep volumes | `docker compose @Test down --remove-orphans` | No |
| `test-reset` | Destroy test volumes and recreate a clean test DB | `docker compose @Test down -v --remove-orphans` then `up -d --wait test-db test-redis` | No |
| `test-logs` | Follow test service logs | `docker compose @Test logs -f --tail=200 test-db test-redis` | **Yes** |
| `test-ps` | Show test container status | `docker compose @Test ps` | No |

### Tests

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `test` | Default gate: full suite, DB auto-recreated by conftest | `docker compose @Test up -d --wait test-db test-redis` then `docker compose @Test run --rm --no-deps test-app pytest` | No |
| `test-all` | Full suite with live coverage gate (`--cov` makes `--cov-fail-under=65` meaningful) | same as `test`, with `pytest --cov=src/mkobi --cov-report=term-missing` | No |
| `test-fresh` | Wipe test volumes, recreate schema, run full suite | `test-reset` then the `test` sequence | No |
| `test-select <args>` | Forward arbitrary args to pytest (verbatim) | `docker compose @Test run --rm --no-deps test-app pytest @args` | No |
| `test-shell` | Interactive bash inside the test image | `docker compose @Test run --rm -it --no-deps test-app bash` | No |

`--no-deps` on the test `run` invocations is deliberate: `test-app` declares
`depends_on: test-migrate (service_completed_successfully)`, and `test-migrate` is a
redundant duplicate image build (`tests/conftest.py` migrates the database itself).
`--no-deps` skips it and saves a full image build per invocation.

### Quality gates

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `lint` | Ruff check backend + tests | `docker compose @Dev run --rm --no-deps app ruff check src/ tests/` | No |
| `format` | Ruff auto-fix (incl. import sorting) | `docker compose @Dev run --rm --no-deps app ruff check --fix src/ tests/` | No |
| `typecheck` | Mypy | `docker compose @Dev run --rm --no-deps app mypy src/` | No |
| `fe-lint` | ESLint | `npm --prefix frontend run lint` | No |
| `fe-test` | Vitest with coverage | `npm --prefix frontend run test` | No |
| `check` | Aggregate gate: lint + typecheck + fe-lint + fe-test | `Invoke-Lint` `&&` `Invoke-Typecheck` `&&` `Invoke-FeLint` `&&` `Invoke-FeTest` | No |

`fe-lint` and `fe-test` are host-native and require `fe-install` to have been run once.

### Database

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `migrate` | Run `alembic upgrade head` (one-shot `migrate` service) | `docker compose @Dev run --rm migrate` | No |
| `migration-new <msg>` | Autogenerate a revision | `docker compose @Dev run --rm app alembic revision --autogenerate -m @args` | No |
| `migration-status` | Show current vs head | `docker compose @Dev run --rm app alembic current` | No |
| `psql` | Interactive psql on the dev DB | `docker compose @Dev exec db psql -U postgres -d bidb` | **Yes** |
| `psql-c <sql>` | One-shot SQL against the dev DB | `docker compose @Dev exec -T db psql -U postgres -d bidb -c @args` | **Yes** |

`migration-new` runs **without** `--no-deps` because `--autogenerate` needs live DB metadata;
Compose will therefore start `migrate` and `db` first. The generated file lands on the host
because `../alembic` is bind-mounted read-write into the dev `app` service.

### Backup

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `backup` | `pg_dump -F c` inside the container, `cp` out to `./backups/` | `exec -T db pg_dump -U postgres -d bidb -F c -f /tmp/mkobi.dump` → `cp db:/tmp/mkobi.dump ./backups/bidb-<stamp>.dump` → `exec -T db rm -f /tmp/mkobi.dump` | **Yes** |
| `restore <file>` | Copy the dump in, then `pg_restore` | `cp <file> db:/tmp/mkobi-restore.dump` → `exec -T db pg_restore -U postgres -d bidb --clean --if-exists /tmp/mkobi-restore.dump` → `exec -T db rm -f /tmp/mkobi-restore.dump` | **Yes** |
| `prune-backups` | Delete `./backups/*.dump` older than 7 days | host-side `Get-ChildItem` + `Remove-Item` | No |

Never redirect `pg_dump` stdout to a host file — PowerShell corrupts binary output. The
dump is written to a path **inside** the container and moved with `docker compose cp`.

### Host-native

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `uv-sync` | Sync the host Python venv from the lockfile | `uv sync --frozen` | No |
| `fe-install` | Deterministic frontend install | `npm --prefix frontend ci` | No |
| `open` | Open the Vite dev URL in the default browser | `Start-Process 'http://localhost:5173'` | No |

There is deliberately **no** host-side `fe-dev` target: `frontend/vite.config.ts` hardcodes
the dev-server proxy target to `http://app:8000`, which resolves only on the compose network.
A host-side `npm run dev` would proxy to a name that does not exist on the host. Fixing that
is deferred (§7.4).

### Diagnostics and cleanup

| Target | Purpose | Command shape | Running stack? |
|---|---|---|---|
| `config` | Print resolved dev config | `docker compose @Dev config` | No |
| `config-test` | Print resolved test config | `docker compose @Test config` | No |
| `doctor` | Print Docker/Compose/PS versions, resolved project names, service lists | `docker version --format ...`, `docker compose version`, both `config --services` | No |
| `clean` | Remove dev + test containers and networks, **keep volumes** | `docker compose @Dev down --remove-orphans` then `@Test down --remove-orphans` | No |
| `fullclean` | Same, plus remove both projects' volumes (prompts first) | `down -v --remove-orphans` for `@Dev` and `@Test` | No |
| `nuke` | `fullclean` + build-cache and unused-image prune (prompts first) | `fullclean` then `docker builder prune -af`, `docker image prune -af` | No |
| `help` | Print the target list | `Show-Help` | No |

`config` and `config-test` print resolved values including `DATABASE__PASSWORD` and
`JWT__SECRET_KEY`. Do not paste the output into a shared channel.

`nuke` deliberately does **not** run `docker system prune --volumes`. That command is
daemon-global and would delete other projects' volumes — this machine currently holds
`mko-bazuna-dev_postgres_data`, `mko-bazuna-test_postgres_data`, `code_base_qdrant_data`,
`claude-memory` and `mcp-sqlite`, and the `mko-bazuna-dev` / `mko-bazuna-test` stacks are
**running right now**. See §7.5.

---

## 6. Verification Plan

Run in order. Each step names what a failure looks like.

**Phase 1 — static config (no containers touched)**

```powershell
# V1 — project names
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String '^name:'          # name: mkobi
docker compose -f docker/docker-compose.test.yml config | Select-String '^name:'                                                                  # name: mkobi-test
```
*Failure:* still `name: docker` → Task 1 did not land, or `name:` was inserted after `services:`.

```powershell
# V2 — dev service list contains rq-worker
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config --services
```
*Expected:* `db`, `migrate`, `app`, `redis`, `rq-worker`, `frontend` (order varies), and **no** `nginx`.
*Failure:* `rq-worker` missing → Task 2 incomplete; `profiles: [production]` still present in the base file.

```powershell
# V3 — no container_name in the test compose
Select-String 'container_name' docker/docker-compose.test.yml
```
*Expected:* no output.

```powershell
# V4 — test compose is hermetic (run Task 4's acceptance criterion 2 verbatim)
```
*Failure:* any `LEAKED_SHOULD_NOT_APPEAR` match → an `${...}` survived.

```powershell
# V5 — hot-reload vars
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String 'WATCHFILES|--reload'
```
*Expected:* `WATCHFILES_FORCE_POLLING: "true"`, `WATCHFILES_POLL_DELAY_MS: "400"`, and a command containing `--reload`.

**Phase 2 — one-time migration (§3.3)**

```powershell
docker volume ls --filter label=com.docker.compose.project=docker
```
*Expected:* only the `VOLUME NAME` header. *Failure:* volumes remain → Step 1 did not complete.

**Phase 3 — first dev start (validates the `--wait` strategy)**

```powershell
.\Makefile.ps1 up
```
**The `[UNVERIFIED]` item is now RESOLVED.** `\Makefile.ps1 up` completed with **exit code 0**.
`up --wait` **does** treat the exited-0 `migrate` one-shot as satisfied — no fallback needed, and
the §6 Phase 3 approval gate is moot. Observed on 2026-09-30:

```
mkobi-db-1         Up (healthy)
mkobi-redis-1      Up (healthy)
mkobi-app-1        Up
mkobi-rq-worker-1  Up
mkobi-frontend-1   Up
mkobi-migrate-1    Exited (0)
```

*Success:* exits 0; `db`, `redis`, `app`, `rq-worker`, `frontend` are running; `migrate` has
  exited 0.
*Failure modes:*
- `container ... unhealthy` or `dependency failed to start` → the `--wait` timeout fired.
  Diagnose with `.\Makefile.ps1 ps` then `.\Makefile.ps1 logs db`.
- A `--wait` failure that names `migrate` → **[RESOLVED — does not occur; see above]**
  The documented fallback (`rm -sf migrate` → `run --rm migrate` → `up --wait`) is therefore
  **not required** and must not be substituted in. The `rm -sf migrate` in `Invoke-Up` remains
  as the stale-migration guard, which is a different concern.


```powershell
.\Makefile.ps1 ps
.\Makefile.ps1 logs app
```
*Expected:* app log shows a successful startup; no `CORS` `ValueError`.

```powershell
# End-to-end health (host port 8010 after the §7.6.1 change; override with APP_HOST_PORT)
Invoke-WebRequest -UseBasicParsing http://localhost:8010/health | Select-Object StatusCode
```
*Expected:* `200`.

**Phase 4 — hot reload (Task 5's behavioural criterion)**

```powershell
.\Makefile.ps1 dev-watch
```
In a second shell, edit `src/mkobi/main.py` (add a comment).
*Expected:* a `Reloading` line within ~10 s.
*Failure:* nothing → `WATCHFILES_FORCE_POLLING` is not reaching the process; re-check V5.

**Phase 5 — test stack and arg forwarding**

```powershell
.\Makefile.ps1 test-up
.\Makefile.ps1 test-ps
```
*Expected:* `test-db` healthy, `test-redis` healthy.
*Failure:* `role "mkobi_app" does not exist` → the `test_postgres_data` volume predates the
init script; run `.\Makefile.ps1 test-reset` once.

```powershell
.\Makefile.ps1 test-select -k test_dummy -v
```
*Expected:* pytest receives `-k test_dummy -v` verbatim and reports `no tests ran` /
a deselected count — **not** a PowerShell parameter-binding error.
*Failure:* `A parameter cannot be found that matches parameter name 'k'` → `$Target` was
declared with a second parameter instead of relying on `$args`.

```powershell
.\Makefile.ps1 test
```
*Expected:* the suite runs against the containerised `test-db` and the session-scoped
`setup_test_database` fixture recreates and migrates the schema.
*Known non-fatal noise:* the test image runs as the non-root `app` user while the working
directory `/app` is root-owned, so pytest may print
`could not create cache path: /.pytest_cache`. This is a warning, not a failure. Do not
"fix" it by adding `--no-cacheprovider`; note it in the run output instead.

**Phase 6 — quality gates and cleanup**

```powershell
.\Makefile.ps1 fe-install
.\Makefile.ps1 lint
.\Makefile.ps1 typecheck
.\Makefile.ps1 check
.\Makefile.ps1 backup
Get-ChildItem .\backups
.\Makefile.ps1 restore .\backups\<the-file-just-created>
.\Makefile.ps1 test-down
.\Makefile.ps1 down
```
*Expected:* `backup` produces a non-empty `.dump` (check `Get-Item` reports a plausible
size — a few MB, not 0 bytes and not a few hundred bytes; a tiny file means binary
corruption). `restore` completes without `pg_restore` errors.

**Phase 7 — hygiene**

```powershell
Test-Path '$null'; Test-Path 'test_write_permission.md'    # both False
git check-ignore -v '$null' backups
git status --porcelain                                      # no unexpected new deletions
```

---

## 7. Risks, Rollback, and Rejected Options

### 7.1 Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `up --wait` does not treat the exited-0 `migrate` one-shot as satisfied | Medium | Named fallback in §6 Phase 3; resolve empirically before committing the script |
| `docker compose rm -sf migrate` removes a container while `app` is mid-start | Low | `rm -s` stops it first; `app` restarts via `restart: unless-stopped` |
| Deleting the six `docker_*` volumes loses local dev data | **Certain** | §3.3 warns explicitly and provides a binary-safe pre-deletion backup sequence |
| Changing `CORS_ORIGINS` from `:?` to a default weakens production posture | Low | The default is a member of `CORS_ORIGINS_PLACEHOLDERS`, so `ENV=production` raises at startup — it fails closed |
| Removing `container_name:` changes container names, breaking muscle memory / bookmarks | Low | Container names become `mkobi-db-1`, `mkobi-test-test-db-1`; documented in §5 |
| `nuke` / `image prune -a` affects other projects on this machine | Medium | `nuke` prompts first; it does **not** run `system prune --volumes` (see §7.5) |
| The new `backups/` directory is not git-ignored | Certain | Task 8 adds it to `.gitignore` |
| Staging unrelated `.ai/` and `.kilo/` changes | Medium | Task 8 warns explicitly; stage by explicit path, never `git add -A` |

### 7.2 Rollback

Every change in Part A is a small, self-contained diff to a text file — `git checkout --
docker/docker-compose.yml docker/docker-compose.override.yml docker/docker-compose.test.yml`
reverts all of it. Reverting Task 1 restores the `docker` project name, so also expect the
`docker_*` volumes to become visible again.

`Makefile.ps1` is untracked, so reverting it means rewriting it; keep the old copy as
`Makefile.ps1.bak` until Task 6 passes verification (do not commit the `.bak`).

Part C is recoverable from git history until the deletion is committed.

The volume deletion in §3.3 step 2 is **the only irreversible step** in this plan.

### 7.3 Rejected options

| Option | Why rejected |
|---|---|
| `docker compose --project-directory .` | **Empirically refuted on this machine.** Resolves `build: {context: ..}` to `C:\py_dev` (the repo's parent) instead of `C:\py_dev\mkobi`, so the whole parent directory becomes build context. Use explicit `--env-file .env` instead. Never reintroduce. |
| Setting `$env:COMPOSE_PROJECT_NAME` in the script | Leaks into every subsequent process in the session. This was the old file's bug. Use `-p` per invocation. |
| A `docker/.env.test` for the test stack | `--env-file` cannot outrank the shell process environment, so it gives false comfort while a real leak persists. Hard-coded literals are correct for a disposable test DB. |
| `profiles: []` in the override to un-gate a service | Compose folds `[]` into the union; it does not clear `production`. Delete the base `profiles:` key instead. |
| `profiles: []` for `nginx` (same shape) | Would work, but is harder to reason about than leaving nginx gated and using `--profile production` explicitly. |
| `docker compose watch` for `dev-watch` | The subcommand exists in Compose v5.5.1 but requires `develop:` blocks, which none of these compose files have. `dev-watch` is therefore "attached `up`" (streaming logs), and hot reload is handled by uvicorn `--reload` + `WATCHFILES_FORCE_POLLING`. Adding `develop:` blocks is deferred. |
| Task / just / mise as the runner | No CI, Windows-only team, ~30 thin targets, and a new install step for zero benefit. A hand-written script keeps the dispatch table portable. |
| Importing `PSScriptRoot` to run from any directory | Relative paths (`--env-file .env`, `-f docker/...`) are resolved against the current directory. Keep the script cwd-relative and say so in `help`, rather than silently behaving differently from a different cwd. |
| Keeping a `Makefile` (GNU make) for parity | No `Makefile` exists in this repo (`Test-Path Makefile` → `False`) and the team is Windows-only. Do not add one. |

### 7.4 Deferred — explicitly out of scope

None of the following is part of this plan. Each carries a one-line rationale.

> **Update (2026-09-30):** the `REDIS__HOST` item formerly at the top of this table has since
> been **implemented** — see §7.6. It is removed from the deferred set.

| Item | Rationale for deferral | Precise fix (so it is not lost) |
|---|---|---|
| `docker/.env.production` ships with every secret commented out | Fixing it means inventing production credentials — an operational decision, not a tooling change. | Out of band, with the operator who owns the deployment. |
| `docs/11-guides/docker.md` profile documentation is wrong in three ways | Documentation-only; must be written **after** Tasks 1–5 land so it describes the fixed state. | (a) delete the "Note on Frontend Profile" block — no `frontend` profile exists; (b) `production` adds only `rq-worker` and `nginx` — `redis` has no profile; (c) the default set is `db, migrate, app, redis, rq-worker` — `frontend` is in the override only. Also add the new `test` target names and the `-p` project names. |
| `nginx` serves a gitignored, host-local `frontend/dist` | A design change (bake the bundle or build in the nginx stage), not a task-runner fix. | Build the bundle in the nginx stage, or drop the `../frontend/dist` bind mount in favour of the `/app/frontend/dist` already copied by the `prod` image. |
| `test-migrate` is redundant | `tests/conftest.py` already recreates and migrates the test DB. | Delete the `test-migrate` service from `docker/docker-compose.test.yml` and drop the `depends_on` entry from `test-app`. |
| Vite proxy hardcoded to `http://app:8000` | Fixing it means a proxy target switch based on environment — a frontend change. | Make the target conditional in `frontend/vite.config.ts` (e.g. `process.env.VITE_API_TARGET ?? 'http://app:8000'`). |
| `pyproject.toml` cleanup | Unrelated to the runner; changing dependency groups risks the image build. | Remove the broken `mko-get-mediascope = "mkobi.app:app"` console script, the unused `testcontainers[postgres,redis]` dev dependency, the unused `slow` / `fast` markers, and either add `--cov` to `addopts` or drop `--cov-fail-under=65`. |
| `.dockerignore` does not exclude `docker/.env*` | Latent secret-in-build-context trap, but no change is needed to complete this plan. | Add `docker/.env*` and `!.env.example` to `.dockerignore`. |
| `read_only: true` prod `app` has no `/tmp` tmpfs | Production hardening; separate change. | Add to `app` in `docker/docker-compose.yml`:<br>`tmpfs:`<br>`  - /tmp` |
| `migrate` runs as the `postgres` superuser | Security hardening; requires a DDL-only role and an init-script change. | Create a dedicated migration role in `docker/init-scripts/` and point `migrate.DATABASE__USER` at it. |
| README is in Russian and documents non-existent commands | Violates the repo's English-only rule, but rewriting the README is its own task. | Translate to English; correct `mkobi.app:app` → `src.mkobi.main:app`; replace the Django command list with the §5 target table. |
| Reaping orphaned `mko-bazuna-*` containers and volumes | **Not safe to bundle.** That stack is **running right now** (`mko-bazuna-dev-web-1`, `mko-bazuna-dev-db-1`, `mko-bazuna-test-db-1` and others are up), so this is a live machine state belonging to another project. | Requires explicit user confirmation. Only then:<br>`docker compose -p mko-bazuna-dev -f <its compose files> down`<br>`docker compose -p mko-bazuna-test -f <its compose files> down -v` |

### 7.5 Deviation from the brief, with rationale

The brief's `nuke` target was sketched as `fullclean` + `docker system prune -f --volumes`.
This plan drops the `--volumes` prune. `system prune --volumes` is daemon-global and would
delete every unused volume on the machine, including `mko-bazuna-dev_postgres_data`,
`mko-bazuna-test_postgres_data`, `code_base_qdrant_data`, `claude-memory` and `mcp-sqlite`.
`nuke` instead performs project-scoped `down -v` for `-p mkobi` and `-p mkobi-test` only,
plus `docker builder prune -af` and `docker image prune -af`, behind a confirmation prompt.

### 7.6 Follow-up work (2026-09-30) — IMPLEMENTED AFTER THE PLAN LANDED

Three items were raised after this plan was implemented. All three are now **done** and
independently verified. They are recorded here so the plan reflects the true current state.

#### 7.6.1 Host ports made collision-proof

**Problem.** The plan assumed mkobi's dev/test stacks could run in parallel with other
projects. They could not: two published ports collided with a **live** stack on this machine
belonging to another project (`mko-bazuna`), which must not be stopped.

| Host port | Held by | mkobi service |
|---|---|---|
| `5433` | `mko-bazuna-test-db-1` | test `test-db` |
| `8000` | `mko-bazuna-dev-web-1` | dev `app` |

**Fix — configurable, not merely renumbered.** Renumbering would just move the collision to
the next port. Host ports are now Compose-interpolated with defaults:

| Service | File | Before | After |
|---|---|---|---|
| dev `app` | `docker/docker-compose.override.yml` | `8000:8000` | `${APP_HOST_PORT:-8010}:8000` |
| test `test-db` | `docker/docker-compose.test.yml` | `5433:5432` | `${TEST_DB_HOST_PORT:-5434}:5432` |
| test `test-redis` | `docker/docker-compose.test.yml` | `6380:6379` | `${TEST_REDIS_HOST_PORT:-6381}:6379` |
| test `test-app` | `docker/docker-compose.test.yml` | `8001:8000` | `${TEST_APP_HOST_PORT:-8001}:8000` |
| dev `frontend` | `docker/docker-compose.override.yml` | `5173:5173` | unchanged (never conflicted) |
| dev `db` | `docker/docker-compose.override.yml` | `127.0.0.1:5432:5432` | unchanged (loopback-bound; the other project's dev DB publishes nothing) |

Only **container-internal** ports are unchanged, so `frontend/vite.config.ts` (`http://app:8000`),
the `app` healthcheck (`localhost:8000/health`) and the `nginx` upstream (`app:8000`) all still
work untouched. The documented human-facing backend URL moved from `:8000` to `:8010`; the
recommended dev entry point (Vite on `5173`) is unaffected.

`tests/conftest.py:18` and `:42` — the native-pytest default moved `5433` → `5434`, still via
`os.environ.setdefault` so an explicit env var wins. Inside Docker the compose value (`5432`)
still takes precedence.

**Hermeticity preserved.** This reintroduced interpolation **for ports only**. Every test
credential remains a literal. Verified: exporting `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD`
and `JWT__SECRET_KEY` with `LEAKED*` values produces **0 matches** in the resolved config, while
`POSTGRES_PASSWORD: test_password` and `MKOBI_APP_PASSWORD: test_app_password` remain literals.
`TEST_DB_HOST_PORT=5499` correctly resolves to `published: "5499"`.

Docs updated to match: `docs/11-guides/docker.md`, `docs/10-deployment/deployment.md`,
`docs/99-reference/run-guide.md`, `docs/99-reference/swagger.md`, `README.md`,
`.kilo/rules/commands.md`, `.ai/context/commands.md`, `.env.example`. A re-scan of all eight
files for `5433`, `6380` and `localhost:8000` returns **no matches**.

`docs/SPEC.md` was deliberately **not** edited — lines 164/180/202 are an append-only record of
what was done at a point in time, not forward-looking operational guidance.

#### 7.6.2 `REDIS__HOST` production bug — FIXED

The item previously at the top of the §7.4 table. `src/mkobi/config.py:212-218` defaults
`RedisSettings.host` to `"localhost"`, which inside a container is the container itself. With
`rate_limiter_fail_closed` defaulting true and no error handling in `api/deps.py`, production
login and upload would fail closed — a total auth outage.

Added to `services.app.environment` in `docker/docker-compose.yml`:

```yaml
      REDIS__HOST: redis
      REDIS__PORT: "6379"
```

**`rq-worker` was deliberately left alone.** The plan's §7.4 had prescribed adding it there too;
that was over-broad and was not applied. Code evidence: `get_redis_client` /
`get_async_redis_client` (`src/mkobi/core/redis_client.py:11-52`) are called only from the
FastAPI request path (`api/deps.py`, `api/routes/*`, `services/auth_service.py`). The worker
runs `/app/.venv/bin/rqworker --url redis://redis:6379/0` — its Redis target is passed on the
command line, and `src/mkobi/workers/data_worker.py` reads no Redis config at all. Adding the
vars would introduce settings the running code path never reads.

#### 7.6.3 Legacy `docker_*` volumes — DELETED

The six volumes orphaned by the `name:` change in Task 1 have been removed:

```
docker_app_data, docker_frontend_vite_cache, docker_postgres_data,
docker_redis_data, docker_test_postgres_data, docker_test_redis_data
```

This **destroyed the local development database `bidb` and test database `bidb_test`** — the
destructive step flagged in §3.3. The user explicitly approved the deletion. `docker volume rm`
exited 0, and `docker volume ls --filter label=com.docker.compose.project=docker` now returns
nothing. The current live state is a single `mkobi-test_test_postgres_data` volume, which the
test stack reuses and which is repopulated by `tests/conftest.py` on every run.

The one-time migration sequence in §3.3 Steps 0–2 is therefore **complete**; it should not be
re-run.

#### 7.6.4 Post-change verification (all passed)

| Check | Result |
|---|---|
| `Makefile.ps1 test-up` | exit 0 — `test-db` and `test-redis` both reach **Healthy** |
| `pg_isready` in `test-db` | `/var/run/postgresql:5432 - accepting connections` |
| `mkobi_app` role present | yes (init script ran on the fresh volume) |
| Resolved test ports | `5434` / `6381` / `8001` |
| Resolved dev ports | `8010` / `5432` / `5173` |
| Base `app` Redis vars | `REDIS__HOST: redis`, `REDIS__PORT: "6379"` |
| Credential-leak regression | 0 matches for `LEAKED*` |
| `Makefile.ps1 help` | exit 0 |
| `Makefile.ps1` parse | no syntax errors |
| `ruff check tests/conftest.py` | All checks passed |
| Residual state after teardown | no containers, no networks |

The `Bind for 0.0.0.0:5433 failed` blocker that ended the original implementation is resolved.

#### 7.6.5 First dev start — VERIFIED END TO END (2026-09-30)

The last unverified item. `\Makefile.ps1 up` was executed for the first time and completed with
**exit code 0**.

| Container | Status |
|---|---|
| `mkobi-db-1` | Up (healthy) |
| `mkobi-redis-1` | Up (healthy) |
| `mkobi-app-1` | Up |
| `mkobi-rq-worker-1` | Up |
| `mkobi-frontend-1` | Up |
| `mkobi-migrate-1` | **Exited (0)** |

| Runtime check | Result |
|---|---|
| `GET http://localhost:8010/health` | **200** — `{"status":"healthy","database":"connected"}` |
| `GET http://localhost:5173` (Vite) | **200** |
| `redis.Redis(host='redis').ping()` **inside the `app` container** | **`True`** |
| `WATCHFILES_FORCE_POLLING` in the running `app` container | `true` |
| App startup log | clean — no `ConnectionError`, no `CRITICAL`, no refused connections |

The Redis check is the direct proof that the §7.6.2 fix works: the same command against the
unfixed compose would have tried `localhost` inside the container and failed. `rq-worker` is
running for the first time, confirming the §Task 2 profile fix. The `AUTHENTICATION_FAILED` /
"Refresh token not found" lines in the log are the frontend's expected silent-refresh probe on
first page load, not a fault.

**Still outstanding from §7.4:** the `mko-bazuna-*` stacks remain running and untouched, as
they belong to another project.

---

## 8. Definition of Done

**Part A — Compose**
- [ ] `docker/docker-compose.yml` has a top-level `name: mkobi`.
- [ ] `docker/docker-compose.test.yml` has a top-level `name: mkobi-test`.
- [ ] `docker/docker-compose.override.yml` has **no** `name:` key.
- [ ] All four `container_name:` keys are gone from `docker/docker-compose.test.yml`.
- [ ] `profiles: [production]` is gone from `rq-worker` in the base; `profiles: []` is gone from the override; `nginx` keeps `profiles: [production]`.
- [ ] `CORS_ORIGINS` in the base compose uses `:-` with a placeholder default, not `:?`.
- [ ] `docker/docker-compose.test.yml` contains zero `${...}` interpolations and ignores exported shell variables.
- [ ] The dev `app` service sets `WATCHFILES_FORCE_POLLING: "true"` and `WATCHFILES_POLL_DELAY_MS`.
- [ ] `docker compose config --services` returns `db, migrate, app, redis, rq-worker, frontend` for the dev pair.

**Part B — Script**
- [ ] `Makefile.ps1` is a full rewrite; every target in §5 exists and runs.
- [ ] `param()` is first; the PowerShell 7 guard follows immediately.
- [ ] `$env:COMPOSE_PROJECT_NAME` is never assigned; `-p mkobi` / `-p mkobi-test` are passed per invocation.
- [ ] `--project-directory` appears nowhere.
- [ ] Exactly one `exit $LASTEXITCODE`, on the final line.
- [ ] No string-built or `--%` command lines; all invocations use array splatting.
- [ ] `test-select <args>` forwards arbitrary flags verbatim.
- [ ] No reference to `manage.py`, `locust`, `scripts/`, `basedpyright`, `mko-bazuna`, `PYTEST_OPTS`, or `PYTEST_SKIP_MARKERS`.
- [ ] `up` hard-fails with a clear message when `--wait` returns non-zero.

**Part C — Hygiene**
- [ ] `$null` and `test_write_permission.md` are deleted and removed from git.
- [ ] `.gitignore` covers `$null` and `backups/`.
- [ ] No unrelated `.ai/` or `.kilo/` changes are staged or reverted.

**End-to-end**
- [ ] `.\Makefile.ps1 up` reaches a healthy dev stack; `http://localhost:8010/health` returns 200 (host port per §7.6.1).
- [ ] Editing `src/mkobi/main.py` triggers a uvicorn reload.
- [ ] `.\Makefile.ps1 test` runs the suite green against the containerised `test-db`.
- [ ] `.\Makefile.ps1 backup` then `restore` round-trips a non-corrupt dump.
- [ ] `.\Makefile.ps1 help` output matches §5.

**Documentation** (only if Task 7 is accepted)
- [ ] `.kilo/rules/commands.md` names no target that does not exist in §5.
