---
id: backend-architecture
domain: backend
tags:
  - clean-architecture
  - layers
  - service-layer
  - repository
  - startup-lifecycle
  - stateless-design
related:
  - configuration
  - logging
  - testing
  - data-flow
  - system-overview
---

# Backend Architecture

## Overview

The backend follows **Clean Architecture** principles with a strict layered design. FastAPI serves as the HTTP layer, delegating all business logic to the service layer, which in turn coordinates data access through repositories.

```
Browser (React SPA)
       ↓ HTTPS/JSON
FastAPI (REST API)
       ↓
Service Layer
       ↓
Repository Layer
       ↓
PostgreSQL
```

## Key Principles

1. **All business logic resides in the service layer** — API route handlers contain no business logic.
2. **React is UI-only** — the frontend contains no business logic, only presentation state.
3. **Access control is enforced on every request** — the backend validates permissions for every API call.
4. **No overengineering** — proven libraries are used directly without unnecessary abstraction layers.
5. **Internationalization** — Full Cyrillic and Latin character support through UTF-8 encoding. The standard user-facing date format is `dd/mm/yyyy`.

## Layer Responsibilities

### API Layer (`src/mkobi/api/`)

- Defines HTTP routes and request/response models
- Handles JWT authentication via dependencies
- Validates input using Pydantic models
- Delegates to service layer for all business logic
- Enforces role-based access control at route level

**Dependency direction:** API → Service → Repository

### Service Layer (`src/mkobi/services/`)

- Contains all business logic
- Orchestrates data access through repositories
- Handles data processing pipeline (upload → parse → transform → aggregate → save)
- Manages authentication, authorization, and rate limiting
- Coordinates background task processing

### Repository Layer (`src/mkobi/db/repositories/`)

- Provides data access abstraction over SQLAlchemy models
- Each repository corresponds to a domain entity
- Uses async SQLAlchemy 2.0 sessions
- No raw SQL — all queries through SQLAlchemy ORM/Core parameterized queries

### Data Layer (`src/mkobi/data/`)

- CSV/CSV.gz file parsing using **Polars** (pandas is forbidden)
- Data transformation according to dashboard processing configurations
- Aggregation (groupby, YoY, shares, custom metrics)
- Formula parser for custom metric expressions

### Core Layer (`src/mkobi/core/`)

- Security utilities (JWT creation/verification, password hashing via bcrypt)
- Permission checking logic
- Logging configuration (structured JSON logging)
- Redis client for rate limiting
- Background task submission (RQ, `core/task_queue.py`) — the only submission
  path; the in-process `asyncio.Queue` has been removed
- Redis-backed lease for the stale-processing reconciler (`core/reconciler_lease.py`)

### Models (`src/mkobi/models/`)

- Pydantic v2 models for request/response validation
- All constants and statuses defined as `StrEnum` (see `src/mkobi/models/enums.py`)

## Stateless Design

The application is fully stateless:

- **No server-side sessions** — authentication state is carried in JWT tokens
- **JWT tokens** are validated on every request via FastAPI dependencies
- **React SPA stores JWT** in memory (production) or sessionStorage (development)
- **No sticky sessions** — any server instance can handle any request

This enables horizontal scaling and simplifies deployment.

## Application Startup Lifecycle

On startup, FastAPI runs initialization through `DatabaseStarter` (lifespan context manager, `src/mkobi/db/starter.py`):

### Step 1: Dependency Check (`main.py`)

Before any imports, `check_dependencies()` verifies that all required Python packages are importable. The application exits with a clear error message if any critical module is missing.

Required modules: `aiofiles`, `fastapi`, `sqlalchemy`, `httpx`, `pydantic`, `polars`, `plotly`, `redis`, `bcrypt`, `jose`, `alembic`, `asyncpg`, `rq`, `tenacity`.

### Step 2: Database Connectivity Check

- Verifies the main database (`bidb`) is reachable by executing `SELECT 1`
- Checks for the existence of the `alembic_version` table to confirm schema is initialized
- Raises `DatabaseNotFoundError` or `SchemaNotFoundError` on failure

