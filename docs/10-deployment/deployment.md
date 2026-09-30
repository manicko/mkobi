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
docker compose -f docker/docker-compose.yml up -d db
uv run alembic upgrade head
```

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
docker compose -f docker/docker-compose.yml --profile production up -d
```

---

## Docker Deployment

The project uses a multi-stage Dockerfile supporting dev, test, and prod targets. See [Docker Guide](../11-guides/docker.md) for the full Docker specification.

### Quick Start

```bash
# Production (default target)
docker compose -f docker/docker-compose.yml up -d

# Production with nginx (production profile; rq-worker starts either way)
docker compose -f docker/docker-compose.yml --profile production up -d

# Development with hot reload and frontend dev server
docker compose -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d
```

**Note:** Development mode includes the frontend service running on port 5173 (Vite dev server with hot reload). Access the application at http://localhost:5173.

### Dockerfile Targets

| Target | Base | Dependencies | Workers | Use Case |
|--------|------|-------------|---------|----------|
| `base` | python:3.12-slim-bookworm | System + build tools | — | Shared base for dev/test |
| `prod-base` | python:3.12-slim-bookworm | Runtime only (libpq5, libmagic1) | — | Minimal base for prod |
| `dev` | base | All (incl. dev) | 1 (--reload) | Local dev |
| `test` | base | All (incl. dev) | 1 (pytest) | CI/CD |
| `prod` | prod-base | Production only | 4 | Production |

### Production Profiles

`nginx` is the **only** service gated by `profiles: [production]`. It is not started by
default; pass `--profile production` to include it:

- **nginx** — Reverse proxy serving React SPA and proxying API requests to FastAPI.

`redis` and `rq-worker` are **not** profile-gated. They start with the base file whether
or not a profile is passed:

- **rq-worker** — Redis Queue worker for background task processing. Runs `/app/.venv/bin/rqworker --url redis://redis:6379/0` — the virtualenv console script invoked directly, not `uv run rq worker`. Shares `app_data` volume with the app service.

