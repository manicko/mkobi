---
id: docker-guide
domain: guides
tags:
  - docker
  - deployment
  - devops
related:
  - run-guide
  - deployment
  - task-queue-migration
  - file-cleanup
  - processing-api
---

# Docker Guide for mkobi BI Dashboard System

## Purpose

This document describes the containerised state of mkobi BI Dashboard: the two
Compose projects, the services in each, published host ports, profiles, build
stages and health checks. It also explains the failure modes seen most often in
development.

`.\Makefile.ps1` is the canonical entry point for developer commands. This
document describes the *state* those commands act on; the raw `docker compose`
invocations are given for reference and diagnosis, not as the normal path.

## Architecture Overview

### Compose Projects

Two independent Compose projects exist. Each is pinned by a top-level `name:`
key, so tearing one stack down can never destroy the other.

| Project | `name:` declared in | Files | Used for |
|---------|--------------------|-------|----------|
| `mkobi` | `docker/docker-compose.yml` | `docker-compose.yml`, plus `docker-compose.override.yml` in development | Development and production |
| `mkobi-test` | `docker/docker-compose.test.yml` | `docker-compose.test.yml` | Test suite |

`docker-compose.override.yml` deliberately declares **no** `name:`. With
multiple `-f` files the last one would win, and development and production are
the same stack — so the name belongs in the base file only.

No compose file sets `container_name:`. Those keys are daemon-global, they
prevent a second concurrent stack, and `docker compose run` discards them
silently.

### Service Sets

The service set depends on which files and profiles are supplied. Verify any of
these locally with `docker compose ... config --services`.

| Invocation | `config --services` |
|------------|---------------------|
| Base file only | `db`, `migrate`, `app`, `redis`, `rq-worker` |
| Base + `docker-compose.override.yml` (development) | `db`, `migrate`, `app`, `frontend`, `redis`, `rq-worker` |
| Base + `--profile production` | `db`, `migrate`, `app`, `nginx`, `redis`, `rq-worker` |
| `docker-compose.test.yml` | `test-db`, `test-migrate`, `test-app`, `test-redis` |

Two consequences cause most of the confusion in this area:

- **`frontend` is defined only in the development override.** A base-file-only
  invocation never starts it, because no profile enables it — there is no
  `frontend` profile. Add `-f docker/docker-compose.override.yml` to reach it.
- **`nginx` is the only profile-gated service in the project.** `redis` and
  `rq-worker` are unconditional and start with the base file whether or not a
  profile is passed.

`migrate` is a one-shot (`restart: "no"`): it runs `alembic upgrade head` and
exits 0. `app` depends on it with `condition: service_completed_successfully`.

### Containers

| Service | Image / build target | Purpose | Profile |
|---------|----------------------|---------|---------|
| `db` | `postgres:18-bookworm` | PostgreSQL 18 database | — |
| `migrate` | `docker/Dockerfile` (`prod`, `dev` in override) | One-shot Alembic migration | — |
| `app` | `docker/Dockerfile` (`${DOCKER_TARGET:-prod}`, `dev` in override) | FastAPI backend | — |
| `redis` | `redis:7.4-alpine` | Rate limiting, token revocation, RQ broker | — |
| `rq-worker` | `docker/Dockerfile` (`prod`) | Background processing: uploads, aggregation | — |
| `frontend` | `docker/Dockerfile.frontend.dev` | Vite dev server with HMR | — (override only) |
| `nginx` | `nginx:1.27-alpine` | Production reverse proxy | `production` |

The test project mirrors this with a `test-` prefix: `test-db`, `test-redis`,
`test-migrate`, `test-app`.

### Published Host Ports

Container-internal ports are fixed. Only the **host** side is
Compose-interpolated, so several checkouts can run side by side without editing
committed files.

| Service | Variable | Host default | Container port |
|---------|----------|--------------|----------------|
| `app` (dev) | `APP_HOST_PORT` | `8010` | `8000` |
| `frontend` (dev) | none — fixed | `5173` | `5173` |
| `db` (dev) | none — fixed | `5432`, bound to `127.0.0.1` | `5432` |
| `test-db` | `TEST_DB_HOST_PORT` | `5434` | `5432` |
| `test-redis` | `TEST_REDIS_HOST_PORT` | `6381` | `6379` |
| `test-app` | `TEST_APP_HOST_PORT` | `8001` | `8000` |

