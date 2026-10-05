---
id: deployment
domain: deployment
tags:
  - deployment
  - docker
  - production
  - nginx
  - health-checks
  - migrations
  - dash-migration
  - rollback
related:
  - backend-architecture
  - configuration
  - health-api
  - security-overview
---

# Deployment

## Overview

This guide covers deployment options for the mkobi BI Dashboard system, from local development to production. The application consists of a FastAPI backend, React 18 frontend, PostgreSQL database, and optional Redis for task queues.

**Related documentation:**
- [Backend Architecture](../06-backend/architecture.md) — System architecture and layer responsibilities
- [Configuration](../06-backend/configuration.md) — Config sources, secrets, and environment variables
- [Security Overview](../08-security/security-overview.md) — Production credential enforcement
- [Health API](../05-health/health-api.md) — Health check endpoints for monitoring

---

## Development Deployment

### Prerequisites

- Python 3.12+
- Node.js 20+
- uv (Python package manager)
- PostgreSQL 18+ (local or Docker)

### Local Setup

1. **Clone and configure:**
    ```bash
    git clone <repository-url>
    cd mkobi
    cp .env.example .env
    # Edit .env with your local settings
    ```

2. **Backend:**
    ```bash
    uv sync
    uv run uvicorn src.mkobi.main:app --reload --port 8000
    ```

3. **Frontend (separate terminal):**
    ```bash
    cd frontend
    npm install
    npm run dev
    # Server runs at http://localhost:5173 (Vite default)
    ```

4. **Database:**
```bash
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d db
uv run alembic upgrade head
```

The base compose file requires **five** variables through `${VAR:?}` (`DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD`, `JWT__SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`), so every `docker compose` invocation against it **must pass `--env-file .env`**. Without the env file Compose aborts interpolation and starts nothing — not `db`, not `app`, not even a read-only `config`. The Makefile wraps this: its `DevCompose` argument list resolves to `-p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml`, so `.\Makefile.ps1 up` (and every other target) supplies the file for you. An explicit command line must supply it itself.

The React dev server runs on port 5173 (Vite) and proxies API requests to FastAPI (container port 8000; the dev overlay publishes the app on host port 8010 by default). Hot reload is enabled for both servers. CORS is configured to allow cross-origin requests between the dev servers.

### Environment Configuration

Development uses `.env` files for convenience (lowest priority in the config source hierarchy). See [Configuration](../06-backend/configuration.md) for the full priority chain.

---

## Production Deployment

### Production Principals

- **No overengineering:** Use proven, simple deployment patterns. The application does not require Kubernetes or complex orchestration for typical workloads.
- **Single responsibility:** Each container serves one purpose — app, database, or cache.
- **Security by default:** No default secrets, non-root containers, secrets via environment or Docker secrets.

### Option A — FastAPI Serves Static Files (Recommended)

FastAPI serves the built React static files directly. This is the simplest production deployment with a single entry point.

```
Client → FastAPI (port 8000)
            ├── /api/*    → REST API handlers
            ├── /static/ → React SPA build output (frontend/dist/)
            └── /         → React SPA index.html
```

**Steps:**

1. **Build frontend:**
    ```bash
    cd frontend
    npm run build
    # Output: frontend/dist/
    ```

2. **FastAPI configuration:**

    The backend mounts `frontend/dist/` as static files. All non-API routes fall through to the React `index.html` for client-side routing.