### Step 3: Alembic Migrations

- Applied automatically when `AUTO_MIGRATE=true`
- Runs via `asyncio.to_thread()` to avoid blocking the event loop
- Uses the `alembic.ini` configuration with the database URL overridden from settings
- The migration run is guarded by a **session-scoped** `pg_try_advisory_lock` whose wait is **bounded** (30 attempts at 10 s, ≈4 m 50 s) and **logged at every refusal**
- A lock that cannot be acquired in that window is a **refusal to migrate** — the process exits non-zero and the stack does not start
- **What it does not cover** — everything `DatabaseStarter.startup` does after `alembic upgrade head` returns: the admin user, the development seeders, orphan temp-file cleanup, old-log cleanup and test-database recreation

### Step 4: Admin User Creation

- Idempotent — safe to run on every startup
- Uses a SAVEPOINT (nested transaction) to handle race conditions cleanly
- Credentials sourced from `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables
- Logs a warning if default credentials are used (development only)

### Step 5: Stale Temp File Cleanup

- Removes orphaned temporary upload files from previous application runs
- Threshold controlled by `STALE_FILE_THRESHOLD_HOURS` (default: 24 hours)
- Uses `platformdirs` user data directory for temp file location

### Step 6: Test Database (test environment only)

- Reached when the tier is `test` or `RECREATE_TEST_DB=true` is set
- **Guarded twice before any statement reaches the target**: recreation is
  refused unless the *configured* environment is `test`, and refused again unless
  the database name matches `^bidb_test(_[A-Za-z0-9]+)?$` (the convention
  `tests/conftest.py` derives for pytest-xdist workers). A refusal raises
  `UnsafeTestDatabaseRecreationError` — it is never logged and ignored
- `RECREATE_TEST_DB` can therefore *select* recreation inside a test tier; it can
  no longer authorise one anywhere else
- On success: terminates existing connections, drops and recreates the database,
  then applies Alembic migrations

### Step 7: Application Ready

- FastAPI begins accepting HTTP requests
- All API endpoints are available
- Background work is submitted to the RQ queue and executed by the `rq-worker`
  process; the application process no longer runs a queue worker of its own
- Stale processing log cleanup is scheduled (see below)

### Stale Processing Log Cleanup

A periodic background task detects and resolves processing logs stuck in `PROCESSING` state (e.g., due to worker crashes). Entries that have been in `PROCESSING` state longer than a configurable timeout (default: 5 minutes) are automatically marked as `FAILED` with an error message indicating the cleanup action. This provides visibility into crashed workers and prevents indefinite `PROCESSING` states.

The production image runs uvicorn with `--workers 4`, so every worker process executes `lifespan` and would otherwise start its own copy of this loop — and run its own boot-time orphan repair. A Redis-backed lease (`core/reconciler_lease.py`) elects a single replica to do both. The lease **fails open**: a replica that cannot reach Redis sweeps anyway, because the cleanup is a monotone, idempotent `UPDATE` and skipping it during an outage would leave nobody sweeping. Only a replica that reached Redis and found the lease held by a live peer suppresses its own sweep. Which replica won the election is published on `/health/detailed`; see [Health API](../05-health/health-api.md).

### Shutdown

- Database engine connections are disposed
- Resources are released cleanly

### Connection-Pool Budget

There are **three** `AsyncEngine` objects, created in three different places and
deliberately carrying three different pool budgets:

| # | Engine | Location | Pool |
| --- | --- | --- | --- |
| 1 | **Application engine** | `db/session.py::get_async_engine` | `QueuePool`, parameters from `DATABASE__POOL_SIZE` / `MAX_OVERFLOW` / `POOL_TIMEOUT` / `POOL_RECYCLE` |
| 2 | **Starter GRANT engine** | `db/starter.py::DatabaseStarter.startup` (`_main_engine`) | `QueuePool` with its own pinned constants `5 + 10 = 15` |
| 3 | **Migration engine** | `alembic/env.py` | `NullPool` — one connection per migration run, no budget |

Engine 2 exists for a reason that is not size. `DROP DATABASE` / `CREATE DATABASE`
**require an AUTOCOMMIT connection**, and the starter must not share the
application engine: putting start-up reads on the request pool would expose them
to a pool timeout during cold start, the worst possible moment for one. So the
divergence is deliberate and its values are pinned as named constants in
`db/starter.py`, which makes a future drift a visible diff rather than an
accident of SQLAlchemy's defaults.

Engine 2 is disposed only in `DatabaseStarter.shutdown()`, so it counts toward the
**steady-state** budget, not merely a start-up spike. Its small ceiling is free
only because its five call sites run **sequentially** — if one is ever made
concurrent, the divergence stops being free and becomes a second, unconfigured
budget.

The arithmetic below uses the starting defaults and PostgreSQL 18's shipped
`max_connections` of `100` (with `superuser_reserved_connections` of `3` inside
that figure, leaving 97 for application roles):

```
per uvicorn worker:  application engine 10 + 20 = 30    starter GRANT engine 5 + 10 = 15
deployment:          4 × 30 = 120  +  4 × 1 = 4  +  1 (rq work horse)   = 125 reachable
unconstrained:       120 + 4 × 15 = 60 + 30 (work-horse pool) + 1       = 211
PostgreSQL 18:       max_connections "typically 100", superuser_reserved_connections 3 inside it
```

**125 > 100 is the finding.** These are *ceilings, not demand*: a `QueuePool`
grows only to its concurrent high-water mark, so a quiet worker holds fewer
connections than its budget. Note also that the production image runs
`--workers 4`; the starter and application engines are **per-process** (each
uvicorn worker runs `lifespan` independently), while the AUTOCOMMIT starter
engines and the migration engine are **per-call**.

Operators can see the server-side half in `pg_stat_activity`:

```sql
-- current count by state
SELECT state, count(*) FROM pg_stat_activity
WHERE datname = current_database() GROUP BY state ORDER BY 2 DESC;