Because the internal ports never move, everything addressing a service over the
Compose network is unaffected by the host-port variables:
`frontend/vite.config.ts` proxies to `http://app:8000`, the `app` healthcheck
calls `http://localhost:8000/health`, and nginx proxies to `app:8000`.

The development database is bound to `127.0.0.1` deliberately. Do not change it
to `0.0.0.0` — that would expose PostgreSQL to the network.

### Volumes

| Compose key | Host volume (`mkobi` project) | Mount point | Scope |
|-------------|-------------------------------|-------------|-------|
| `postgres_data` | `mkobi_postgres_data` | `/var/lib/postgresql` (PG18+ requirement) | base |
| `app_data` | `mkobi_app_data` | `/app/data` | base |
| `redis_data` | `mkobi_redis_data` | `/data` | base |
| `frontend_vite_cache` | `mkobi_frontend_vite_cache` | `/app/node_modules/.vite` | dev override |

The test project owns `mkobi-test_test_postgres_data` and
`mkobi-test_test_redis_data`. `node_modules` is **not** a volume: the frontend
dev image installs it at build time, which is also what avoids the Windows
SIGBUS fault described under Troubleshooting.

### Networks

- `mkobi` project: `mkobi_default` (bridge)
- `mkobi-test` project: `test_network` (bridge), isolated from the dev stack

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+ — the `docker compose` v2 subcommand, not `docker-compose`
- PowerShell 7+ — `.\Makefile.ps1` refuses to run on Windows PowerShell 5.1
- uv — host-native Python work only

## Quick Start

`.\Makefile.ps1` wraps `docker compose` with the correct project name, file
list and `--env-file` for each stack. Run it from the repository root: relative
paths such as `--env-file .env` resolve against the current directory.

### Development

```powershell
# Start the dev stack and block until healthy
.\Makefile.ps1 up

# Stop the dev stack
.\Makefile.ps1 down
```

The raw invocations the task runner performs, for reference:

```bash
# Development stack: 6 services, no nginx
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml up -d

# Any command that mentions frontend must include the override file,
# because no profile makes it start
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml logs -f frontend
```

- Frontend dev server: <http://localhost:5173> (Vite, HMR)
- Backend API: <http://localhost:8010> on the host, container port `8000`.
  Override the host port with `APP_HOST_PORT` when `8010` is taken.

> **Note on `--env-file .env`:** a base-file-only `config` or
> `config --services` **requires** `--env-file .env`. The base compose still
> uses `${VAR:?}` for `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD`,
> `JWT__SECRET_KEY`, `ADMIN_USERNAME` and `ADMIN_PASSWORD`; without the env file
> interpolation aborts and no config is printed. Every `docker compose
> -f docker/docker-compose.yml` command needs the flag.

> **Note on Cookie Security:** the `AppSettings.cookie_secure` setting defaults
> to `true`, which requires HTTPS for cookies to be sent. Development runs over
> HTTP, so `docker-compose.override.yml` sets `APP__COOKIE_SECURE=false` to allow
> authentication cookies to work. Do not use `false` in production — the default
> is the secure value.

> **Note on the Development Entry Point:** the dev `app` on host port `8010`
> also serves the production React build, which uses secure cookies and
> memory-only token storage and therefore cannot authenticate over HTTP. **The
> intended entry point in development is <http://localhost:5173>**, the Vite dev
> server, which proxies `/api` to `http://app:8000` over the Docker network.

### Testing

Tests run in a separate Compose project, `mkobi-test`, with its own volumes and
network. Credentials there are hard-coded literals; only the ports are
interpolated, so ambient environment variables cannot leak into the stack.

```powershell
# Start test-db + test-redis and wait for them to be healthy
.\Makefile.ps1 test-up

# Run the full suite (default gate)
.\Makefile.ps1 test

# Full suite with the live coverage gate
.\Makefile.ps1 test-all

# Wipe the test volumes, recreate the schema, run the full suite
.\Makefile.ps1 test-fresh

# Forward arguments to pytest verbatim
.\Makefile.ps1 test-select -k some_test -v

# Stop the test stack
.\Makefile.ps1 test-down

# Destroy the test volumes and recreate a clean test database
.\Makefile.ps1 test-reset
```

Run `.\Makefile.ps1 help` for the full target list; that is the single source of
truth for the command surface, so it is not reproduced here.