3. **Environment variables required:**
    ```
    ENV=production
    DATABASE__HOST=<production-db-host>
    DATABASE__PASSWORD=<strong-password>      # postgres superuser: db, migrate
    MKOBI_APP_PASSWORD=<strong-password>      # mkobi_app role: app, rq-worker
    JWT__SECRET_KEY=<random-256-bit-secret>
    CORS_ORIGINS=["https://app.example.org"]
    LOGGING__LEVEL=WARNING
    ```

    The two password names address **different roles**, and neither name says
    which: under the base compose file `DATABASE__PASSWORD` is the `postgres`
    superuser password (`db` and `migrate`), and `MKOBI_APP_PASSWORD` is the
    least-privilege `mkobi_app` password, which Compose maps onto
    `DATABASE__PASSWORD` for `app` and `rq-worker`. Outside Compose there is no
    second name — `DATABASE__PASSWORD` is simply the password for whichever
    role `DATABASE__USER` names. See
    [Required Production Variables](#required-production-variables).

    `https://your-domain.com` is one of the four **placeholder origins** the production
    tier refuses, so setting it aborts startup instead of producing a permissive
    policy. Replace it with your real domain(s). The refused set, and why the refusal
    also surfaces on `migrate` and `rq-worker`, which serve no HTTP, is documented in
    [Security Checklist](security-checklist.md#required-production-variables) and
    [Docker Guide](../11-guides/docker.md#cors_origins-is-required-in-practice).

### Option B — Nginx Reverse Proxy

Nginx proxies API requests to FastAPI and serves the React SPA static files. This adds a layer of control (SSL termination, caching, load balancing) at the cost of additional complexity.

```
Client → Nginx (port 80/443)
            ├── /api/*  → FastAPI (port 8000)
            └── /*      → React SPA static (frontend/dist/)
```

**nginx.conf snippet:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

To enable, start the nginx service from `docker-compose.yml`:
```bash
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml --profile production up -d
```

The `nginx` service is the production edge. Its client bundle **ships inside the
image**: the service builds the `frontend-nginx` stage of `docker/Dockerfile`,
which copies the SPA out of the same `frontend-builder` stage the app image
uses, into `/usr/share/nginx/html`. There is no host `../frontend/dist` bind
mount — that directory is git-ignored twice (`frontend/.gitignore` and a root
`dist/` rule) and unversioned, so it was never a sound production carrier. What
the edge serves is therefore determined by the image build, not by whatever
happens to be on the host. See [B6](#the-client-bundle-ships-inside-the-edge-image).

### Where the API-documentation surface is protected in production

The production control for the documentation surface is **nginx's `location`
set, not the application**. The `location /api/` block proxies the API and the
two health paths are routed explicitly; `/docs`, `/redoc` and `/openapi.json`
are **not** among the proxied paths, so they fall through to `location /` and
the React SPA is returned for them. Nginx therefore never asks the application
for those paths.

The application additionally sets `docs_url`, `redoc_url` and `openapi_url` to
`None` when `ENV=production` (`src/mkobi/app.py::create_app`), so if the
application is ever reached directly — outside the shipped nginx topology — all
three document URLs return `404` rather than serving the schema. That is
**defence in depth only**: in the deployed topology it is nginx that keeps the
schema surface unreachable, and the application gate changes nothing an external
caller can observe. The unreachable-path seam (nginx declares no `location` for
these paths) is tracked as hand-over `HO-4`, owned by phase 12 for the
`nginx.conf` file and phase 10 for the deployed composition.

**This is scoped to the documentation surface, not to every URL nginx does not
name.** Where a path *is* proxied (`location /api/`), nginx applies no rewriting
of its own, so the application's behaviour is the control there. The four
collection paths are the case in point: nginx proxies them unchanged, and the
application's `redirect_slashes=False` (`app.py::create_app`) is what makes a
no-slash request answer `404` instead of an anonymous `307`. That flag is the
control for those paths, not defence in depth — see
[Swagger UI Guide](../99-reference/swagger.md#collection-paths).

---

## Docker Deployment

The project uses a multi-stage Dockerfile supporting dev, test, and prod targets. See [Docker Guide](../11-guides/docker.md) for the full Docker specification.

### Quick Start

Every command below passes `--env-file .env`, because the base compose file
requires five variables through `${VAR:?}` and aborts interpolation without
them. `.env` is **not** committed; create it from `.env.example` and fill the
five names (see [Required Production Variables](#required-production-variables)).

```bash
# Production (default target)
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml up -d

# Production with nginx (production profile; rq-worker starts either way)
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml --profile production up -d

# Development with hot reload and frontend dev server
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d
```

The Makefile targets (`.\Makefile.ps1 up`, `down`, `logs`, `psql`, …) already
pass `--env-file .env` and both `-f` files; an explicit command line must repeat
them. Production additionally reads its own values from a production env file —
copy `docker/.env.production` and fill it, then pass `--env-file
docker/.env.production` instead.

**Note:** Development mode includes the frontend service running on port 5173 (Vite dev server with hot reload). Access the application at http://localhost:5173.

### Dockerfile Targets

| Target | Base | Dependencies | Workers | Use Case |
|--------|------|-------------|---------|----------|
| `base` | python:3.12-slim-bookworm | System + build tools | — | Shared base for dev/test |
| `prod-base` | python:3.12-slim-bookworm | Runtime only (libpq5, libmagic1) | — | Minimal base for prod |
| `dev` | base | All (incl. dev) | 1 (--reload) | Local dev |
| `test` | base | All (incl. dev) | 1 (pytest) | CI/CD |
| `prod` | prod-base | Production only | 4 | Production |
| `frontend-nginx` | nginx:1.27-alpine | The built SPA only | — | Production edge (see [The client bundle ships inside the edge image](#the-client-bundle-ships-inside-the-edge-image)) |

### The client bundle ships inside the edge image

The production edge serves its client bundle **from the image, not from the
host**. `docker/Dockerfile`'s `frontend-nginx` stage is `FROM` the same pinned
`nginx:1.27-alpine` digest the compose file used and copies the SPA out of the
`frontend-builder` stage into `/usr/share/nginx/html`; the `nginx` service builds
that stage and declares `image: mkobi/nginx:${IMAGE_TAG:-local}`. The host
`../frontend/dist` bind mount is **gone**: that directory is git-ignored twice
(`frontend/.gitignore`, and a root `dist/` rule that matches at any depth) and
is never committed, so it was never a versioned carrier. A failed frontend build
leaves no `index.html`, and the stage's `RUN test -f …/index.html` aborts the
image rather than shipping an empty bundle.

The application-side static mount (`src/mkobi/app.py::resolve_frontend_bundle`)
is **kept**, but it is not the production edge path. It serves the SPA app-side
when the configured `FRONTEND__DIST_DIR` exists and carries an `index.html`, for
the dev tier and for the single-entry Option A deployment this guide documents.
In the shipped production topology nginx proxies only `/api` and the health
paths to the app and serves `/` from the image, so the app-side mount is never
consulted for the SPA there.

### Production Profiles

`nginx` is the **only** service gated by `profiles: [production]`. It is not started by
default; pass `--profile production` to include it:

- **nginx** — Reverse proxy serving React SPA (from its own image) and proxying API requests to FastAPI.

`redis` and `rq-worker` are **not** profile-gated. They start with the base file whether
or not a profile is passed:

- **rq-worker** — Redis Queue worker for background task processing. Runs `/app/.venv/bin/python -m mkobi.rq_worker_wrapper` — the wrapper module invoked through the virtualenv interpreter directly. The retired `rqworker` console script does **not** exist in the current manifest (`pyproject.toml` declares no such entry point), so any row naming `/app/.venv/bin/rqworker` describes a symbol that is not installed. Shares `app_data` volume with the app service.

See [Docker Guide](../11-guides/docker.md#rq-worker) for its dependencies, environment and mounts.

### Start Order and Readiness

Services are started in a fixed order, and every edge names a *condition*
rather than a mere "container started":

```
db (healthy)
  └─> migrate (service_completed_successfully)
        └─> app (with redis healthy)
              └─> nginx (service_healthy, production profile only)
```

| Order | Service | Waits for | Condition |
| --- | --- | --- | --- |
| 1 | `db` | — | `pg_isready` healthcheck |
| 2 | `migrate` | `db` | `service_healthy` |
| 3 | `app` | `migrate`, `db`, `redis` | `service_completed_successfully`, `service_healthy`, `service_healthy` |
| 4 | `nginx` | `app` | `service_healthy` |

Two of these edges are load-bearing and should not be relaxed:

- **`nginx` waits on the application's health.** It used to declare only
  `depends_on: [app]`, so the reverse proxy could begin serving while the
  application was still booting. It is now keyed on
  `app: {condition: service_healthy}`, gated by the app healthcheck
  (`curl -f http://localhost:8000/health`, which performs a real database
  round-trip). An operator now sees an absent proxy at startup rather than a
  `502` at request time — the failure is meant to happen once, during deploy,
  not on every request afterwards.
- **`app` waits on `redis` for startup ordering only.** The stale-processing
  reconciler lease fails open: the application boots and sweeps even when Redis
  is unreachable. The wait exists so the app does not spend the first seconds of
  a slow Redis boot in the fail-open state; it is not a correctness dependency,
  and removing it would not break the sweep.

The development tier has the same readiness signal. The development override no
longer disables the `app` healthcheck, so `docker compose ... up -d --wait` —
which is what `.\Makefile.ps1 up` runs — returns only after `/health` answers.
`up` is consequently slower than it used to be and now fails loudly on a
half-started stack instead of returning early.

See [Docker Guide](../11-guides/docker.md#readiness-and-start-order) for the
Compose-level view, including the development-specific differences.

### Test Environment Port Configuration

The standalone test Docker Compose (`docker/docker-compose.test.yml`) uses shifted, **configurable** host ports to enable parallel dev+test execution and parallel checkouts on one machine:

| Service | Host Port (default) | Env override | Container Port |
|---------|---------------------|--------------|----------------|
| `test-db` | **5434** | `TEST_DB_HOST_PORT` | 5432 |
| `test-redis` | **6381** | `TEST_REDIS_HOST_PORT` | 6379 |
| `test-app` | **8001** | `TEST_APP_HOST_PORT` | 8000 |

The dev app service (`docker-compose.override.yml`) similarly publishes `${APP_HOST_PORT:-8010}` to container port 8000.

Ports are bound to `0.0.0.0` (Docker default). Security risk is **LOW** — the test database contains no production data and uses default test passwords.

**Rationale:** Native test execution from the host terminal is a documented workflow. Running `pytest` directly (not via `docker compose exec`) is faster for iterative development. The shifted ports enable running dev and test environments simultaneously without conflicts. Ports only are interpolated from the environment — all test credentials remain literal literals in the compose file, so ambient environment variables cannot leak into the test stack.

`tests/conftest.py` uses `os.environ.setdefault("DATABASE__PORT", "5434")` to support both workflows:
- Inside Docker: environment variables set by Docker Compose (port 5432 internal)
- From host: defaults to `localhost:5434` for direct pytest execution

> **Security note:** On shared machines, consider binding to `127.0.0.1` instead of the default `0.0.0.0` to prevent cross-talk between developers. For CI/CD environments, running tests inside the container (`.\Makefile.ps1 test`) avoids exposing ports entirely.

### Required Production Variables

The base compose file requires these names through `${VAR:?}`, so Compose aborts
interpolation when any one of them is absent and **nothing starts** — not `db`, not
`app`, and not even a read-only `config` invocation. There are **five**, not two:

| Variable | Description |
| --- | --- |
| `DATABASE__PASSWORD` | PostgreSQL **superuser** password, used by `db` and `migrate` |
| `MKOBI_APP_PASSWORD` | Password of the least-privilege application role (`mkobi_app`), mapped onto `DATABASE__PASSWORD` for `app` and `rq-worker` |
| `JWT__SECRET_KEY` | JWT signing secret |
| `ADMIN_USERNAME` | Initial admin username (must be a valid email) |
| `ADMIN_PASSWORD` | Initial admin password |

```
DATABASE__PASSWORD=<production-password>
MKOBI_APP_PASSWORD=<app-role-password>
JWT__SECRET_KEY=<production-secret>
ADMIN_USERNAME=admin@your-domain.com
ADMIN_PASSWORD=<production-password>
```

`${VAR:?}` enforces presence only, not strength — credential strength is checked by the
application at startup and refuses weak, placeholder and empty values in the production
tier. See [Security Checklist](security-checklist.md#required-production-variables) for
the per-variable detail and the names that carry a default but are still required in
practice.

### Trusted Proxy Addresses (`FORWARDED_ALLOW_IPS`)

Rate limiting keys on the client IP that uvicorn puts in the ASGI scope. In production
only `nginx` publishes a port and proxies to `app:8000`, so without a trusted-proxy
declaration every external request arrives with the nginx container's address and the
entire internet shares one `login:` bucket.

The base compose file sets, on the `app` service:

```yaml
FORWARDED_ALLOW_IPS: "${FORWARDED_ALLOW_IPS:-172.21.0.0/16}"
```

uvicorn's `ProxyHeadersMiddleware` consults `X-Forwarded-For` only when the direct peer
is in this trusted set; when it is, uvicorn walks the forwarded chain in reverse and
returns the first host **not** in the set — the correct, non-attacker-controlled
behaviour. The value is passed via the environment (not a `CMD` argument), so it is
tier-scoped in compose and overridable without an image rebuild.

- The value **must be the compose network's subnet**. The default
  `172.21.0.0/16` is the subnet the `mkobi_default` network uses on the reference host
  — a documented, overridable default, not a constant.
- The `docker-compose.override.yml` development tier sets `FORWARDED_ALLOW_IPS:
  "127.0.0.1"`, i.e. trust nothing: no dev ingress path sets a forwarding header.
- **A mismatched value fails safe.** If the value does not match the host's actual
  subnet, no peer is trusted, `X-Forwarded-For` is never consulted, and behaviour
  degrades to the single-bucket state — no bypass. There is **no diagnostic signal**:
  uvicorn's `proxy_headers` module does not log, so a mismatch produces zero output.
- **Never set this to `*`.** Wildcard trust returns the left-most,
  fully client-controlled forwarded entry with no untrusted-hop walk, converting this
  availability defect into a brute-force bypass at internet scale.

### Database Migrations

- `AUTO_MIGRATE` — **off by default**, and off everywhere in the shipped Compose files. The `auto_migrate` setting is `false` in `src/mkobi/settings/app.yaml` and in the `Settings` field, and `AUTO_MIGRATE=true` makes the **application process** run `alembic upgrade head` during startup (`DatabaseStarter.startup`). It therefore takes effect only where a process actually receives the variable, and in the base compose file none does: `app` is not given `AUTO_MIGRATE` at all, and `rq-worker` receives a literal `AUTO_MIGRATE: "false"`. Setting `AUTO_MIGRATE=true` in an env file changes nothing — use the `migrate` service below.
- **Migration advisory lock** — In multi-instance deployments (K8s replicas, multiple Gunicorn workers), parallel migrations can corrupt the schema. The lock is taken in `alembic/env.py` (not by `_apply_migrations()`): a session-scoped `pg_try_advisory_lock` with a **bounded** retry of 30 attempts at 10 s, and **every refusal is logged**. A lock that cannot be acquired within that window **stops the migration** — the process exits non-zero rather than proceeding without exclusion. The lock is released after completion, even on failure.
- **Migration job pattern** — For production Docker Compose deployments, a dedicated `migrate` service runs `alembic upgrade head` before the app service starts. The app service depends on the migration service completing successfully (`depends_on: migrate: condition: service_completed_successfully`). This separates migration concerns from application startup and allows `AUTO_MIGRATE=false` in the app config.
- **Schema drift check** — `.\Makefile.ps1 migration-check` runs `alembic check` as a one-shot inside the hermetic test compose (`docker compose -p mkobi-test -f docker/docker-compose.test.yml run --rm test-migrate alembic check`), against `bidb_test`. It reports "No new upgrade operations detected." when the model layer and the migrated database agree, and exits non-zero with the differing operations when they do not. Three properties of the check are load-bearing and easy to misread: it **can only be trusted against an already-migrated database** (with no version table present, `alembic check` creates `alembic_version` itself and then falsely reports no drift); it **also takes the migration advisory lock**, because `alembic check` runs `env.py` online, so a blocked run fails with *"refusing to migrate"* — a lock verdict, not a drift verdict; and the target is deliberately bound to `bidb_test` because a bare host `alembic check` resolves through `alembic.ini`'s commented-out `sqlalchemy.url` to the app config's `DATABASE_URL`, i.e. the shared dev database (`bidb` on `localhost:5432`). Two drift classes are **not** detected and must be checked by hand: a changed server default (`compare_server_default` is never enabled) and a changed native-enum label (Alembic has no enum comparator; `DashboardAccess.permission`'s `dashboard_permission_level` enum is the concrete blind spot). `alembic check` must **never** be added to the one-shot `migrate` service, which has to remain able to run against a drifted database in order to repair it.
- Manual migration:
```bash
# The prod image runs as the non-root `app` user, for which `uv` is not
# executable (uv is installed under /root/.local/bin and `app` cannot read it:
# `uv run` fails with `uv: Permission denied`). Invoke the venv binary directly.
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /app/.venv/bin/alembic upgrade head
# Check status:
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /app/.venv/bin/alembic current
```

### Database Role (Least-Privilege)

The application uses a dedicated database role (`mkobi_app`) with limited privileges instead of the superuser `postgres` role:

| Role | Purpose | Privileges |
| --- | --- | --- |
| `postgres` | Migrations (DDL) | Superuser |
| `mkobi_app` | Runtime operations | `CONNECT`, `SELECT`, `INSERT`, `UPDATE`, `DELETE` on tables; `USAGE` on sequences |

This follows the least-privilege principle: any SQL injection or application bug is limited to the `mkobi_app` role's permissions and cannot execute superuser operations. The `postgres` role is used only for migrations that require DDL.

The role is created via an initialization SQL script mounted to `/docker-entrypoint-initdb.d/` in the PostgreSQL container. The application's `DATABASE__USER` and `DATABASE__PASSWORD` point to the `mkobi_app` role.

The role definition and all of its grants live in **one referenced artefact**: `docker/init-scripts/shared/app-role-grants.sql`. The init script `docker/init-scripts/01-create-app-role.sh` only supplies the psql variables (`app_password`, `dbname`) and loads it, so the artefact is the single definition and the two cannot drift. The artefact is idempotent: it creates the role only when absent and re-applies credentials and grants on every run.

The schema-level privilege in that artefact is `USAGE` on schema `public`. The test-tier recreation path (`src/mkobi/db/starter.py::recreate_test_database`) grants `USAGE, CREATE` instead. **This difference is deliberate and per-tier**, not drift: the persistent database's migrations run as the `postgres` superuser, which owns every object, so the application role never needs `CREATE` there, while the ephemeral test tier builds its schema under conditions that allow it. The rationale is recorded in the artefact's header. Do not harmonise the two.

Roles are **cluster-global, not part of a database dump**. A `pg_dump` of `bidb` does not contain `mkobi_app`, and `pg_restore` of that dump will not recreate it. When restoring onto a fresh cluster, the role must be created and granted first — the backup workflow exports cluster globals separately (see `Makefile.ps1`'s `Export-ClusterGlobals`/`Invoke-Load-Globals`) and loads them after the restore's drop phase.

If a restore reports **failed grants** (`role "mkobi_app" does not exist`, or `GRANT ... TO mkobi_app` errors), the role was absent when the grants ran. The remedy is to load the referenced artefact against the restored database, then re-run the grants:

```bash
psql -v ON_ERROR_STOP=1 \
     -v app_password="$MKOBI_APP_PASSWORD" \
     -v dbname=bidb \
     --username "$POSTGRES_USER" --dbname bidb \
     --file docker/init-scripts/shared/app-role-grants.sql
```

Roles are never created by an Alembic migration: a per-database migration cannot describe a cluster-global object, and a role created by a migration would break the per-environment grant model. No `GRANT`, `REVOKE`, `CREATE ROLE` or `ALTER DEFAULT PRIVILEGES` appears under `alembic/`.

### PostgreSQL Locale Configuration

The PostgreSQL container uses the `builtin` locale provider with `C.UTF-8` collation:

```yaml
POSTGRES_INITDB_ARGS: "--locale-provider=builtin --locale=C.UTF-8"
```

The builtin provider gives an **immutable collation version** (fixed at `1`), eliminating collation mismatch errors that occur with the default `libc` provider when the Docker image's base OS changes. `C.UTF-8` supports both Latin and Cyrillic characters.

This is configured in both `docker/docker-compose.yml` and `docker/docker-compose.test.yml`.

### Volumes

| Volume | Container Path | Purpose | Backup | Retention | Budget |
|--------|---------------|---------|--------|-----------|--------|
| `postgres_data` | `/var/lib/postgresql` | Database persistence | Yes — `pg_dump` + cluster globals, **daily** (`.\Makefile.ps1 backup`) | per `prune-backups` (7 days) | bounded by the database, not the 50 GB artefact budget |
| `app_data` | `/app/data` | Uploads, logs, temp files | No (scratch; see the note below) | temp files **24 h**; processing logs **90 days** | **50 GB** artefact-and-log budget, a **declared** ceiling — nothing currently admits against it; see [Artefact and log volume budget](#artefact-and-log-volume-budget) |
| `redis_data` | `/data` | Task queue + reconciler lease | Yes — `BGSAVE` snapshot `bidb-<stamp>.redis.rdb` (`.\Makefile.ps1 backup`) | per `prune-backups` (7 days) | small; RQ registries and the lease marker |

`app_data` holds **two** classes with different lifecycles and **no** backup:
uploads are scratch — `process_csv` unlinks the accepted artefact once the job
reaches a terminal state, and a hard kill leaves it to the stale-age sweep
(`STALE_FILE_THRESHOLD_HOURS`, default 24 h) — so they are not a backup target.
Processing logs are retained 90 days. The `postgres_data` and `redis_data`
volumes are the durability targets; the [Backup and Restore](#backup-and-restore)
section below describes the paired artefacts and the rehearsed restore.

### Backup and Restore

A restore needs **three** artefacts from one run, sharing a single timestamp
stamp: the database dump (`bidb-<stamp>.dump`), the cluster globals
(`bidb-<stamp>.globals.sql`) and the Redis snapshot (`bidb-<stamp>.redis.rdb`).
`.\Makefile.ps1 backup` emits all three. Cluster globals are separate because a
`pg_dump` of `bidb` does not contain the `mkobi_app` role (roles are
cluster-global) — see [Database Role](#database-role-least-privilege).

**RPO 24 h · RTO 4 h, daily backups.** The recovery-point objective is 24 hours
because backups run daily; the recovery-time objective is 4 hours. These are the
ruled figures (`DP-10-13`), not observations.

**The acceptance gate is a rehearsed restore against a scratch database, and it
has been executed.** `.\Makefile.ps1 rehearse-restore yes` sources a fresh dump
and its paired globals from the hermetic test cluster, creates a uniquely-named
throwaway database on that cluster, restores the paired artefacts into it in the
documented order (`pg_restore --clean` first, then cluster globals), reads
`alembic_version` **from the restored database**, and drops the scratch database
on every exit path. It never reads or writes the dev database `bidb` and never
restores into a `bidb_test*` database. It was run against this tree and passed:
the restored `alembic_version` was read back and the scratch database was
dropped. RPO is not exercised by the rehearsal (it is a policy, not a
mechanism); RTO's restore path is.

Cross-tier restore order is **Redis first, then the database**: the reconciler
lease and the RQ queue live in Redis, so restoring the database against a stale
store is the worse failure. The Redis restore (`.\Makefile.ps1 restore-redis yes
<file.redis.rdb>`) refuses while `redis` runs, because an RDB is loaded only at
startup.

### Artefact and log volume budget

The `app_data` artefact-and-log volume carries a **50 GB** budget. It is a
**declared ceiling**: **nothing currently admits against it** (see the enforcement
note below). Retention is **temporary files 24 hours** and **processing logs
90 days** (the `logs_retention_days` setting). The figure is ruled (`DP-10-7` /
`DP-11-H`, Product Owner, 2026-10-03); this is the derivation it is bound to,
published beside it:

- **Processing logs (90-day retention, the dominant reclaimed term).** The log
  ceiling is expressed as rotating **file** handlers only when an operator
  explicitly sets `LOGGING__LOG_FILE`; no compose service does so by default, so
  the **default deployment installs zero rotating file handlers** and this term
  is **0 MB**. In the conditional case where an operator sets
  `LOGGING__LOG_FILE` under `--workers 4`, four rotating handlers of 6 files ×
  10 MB ≈ **240 MB live** is the ceiling, and at 90 days the retained log set is
  bounded by that rotating ceiling plus the database-side `processing_logs`
  rows, not by the raw stream.
- **Upload scratch (24-hour retention).** Uploads are admitted at up to
  `UPLOAD__MAX_FILE_SIZE_MB` (100 MiB default) and removed at a terminal job
  state or by the 24-hour stale sweep; the live set is bounded by the 24-hour
  horizon times the observed accept rate.
- **Loader expansion.** A `.csv.gz` that passes the compressed-size check
  expands **5.14× in frame memory** and **14.6–15.2× in peak RSS** relative to
  its on-disk (compressed) size (measured; see
  `docs/06-backend/architecture.md`), but that is **residency**, not
  `app_data` bytes — the compressed artefact is what sits on the volume until
  the job terminalises it. The expansion bounds the worker's 512 MiB ceiling,
  not the disk budget.
- **Headroom.** The 50 GB figure is a conservative ceiling with headroom above
  the sum of the retained terms as configured today. It is a **declared**
  ceiling, not an accounting balance: **nothing currently admits against it**, so
  an operator sizing this volume must not treat it as admission-bounded.

**Corrected arithmetic.** The original derivation added an unconditional 240 MB
for four rotating handlers. The shipped configuration installs none, so the
default-case terms are: processing logs **0 MB** + upload scratch (24-hour horizon
× accept rate) + headroom. The 240 MB term applies **only** in the conditional
`LOGGING__LOG_FILE` case; even then it is 0.24 GB against a 50 GB budget, so the
default-vs-conditional difference does not move the published figure — it moves
the derivation. The 50 GB ruling stands either way.

The budget is a ruling revised only if this derivation contradicts it; today it
does not. **Nothing currently enforces the ceiling.** There is no `disk_usage`,
`statvfs`, `free_space`, `budget_bytes` or `MAX_VOLUME` check anywhere in
`src/mkobi`: the budget is **declared**, not enforced. The check that would
close the gap — a pre-accept byte check expressed against the resolved upload
directory — is phase 06's `FAB-5`; this section owns the **budget** figure and
its derivation, per the ceiling-versus-budget separation (`C11-7`).

### Capacity Register

One place that carries the deployment's capacity figures and where each is
sourced. Every entry names its source; ceilings are **referenced** from Backend
Architecture rather than restated, so the register cannot drift from them.

| Figure | Value | Source |
| --- | --- | --- |
| Connection budget | `4 × 30 = 120` reachable `125`; `210` unconstrained ceiling | **By reference** — [Connection-Pool Budget](../06-backend/architecture.md#connection-pool-budget) (owns the engine census). The store's `max_connections` is configured nowhere; record in [Store Connection Ceiling](../06-backend/architecture.md#store-connection-ceiling-prf-9) |
| Loader ceiling (memory) | `.csv.gz` peak ~192–195 MB at 400,000 × 6; worker ceiling 512 MiB | [Loader Memory Ceiling](../06-backend/architecture.md#loader-memory-ceiling-and-csvgz-expansion-prf-8) (`PRF-8`) |
| Worker ceiling | one replica, 512 MiB / 0.5 CPU; no job timeout / result TTL / burst; throughput unbounded | [Worker Topology](../06-backend/architecture.md#worker-topology-and-throughput-ceiling-prf-7) (`PRF-7`) |
| Artefact-and-log budget | **50 GB**, a **declared** ceiling — nothing admits against it; retention temp files **24 h**, processing logs **90 days** | [Artefact and log volume budget](#artefact-and-log-volume-budget) above (`PRF-11` derivation beside it) |
| Database durability | RPO **24 h** / RTO **4 h**, daily backups; rehearsed restore is the gate | [Backup and Restore](#backup-and-restore) above |

**Per-tier memory and CPU limits** (`deploy.resources`, from
`docker/docker-compose.yml`):

| Service | Memory limit | CPU limit | Memory reservation |
| --- | --- | --- | --- |
| `db` | 1 GiB | 1.0 | 512 MiB |
| `app` | 1 GiB | 1.0 | 512 MiB |
| `rq-worker` | 512 MiB | 0.5 | 256 MiB |
| `redis` | 256 MiB | 0.5 | 128 MiB |
| `nginx` | 128 MiB | — | 64 MiB |

`migrate` declares no `deploy.resources` limits (it is a one-shot job). The
`db` service's 1 GiB / 1.0 CPU limit is stated here because it is the service
holding the largest index and is named by no other document.

**Instrumentation gap (filed, not built).** There is an objective — observing
queue depth, pool utilisation and per-tier memory headroom — that **nothing
measures**: a search for prometheus, OpenTelemetry, Sentry, StatsD, Datadog,
py-spy, cProfile or memory_profiler across `pyproject.toml` and `src/mkobi/**`
returns no match. The deployment therefore has **no exported metrics series**;
every figure above is a measured-at-a-point value or a configured limit, not a
live signal. **What would close it:** an exporter that publishes, at minimum, the
RQ queue depth (`rq:queue:default`) and worker registration count as a scraped
series — which is also what would make the queue-depth alert (currently reading
zero, see [Monitoring gaps](#monitoring-gaps)) real. Building that
instrumentation is the operations layer's work and is **not done here**: the gap
is filed so the flat-zero alert is never mistaken for an idle queue.

### Health Checks

- **db**: `pg_isready` — verifies PostgreSQL is accepting connections
- **app**: HTTP GET `/health` — verifies the application responds; this is the
  readiness gate `nginx` starts behind (see [Start Order and
  Readiness](#start-order-and-readiness))
- **redis**: `redis-cli ping` — verifies Redis availability

The detailed component breakdown, including the reconciler-lease component on
`/health/detailed` and the reason `/health` is deliberately left narrow, is in
[Health API](../05-health/health-api.md).

### Monitoring gaps

**The queue-depth alert reads zero, and that is a known gap, not a healthy
signal.** No component emits a queue-depth metric: a search for prometheus,
OpenTelemetry, Sentry, StatsD or any metrics exporter across `pyproject.toml`
and `src/mkobi/**` returns no match, so the RQ queue depth (`rq:queue:default`)
is observable only by connecting to Redis by hand, not by any exported series.
An alert wired to that absent series evaluates against a constant zero — it is
flat regardless of the real depth — so a **zero reading must never be read as an
idle queue**. The gap is filed for the operations layer; closing it requires an
exporter that publishes the queue depth (and the worker registration count) as a
scraped series. Building such instrumentation is not this deployment's job, and
none is shipped in this tree.

The worker's own registry liveness **is** observable: the `rq-worker` healthcheck
reads the RQ worker registry and the `last_heartbeat` age rather than pinging
Redis, so a dead, wedged or still-retrying worker is reported unhealthy.

### Common Operations

```bash
# View logs
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml logs -f app

# Open shell
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /bin/bash

# Run tests (the test image runs as the non-root app user, for whom `uv` is not
# executable; call the venv binary directly, as the Makefile's test targets do)
docker compose -p mkobi-test -f docker/docker-compose.test.yml exec test-app /app/.venv/bin/pytest tests/ -v

# Stop and remove everything (including volumes)
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml down -v

# Rebuild after code changes
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml up -d --build
```

---

## Rollback Procedures

When a deployment fails or introduces critical bugs, use these procedures to safely roll back to a previous stable state.

### Docker Image Rollback

The image coordinate is a real tag, not a floating `latest`: the base compose
file names `mkobi/app:${IMAGE_TAG:-local}` (and `mkobi/migrate`, `mkobi/rq-worker`,
`mkobi/nginx` likewise), and a build tags the service with exactly that string.
The repository is the **local image store** — nothing is pushed to a registry —
so a rollback selects a previously built local tag by setting `IMAGE_TAG` in the
env file. It is **not** a `docker pull`: there is no registry to pull from.

```bash
# List locally-built application images and their tags
docker images mkobi/app

# Select a previously built tag (a real tag, never :latest) by editing
# IMAGE_TAG in .env, then recreate the services at that coordinate
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml up -d
```

`IMAGE_TAG` is read by `migrate`, `app`, `rq-worker` and `nginx` alike, so one
value moves the whole deployment to an earlier build. `:latest` is deliberately
never used: it is not a selectable rollback target.

### Database Migration Rollback

Use Alembic to revert schema changes. **Warning:** Downgrading may cause data loss if the migration included column drops or data removal.

```bash
# Revert the last migration
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /app/.venv/bin/alembic downgrade -1

# Revert to a specific revision
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /app/.venv/bin/alembic downgrade <revision>

# Check current revision before rollback
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /app/.venv/bin/alembic current

# View migration history
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml exec app /app/.venv/bin/alembic history
```

**Important considerations:**
- Always backup your database before running downgrade
- Test rollback procedures in staging first
- Some migrations may not be reversible — check revision scripts in `alembic/versions/`

### Configuration Rollback

Restore previous configuration files from backup:

```bash
# Restore .env from backup
cp .env.backup .env

# Or restore from version control
git checkout HEAD~1 -- .env

# Restart services to apply changes
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml restart app
```

For production environments using Docker secrets or mounted config files:

```bash
# Restore secrets from backup location
cp /secure/backups/.env.production .env
docker compose -p mkobi --env-file .env -f docker/docker-compose.yml up -d
```

---

## Design Principles

This project intentionally avoids overengineering. The following decisions reflect that philosophy:

- **No Redux/Zustand:** TanStack Query handles all server state. React local state (`useState`, `useReducer`) handles UI state.
- **No unnecessary abstraction layers:** API calls go through a thin Axios instance (with JWT interceptors). No additional service wrappers or API gateway abstractions.
- **No duplicated logic:** Pydantic models from the backend are the single source of truth for data shapes. Frontend types are derived from the OpenAPI spec.
- **No premature scaling:** A single FastAPI instance with **4 uvicorn workers** handles typical BI workloads. Scale horizontally only when metrics justify it. The connection arithmetic that bounds this figure — and the finding that it exceeds the store's `max_connections` — is the [Connection-Pool Budget](../06-backend/architecture.md#connection-pool-budget) in Backend Architecture; that section owns the ceiling and is not restated here. The deployment reaches a **125**-connection estimate against PostgreSQL 18's shipped `max_connections` of `100`, and up to a **210** unconstrained ceiling; the ceiling is therefore a risk rather than a comfortable number, and the pool's per-process values are reachable from `DatabaseSettings` should the sizing change.
- **No framework churn:** The stack (FastAPI, React, PostgreSQL, Polars) is stable and well-supported. Avoid adding new frameworks without strong operational justification.

---

## Dash Migration Path

The system may need to coexist with an existing Dash application during migration. Two strategies are supported:

### Strategy 1 — iframe Fallback (Gradual Migration)

Embed existing Dash charts within the React SPA via `<iframe>`. This allows incremental migration of individual dashboards without a full rewrite.

```tsx
// React component wrapping a Dash chart
<DashEmbed url="http://dash-server:8050/chart-name" />
```

**Pros:** Zero risk to existing Dash dashboards. Teams can migrate one chart at a time.
**Cons:** iframe isolation limits interactivity. Two runtimes to maintain.

### Strategy 2 — Full Replacement (Preferred)

Replace Dash charts with Plotly.js React components. The backend API serves the same aggregated data format to both frontends during the transition period.

```tsx
// Plotly.js React chart
import Plot from 'react-plotly.js';
<Plot data={chartData} layout={layout} />
```

**Pros:** Single runtime, full interactivity, consistent UX, no iframe limitations.
**Cons:** Requires rewriting each Dash chart as a React component.

### Recommendation

Use Strategy 1 for complex, stable charts that rarely change. Use Strategy 2 for new development and charts that need tight integration with the React SPA. Over time, migrate all charts to Strategy 2.

---

## Cross-References

- [Backend Architecture](../06-backend/architecture.md) — System architecture and startup lifecycle
- [Configuration](../06-backend/configuration.md) — Config sources, secrets, and environment variables
- [Security Overview](../08-security/security-overview.md) — Production credential enforcement and security constraints
- [Security Checklist](security-checklist.md) — Production security verification checklist
- [Health API](../05-health/health-api.md) — Health check endpoints for load balancers and Kubernetes
- [Task Queue](../03-processing/task-queue.md) — Redis/RQ migration for production background processing
- [Logging](../06-backend/logging.md) — Structured JSON logging in production