See [Docker Guide](../11-guides/docker.md#rq-worker) for its dependencies, environment and mounts.

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

> **Security note:** On shared machines, consider binding to `127.0.0.1` instead of the default `0.0.0.0` to prevent cross-talk between developers. For CI/CD environments, running tests inside the container (`docker compose exec test-app uv run pytest`) avoids exposing ports entirely.

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

### Database Migrations

- `AUTO_MIGRATE` — **off by default**, and off everywhere in the shipped Compose files. The `auto_migrate` setting is `false` in `src/mkobi/settings/app.yaml` and in the `Settings` field, and `AUTO_MIGRATE=true` makes the **application process** run `alembic upgrade head` during startup (`DatabaseStarter.startup`). It therefore takes effect only where a process actually receives the variable, and in the base compose file none does: `app` is not given `AUTO_MIGRATE` at all, and `rq-worker` receives a literal `AUTO_MIGRATE: "false"`. Setting `AUTO_MIGRATE=true` in an env file changes nothing — use the `migrate` service below.
- **Migration advisory lock** — In multi-instance deployments (K8s replicas, multiple Gunicorn workers), parallel migrations can corrupt the schema. The `_apply_migrations()` method acquires a PostgreSQL advisory lock (`pg_advisory_lock(42)`) before running migrations, ensuring only one instance runs migrations at a time. The lock is released after completion, even on failure.
- **Migration job pattern** — For production Docker Compose deployments, a dedicated `migrate` service runs `alembic upgrade head` before the app service starts. The app service depends on the migration service completing successfully (`depends_on: migrate: condition: service_completed_successfully`). This separates migration concerns from application startup and allows `AUTO_MIGRATE=false` in the app config.
- Manual migration:
```bash
docker compose -f docker/docker-compose.yml exec app uv run alembic upgrade head
# Check status:
docker compose -f docker/docker-compose.yml exec app uv run alembic current
```

### Database Role (Least-Privilege)

The application uses a dedicated database role (`mkobi_app`) with limited privileges instead of the superuser `postgres` role:

| Role | Purpose | Privileges |
| --- | --- | --- |
| `postgres` | Migrations (DDL) | Superuser |
| `mkobi_app` | Runtime operations | `CONNECT`, `SELECT`, `INSERT`, `UPDATE`, `DELETE` on tables; `USAGE` on sequences |

This follows the least-privilege principle: any SQL injection or application bug is limited to the `mkobi_app` role's permissions and cannot execute superuser operations. The `postgres` role is used only for migrations that require DDL.

The role is created via an initialization SQL script mounted to `/docker-entrypoint-initdb.d/` in the PostgreSQL container. The application's `DATABASE__USER` and `DATABASE__PASSWORD` point to the `mkobi_app` role.

### PostgreSQL Locale Configuration

The PostgreSQL container uses the `builtin` locale provider with `C.UTF-8` collation:

```yaml
POSTGRES_INITDB_ARGS: "--locale-provider=builtin --locale=C.UTF-8"
```

The builtin provider gives an **immutable collation version** (fixed at `1`), eliminating collation mismatch errors that occur with the default `libc` provider when the Docker image's base OS changes. `C.UTF-8` supports both Latin and Cyrillic characters.

This is configured in both `docker/docker-compose.yml` and `docker/docker-compose.test.yml`.

### Volumes

| Volume | Container Path | Purpose |
|--------|---------------|---------|
| `postgres_data` | `/var/lib/postgresql` | Database persistence |
| `app_data` | `/app/data` | Uploads, logs, temp files |
| `redis_data` | `/data` | Task queue (if used) |

### Health Checks

- **db**: `pg_isready` — verifies PostgreSQL is accepting connections
- **app**: HTTP GET `/health` — verifies the application responds
- **redis**: `redis-cli ping` — verifies Redis availability

### Common Operations

```bash
# View logs
docker compose -f docker/docker-compose.yml logs -f app

# Open shell
docker compose -f docker/docker-compose.yml exec app /bin/bash

# Run tests
docker compose -f docker/docker-compose.test.yml exec test-app uv run pytest tests/ -v

# Stop and remove everything (including volumes)
docker compose -f docker/docker-compose.yml down -v

# Rebuild after code changes
docker compose -f docker/docker-compose.yml up -d --build
```

---

## Rollback Procedures

When a deployment fails or introduces critical bugs, use these procedures to safely roll back to a previous stable state.

### Docker Image Rollback

To revert to a previous application version:

```bash
# List available local images
docker images mkobi/app

# Pull a specific previous image tag (if using versioned tags)
docker pull mkobi/app:<previous-tag>

# Update compose file or set environment to use specific tag
# Then restart services
docker compose -f docker/docker-compose.yml up -d
```

For Docker Compose with pre-built images, ensure you have versioned tags pushed to your registry and update the `image` tag in your compose configuration.

### Database Migration Rollback

Use Alembic to revert schema changes. **Warning:** Downgrading may cause data loss if the migration included column drops or data removal.

```bash
# Revert the last migration
docker compose -f docker/docker-compose.yml exec app uv run alembic downgrade -1

# Revert to a specific revision
docker compose -f docker/docker-compose.yml exec app uv run alembic downgrade <revision>

# Check current revision before rollback
docker compose -f docker/docker-compose.yml exec app uv run alembic current

# View migration history
docker compose -f docker/docker-compose.yml exec app uv run alembic history
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
docker compose -f docker/docker-compose.yml restart app
```

For production environments using Docker secrets or mounted config files:

```bash
# Restore secrets from backup location
cp /secure/backups/.env.production .env
docker compose -f docker/docker-compose.yml up -d
```

---

## Design Principles

This project intentionally avoids overengineering. The following decisions reflect that philosophy:

- **No Redux/Zustand:** TanStack Query handles all server state. React local state (`useState`, `useReducer`) handles UI state.
- **No unnecessary abstraction layers:** API calls go through a thin Axios instance (with JWT interceptors). No additional service wrappers or API gateway abstractions.
- **No duplicated logic:** Pydantic models from the backend are the single source of truth for data shapes. Frontend types are derived from the OpenAPI spec.
- **No premature scaling:** A single FastAPI instance with 4 workers handles typical BI workloads. Scale horizontally only when metrics justify it.
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