Note that `test-migrate` is declared in the compose file but the runner never
starts it: the test targets bring up `test-db` and `test-redis` only and then
run pytest with `--no-deps`, because `tests/conftest.py` recreates and migrates
the test database itself (`setup_test_database`).

> **Test Port Security Note:** host ports are intentionally exposed so the
> suite can be run natively from a host terminal during development.
> - **Risk is LOW** — the test database holds no production data and uses
>   default test passwords.
> - **Shifted defaults** — `5434`, `6381`, `8001` avoid the ports a dev or
>   production stack already uses, so both can run at once.
> - **For shared machines:** consider binding to `127.0.0.1` instead of the
>   default `0.0.0.0` to prevent cross-talk between developers.
> - **For CI/CD:** run inside the container
>   (`docker compose -p mkobi-test -f docker/docker-compose.test.yml exec test-app uv run pytest`)
>   to avoid exposing ports at all.

### Production

```powershell
# Add the production reverse proxy on top of the base stack
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml --profile production up -d
```

The `production` profile adds exactly one service, `nginx`. `redis` and
`rq-worker` are not profile-gated and are already part of the base stack.

The `app` service build target is `${DOCKER_TARGET:-prod}`. Set
`DOCKER_TARGET` in the environment to build a different stage:

```bash
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml build --build-arg DOCKER_TARGET=prod
```

## Daily Operations

`.\Makefile.ps1` covers the daily loop. The equivalent raw commands are listed
for diagnosis; they carry the same project name, file list and `--env-file` the
runner uses.

| Task | Task runner | Raw command basis |
|------|-------------|-------------------|
| Start | `.\Makefile.ps1 up` | `up -d --wait` on the dev pair |
| Stop | `.\Makefile.ps1 down` | `down --remove-orphans` on the dev pair |
| Status | `.\Makefile.ps1 ps` | `ps` on the dev pair |
| Logs | `.\Makefile.ps1 logs [service]` | `logs -f --tail=200 [service]` |
| Shell | `.\Makefile.ps1 shell` | `run --rm --no-deps app bash` |
| Command in `app` | `.\Makefile.ps1 exec <cmd>` | `exec app <cmd>` |
| Rebuild | `.\Makefile.ps1 build` / `rebuild` | `build` / `build --no-cache` |

A few operations are intentionally not wrapped, because they destroy data or
print secrets. Run them deliberately:

```bash
# Remove dev volumes as well as containers
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.override.yml down -v

# Resolved configuration — prints interpolated secrets, do not paste it
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.override.yml config
```

`.\Makefile.ps1 clean`, `fullclean` and `nuke` cover the equivalent cleanup
across both projects; `fullclean` and `nuke` prompt before removing volumes and
are scoped to `mkobi` and `mkobi-test` only.

## Development Workflow

### Hot Reload

- **Backend:** uvicorn `--reload` with `--reload-exclude /app/tests/`. On
  Windows, Docker Desktop's gRPC-FUSE bind mounts deliver no inotify events, so
  the dev `app` service also sets `WATCHFILES_FORCE_POLLING=true` and
  `WATCHFILES_POLL_DELAY_MS=400`; without those, reload never fires.
- **Frontend:** Vite dev server with hot module replacement. The dev `frontend`
  service sets `CHOKIDAR_USEPOLLING` and `WATCHPACK_POLLING` for the same
  reason.

### Frontend Development

- Dev server: <http://localhost:5173>
- Proxies `/api` to the container address `http://app:8000`; the host port
  (`8010` by default) is irrelevant to the browser
- React 18 + TypeScript, TanStack Query
- `npm` lives in the frontend images only — see Docker Internals below

### Backend Development

- FastAPI with automatic reload
- PostgreSQL with hot reload support
- Shared `app_data` volume for temp files

### Cookie Configuration

`AppSettings.cookie_secure` controls cookie security:

- `true` (default) — requires HTTPS, use in production
- `false` — works over HTTP, set by the development override

## Testing