-- the maximum, and what predicts "sorry, too many clients already"
SELECT current_setting('max_connections')::int                AS max_connections,
       current_setting('superuser_reserved_connections')::int AS superuser_reserved,
       (SELECT count(*) FROM pg_stat_activity)                AS total_now,
       (SELECT count(*) FROM pg_stat_activity
          WHERE backend_type = 'client backend')               AS client_backends_now,
       (SELECT count(*) FROM pg_stat_activity
          WHERE state = 'idle in transaction')                 AS idle_in_transaction,
       (SELECT count(*) FROM pg_stat_activity
          WHERE wait_event_type = 'Lock')                      AS waiting_on_lock;
```

`engine.pool.status()` is the client-side half PostgreSQL cannot give: how many
connections the pool has opened, how many are checked out, and how many are
overflowing. Both halves are needed — the server sees connections, the pool sees
budget.

`DATABASE__POOL_RECYCLE=300` is the recommended production value. It sits below
every binding anchor: PgBouncer's `server_idle_timeout` (600 s) and
`server_lifetime` (3600 s), and a managed proxy's 1800 s idle and 24-hour hard
client cap. It is a starting recommendation, not a decision: the sizing choice
belongs to the performance phase. The default remains `-1` (no recycle) so
rollout changes nothing.

## Configuration

See [Configuration](configuration.md) for details on config source priority, secrets management, and production credential enforcement. See [Deployment](../10-deployment/deployment.md) for Docker and production deployment details.

## Cross-References

- [System Overview](../00-overview/overview.md) — Technology stack and project structure
- [Data Flow](../00-overview/data-flow.md) — End-to-end data processing pipeline
- [Configuration](configuration.md) — Config sources, secrets, and environment variables
- [Logging](logging.md) — Logging standards and structured JSON logging
- [Testing](testing.md) — Pytest strategy and coverage areas
- [Database Schema](../09-database/schema-core.md) — PostgreSQL table definitions and indexes
- [API Responsibilities](../SPEC.md#14-api-responsibilities-fastapi) — Full API endpoint listing
- [Deployment](../10-deployment/deployment.md) — Production deployment and Docker configuration
- [Task Queue](../03-processing/task-queue.md) — Background processing and Redis/RQ migration