For the isolated test environment, its volumes, its network and the runner
targets, see [Quick Start](#quick-start). The essentials:

- Standalone compose, no merge with the dev or production stack
- Separate services (`test-db`, `test-redis`, `test-migrate`, `test-app`),
  volumes (`test_postgres_data`, `test_redis_data`) and network (`test_network`)
- Configurable host ports: `TEST_DB_HOST_PORT` (`5434`), `TEST_REDIS_HOST_PORT`
  (`6381`), `TEST_APP_HOST_PORT` (`8001`)
- Hard-coded credentials, so no ambient variable can change them
- No port or volume conflicts with the dev stack, because the two stacks are
  separate Compose projects

`tests/conftest.py` sets `os.environ.setdefault` for the database connection, so
Compose values win inside the container while native host runs keep working
defaults. The schema is created and migrated by `conftest`, not by
`test-migrate`.

## Production Deployment

### RQ Worker

Runs the Redis Queue worker for background task processing (CSV uploads, data
aggregation). It is part of the base stack, not a production-only service.

- **Command:** `/app/.venv/bin/rqworker --url redis://redis:6379/0`
- **Depends on:** `redis` (healthy), `migrate` (completed successfully)
- **Environment:** as `app`, plus `AUTO_MIGRATE: "false"` — migrations belong to
  the `migrate` service
- **Shares volume:** `app_data`, so it sees the same upload and temp files as
  the app
- **Mounts** `alembic/` and `alembic.ini` read-only, for migration rollback
- **Does not need `REDIS__HOST`/`REDIS__PORT`**: it receives its target from the
  explicit `--url` on the command line

> **Note:** the RQ worker is the production implementation of the task queue. The
> in-memory `asyncio.Queue` is used when it is not running. See
> [Task Queue Migration](./task-queue-migration.md) for the migration plan.

### Nginx Reverse Proxy

Optional production reverse proxy, and the only service gated by the
`production` profile. Serves the React SPA static files and proxies API requests
to FastAPI at `app:8000`.

- **Depends on:** `app`
- **Ports:** `80:80`
- **Volumes:** `docker/nginx/nginx.conf` (read-only), `frontend/dist` (read-only)
- **Requires a prior frontend build** — the dist directory is mounted, not built
- **Security hardening:**
  - `read_only: true` — immutable root filesystem
  - `tmpfs` for runtime-writable paths: `/tmp`, `/var/cache/nginx`, `/var/run`,
    `/var/log/nginx`
  - All volumes mounted read-only (`:ro`)
  - Healthcheck verifies an HTTP response, not just config syntax

> **Note on `no-new-privileges`:** the official `nginx` image uses `setuid`
> internally to drop from root to the `nginx` user, so
> `security_opt: no-new-privileges:true` would crash the container. For nginx,
> the read-only filesystem is the primary hardening control.

See [Deployment](../10-deployment/deployment.md) for the nginx configuration.

## Environment Configuration

### Which .env File to Use

| File | Purpose | Values |
|------|---------|--------|
| `.env` (repository root) | Development — ready to use | Working development values |
| `docker/.env.development` | Development template | `CHANGE_ME` placeholders — must be copied |
| `docker/.env.production` | Production deployment | Commented template — must be filled before deployment |

```bash
# Development with the root .env (no setup needed)
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml up -d

# Or with a copied template
cp docker/.env.development docker/.env    # then replace CHANGE_ME values
docker compose -p mkobi --env-file docker/.env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml up -d

# Production
docker compose --env-file docker/.env.production \
  -f docker/docker-compose.yml up -d
```

> **Note on Development Credentials:** in development, weak passwords are
> allowed for `ADMIN_USERNAME` and `ADMIN_PASSWORD`, and the default `.env`
> uses `admin@example.com` for both. This enables quick startup — **never use
> these in production**, where known-weak values are rejected.

### Required Variables

The base compose file uses `${VAR:?}`, so these must be present or Compose
aborts before it will print a config or start anything:

| Variable | Description |
|----------|-------------|
| `DATABASE__PASSWORD` | PostgreSQL superuser password |
| `MKOBI_APP_PASSWORD` | Application database role password |
| `JWT__SECRET_KEY` | JWT signing secret |
| `ADMIN_USERNAME` | Initial admin username (must be a valid email) |
| `ADMIN_PASSWORD` | Initial admin password |

The development override adds `DATABASE__ADMIN_PASSWORD` to the same list.

> **Security Note:** `${VAR:?}` enforces presence, not strength. For production
> deployments set strong, unique values for `DATABASE__PASSWORD`,
> `MKOBI_APP_PASSWORD` and `JWT__SECRET_KEY`; the application validates
> credential strength at startup when `ENV=production`.

### Key Variables

| Variable | Description |
|----------|-------------|
| `ENV` | Environment (`development` / `test` / `production`) |
| `DOCKER_TARGET` | Build target for `app` and `migrate` (default `prod`) |
| `DATABASE__HOST` | Database host |
| `LOGGING__LEVEL` | Logging level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `RECREATE_TEST_DB` | Recreate the test database on startup |
| `APP__COOKIE_SECURE` | Cookie `Secure` attribute. Defaults to `true`; the dev override sets `false` |
| `REDIS__HOST`, `REDIS__PORT` | Redis address. Must be `redis` inside a container, since the default `localhost` resolves to the container itself |
| `APP_HOST_PORT` | Host port for the dev `app` (default `8010`) |
| `TEST_DB_HOST_PORT`, `TEST_REDIS_HOST_PORT`, `TEST_APP_HOST_PORT` | Host ports for the test stack (defaults `5434`, `6381`, `8001`) |
| `CORS_ORIGINS` | Allowed origins. Defaults to `["http://localhost:5173"]` in the base file, `["http://localhost:3000"]` in the dev override |

## Docker Internals

### Multi-Stage Build Architecture

`docker/Dockerfile` defines the following stages:

| Stage | Description |
|-------|-------------|
| `frontend-builder` | Builds the React SPA (intermediate stage) |
| `base` | Common base with system dependencies |
| `prod-base` | Minimal runtime base for production |
| `dev` | Development environment with hot reload |
| `test` | Environment for running tests |
| `prod` (default) | Production image with multiple workers |

**base**
- Python 3.12-slim-bookworm
- System dependencies: `build-essential`, `libpq-dev`, `libmagic1`, `curl`
  - `libmagic1` is required for server-side MIME detection in the upload
    pipeline
- Installs uv, creates a non-root `app` user

**frontend-builder**
- Node 20 Alpine
- `npm ci` then `npm run build`; no BuildKit cache mount, so `node_modules`
  persists in the image layer
- Output: `frontend/dist/`

**dev**
- Extends `base`; installs all dependencies including dev
- Copies source for hot reload
- Runs with `--reload`

**test**
- Extends `base`; installs all dependencies including dev
- Copies tests and source, sets `ENV=test`
- Default command runs pytest

**prod-base**
- Python 3.12-slim-bookworm with runtime dependencies only: `libpq5`,
  `libmagic1`, `curl`
- No build tools — smaller attack surface

**prod** (default target)
- Extends **prod-base**
- Installs production dependencies only (`uv sync --no-dev`)
- Copies the frontend build artifacts from `frontend-builder`
- Runs with multiple workers (`--workers 4`)
- Includes a `HEALTHCHECK` directive (curl `/health`)

> **`npm` is not in the backend images.** It exists only in `frontend-builder`
> (a Node image) and in the separate `docker/Dockerfile.frontend.dev` used by
> the `frontend` service. The `app` container is a Python image, so a frontend
> build cannot be executed inside it. Build the bundle from the `frontend`
> service or on the host.

### Build Examples

```bash
# Build a specific target
docker build -f docker/Dockerfile --target dev -t mkobi:dev .
docker build -f docker/Dockerfile --target prod -t mkobi:prod .
docker build -f docker/Dockerfile --target test -t mkobi:test .

# Force a full rebuild
docker build -f docker/Dockerfile --no-cache --target prod -t mkobi:prod .
```

Layer caching is preserved by copying `pyproject.toml` and `uv.lock` before the
source tree, keeping the frontend build in its own stage, combining related
commands into few layers, and applying `docker/.dockerignore` to the build
context.

## Health Checks

| Service | Method | Notes |
|---------|--------|-------|
| `db` | `pg_isready -U postgres -d bidb` | |
| `app` | `curl -f http://localhost:8000/health` | `start_period: 40s`; **disabled in the dev override** |
| `redis` | `redis-cli ping` | |
| `rq-worker` | Python one-liner, `Redis(...).ping()` | **disabled in the dev override** |
| `nginx` | `wget --spider -q http://localhost/` | Verifies nginx is serving, not merely config-valid |

The dev override disables the `app` and `rq-worker` healthchecks for faster
startup, so `up --wait` in development does not gate on them.

## PostgreSQL Locale Configuration

PostgreSQL 18 uses the `builtin` locale provider with `C.UTF-8` collation,
configured via `POSTGRES_INITDB_ARGS`:

```yaml
POSTGRES_INITDB_ARGS: "--locale-provider=builtin --locale=C.UTF-8"
```

This provides:

- **Immutable collation version** (fixed at `1`) — no collation mismatch errors
  on image updates
- **Full UTF-8 support** for both Latin and Cyrillic characters
- **No index corruption risk** from OS locale changes

The `-bookworm` Debian tag is used for stability. When upgrading to `-trixie` in
the future, no collation refresh is needed — the builtin provider is immutable.

## Troubleshooting

### Database connection issues

```bash
# Is the database ready?
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml exec db pg_isready -U postgres

# Or, with the task runner:
.\Makefile.ps1 exec pg_isready -U postgres
```

Database logs: `.\Makefile.ps1 logs db`.

### Migration issues

```powershell
# Apply migrations
.\Makefile.ps1 migrate

# Show current vs head
.\Makefile.ps1 migration-status
```

### SIGBUS Error in the Frontend Container (Windows)

```
npm error signal SIGBUS
npm error command sh -c vite --host 0.0.0.0
```

**Root cause:** cross-OS filesystem incompatibility. Mounts from Windows NTFS to
Linux containers through gRPC FUSE or SMB layers cause memory-alignment issues
when Node.js/Vite accesses files.

**Fix already in place:** the `frontend` service builds from a dedicated image,
`docker/Dockerfile.frontend.dev`, which installs `node_modules` inside the image
at build time and mounts only individual source files for hot reload. Source
mounts are the problem, so a `node_modules` volume is not used.

If the symptom persists, clear the Vite cache volume:

```powershell
docker volume rm mkobi_frontend_vite_cache
```

### Frontend not loading

```bash
# Rebuild the frontend service — the only place a bundle can be built
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml up -d --build frontend

# Frontend container logs
docker compose -p mkobi --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml logs -f frontend

# Backend logs, if the API is what fails
.\Makefile.ps1 logs app
```

Remember that the base file alone does not define `frontend`; the override is
required.

### PostgreSQL 18 Collation Version Error

When starting PostgreSQL 18 containers you may see repeated log messages like:

```
ERROR:  syntax error at or near "COLLATION_VERSION"
LINE:  ALTER DATABASE template1 REFRESH COLLATION_VERSION
```

**Why this is harmless:** a known incompatibility between the Debian
`postgresql-common` package (used in the postgres image) and PostgreSQL 18's
stricter parser. `REFRESH COLLATION_VERSION` was valid in PG16/17, but
PostgreSQL 18 requires `REFRESH COLLATION VERSION`.

**Why it does not affect this project:** the `builtin` locale provider creates an
immutable collation version (always `1`), so this refresh is never needed. The
database starts and operates correctly despite the log lines. These messages
are cosmetic and require no action.

### "required variable X is missing a value" error

Compose cannot interpolate a variable the compose file requires with
`${VAR:?}`. Ensure you:

1. Have a `.env` file in the repository root
2. Pass `--env-file .env` with every base-file command — without it,
   `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD`, `JWT__SECRET_KEY`,
   `ADMIN_USERNAME` and `ADMIN_PASSWORD` are all missing and the command aborts
   before producing any output

This affects read-only commands too: a base-file `config` or `config --services`
without `--env-file .env` fails in exactly the same way.

## Security

1. **Non-root user:** the application runs as `app` (not root)
2. **Read-only filesystem:** `nginx` uses `read_only: true` with explicit `tmpfs`
   mounts (it uses `setuid` internally, so `security_opt` cannot be applied)
3. **No privilege escalation:** `app` uses `security_opt: no-new-privileges:true`,
   blocking `setuid`/`setgid` exploitation
4. **Minimal capabilities:** `app` drops all Linux capabilities via
   `cap_drop: ALL` — it binds port 8000, so no privileged port is needed
5. **Secrets:** use Docker secrets or environment variables; the script never
   mutates `COMPOSE_PROJECT_NAME`, which would leak into unrelated invocations
6. **`.env` is never committed** to version control
7. **Production:** change all default passwords and the JWT secret
8. **Image scanning:** `docker/scripts/scan-images.ps1` scans built images for
   CVEs

> **Important:** the dev override sets `read_only: false` on `app` and
> `rq-worker`, because both stream and process files under
> `/app/data/tmp_uploads` and share the `app_data` volume. Production keeps
> `read_only: true`.

### Volume vs tmpfs for Data Directories

`app_data` is used for `/app/data` rather than tmpfs mounts:

- **tmpfs limitation:** tmpfs directories are owned by root, and the
  application runs as `app` (uid 100, gid 101), which cannot write to them
- **Solution:** the `app_data` named volume inherits the ownership set in the
  Dockerfile (`chown -R app:app /app/data`)

## Performance Tips

1. **Use layer caching:** order Dockerfile commands from least to most frequently
   changing
2. **Multi-stage builds:** exclude build dependencies from the final image
3. **uv:** faster than pip for dependency installation
4. **`--no-dev`:** excludes development dependencies in production

## File Structure

```
.
├── .dockerignore                   # Build context file
├── .env                            # Environment variables (gitignored, required for --env-file)
├── .env.example                    # Template for .env
├── Makefile.ps1                    # Developer task runner (PowerShell 7+)
├── docker/
│   ├── docker-compose.yml            # Base compose: db, migrate, app, redis, rq-worker (+ nginx profile)
│   ├── docker-compose.override.yml   # Development overrides, incl. frontend
│   ├── docker-compose.test.yml       # Standalone test environment
│   ├── Dockerfile                    # Multi-stage backend build (+ frontend-builder)
│   ├── Dockerfile.frontend.dev       # Frontend dev image (avoids Windows SIGBUS)
│   ├── .dockerignore                 # Build context exclusions
│   ├── init-scripts/
│   │   └── 01-create-app-role.sh     # DB initialization (creates mkobi_app role)
│   ├── nginx/
│   │   └── nginx.conf                # Nginx configuration (production profile)
│   └── scripts/
│       └── scan-images.ps1           # Trivy vulnerability scanner for built images
└── frontend/
    ├── dist/                         # Built frontend (generated)
    └── ...
```

## Migration from Old Setup

If migrating from a single-stage Dockerfile:

1. Review the multi-stage `docker/Dockerfile`
2. Update the compose file to specify the build target
3. Test each environment (dev, test, production)
4. Update CI/CD pipelines to use the new targets

## Application Data Directories

### Temporary and Upload Folders

The application uses several directories for file processing, managed through
the `app_data` volume. This volume-based approach (instead of tmpfs) ensures
correct ownership for the non-root `app` user.

| Directory | Path (Docker) | Purpose | Lifecycle |
|-----------|---------------|---------|-----------|
| `tmp_uploads` | `/app/data/tmp_uploads` | Initial upload streaming, temp storage during processing | Auto-cleanup on success or failure; startup cleanup for stale files |
| `uploads` | `/app/data/uploads` | Potential permanent file storage | Manual or policy-based cleanup |
| `logs` | `/app/data/logs` | Application logs | Rotated, retention by `LOGS_RETENTION_DAYS` |

### Upload Temp Directory

- **Configuration:** `UPLOAD__TEMP_DIR` (defaults to a platformdirs path)
- **Used by:** `src/mkobi/api/routes/upload.py` for streaming uploads
- **Lifecycle:**
  1. Initial temp file created with prefix `upload_{uuid}` during streaming
  2. Renamed to `{log_id}.csv` or `{log_id}.csv.gz` when processing starts
  3. Deleted after processing completes (success or failure)
  4. Orphaned files (24h or older) cleaned on startup by
     `cleanup_stale_temp_files()`

### Cleanup Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `STALE_FILE_THRESHOLD_HOURS` | Age threshold for stale temp files | 24 |
| `LOGS_RETENTION_DAYS` | Log retention period | 30 |

See [Temp File Cleanup](../03-processing/file-cleanup.md) for the complete
cleanup architecture.

## Cross-References

- [Run Guide](../99-reference/run-guide.md) — complete application run
  instructions
- [Deployment](../10-deployment/deployment.md) — production deployment
  strategies
- [Task Queue Migration](./task-queue-migration.md) — background task processing
  setup
- [Temp File Cleanup](../03-processing/file-cleanup.md) — file cleanup
  architecture
- `.\Makefile.ps1 help` — authoritative list of task-runner targets

## Reference

### Docker Image Versions

| Service | Image | Version |
|---------|-------|---------|
| db / test-db | postgres | 18-bookworm |
| redis / test-redis | redis | 7.4-alpine |
| nginx | nginx | 1.27-alpine |
| frontend-builder / frontend | node | 20-alpine |

To update image versions, check Docker Hub for the latest tags and change them
in the compose files.

## License

MIT
