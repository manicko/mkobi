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
  - transactions
  - concurrency
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

## Transaction Ownership

**A request's unit of work belongs to the service layer.** The seam is `IUserService`: its write
methods — `create_user`, `update_user_role`, `update_user_active_status` and `delete_user` — each
end their own transaction, so a write is durable when the method returns and nothing is committed
when it raises.

The transport layer holds **no** boundary of its own:

- `api/deps.py::get_db_dependency` and `db/session.py::get_session` / `get_db` yield a session and
  close it. They **commit nothing and roll nothing back**. **Closing the session is not a
  transaction boundary** — a write that was never committed is discarded when the session closes,
  and a route that adds a `commit()` of its own duplicates a boundary the service already owns.
- Repositories (`db/repositories/`) `add`/`setattr` and then `flush()`; they do not commit. That is
  why the driver's `IntegrityError` is raised at flush time and is classified in the service, which
  is the layer that knows what the error *means*.
- Nine `await db.commit()` call sites remain in six route modules under `api/routes/`. That
  inconsistency is recorded, not resolved here; the rule above is the direction the codebase is
  moving in.

A caller that needs **two** writes in one transaction cannot get it from this seam and must open the
transaction itself. The worker's aggregate rebuild is the notable case: it is a long
multi-statement transaction owned by the worker rather than by a service, and is described under
[Aggregate Rebuild Exclusion](#aggregate-rebuild-exclusion).

## Stateless Design

The application is fully stateless:

- **No server-side sessions** — authentication state is carried in JWT tokens
- **JWT tokens** are validated on every request via FastAPI dependencies
- **React SPA stores JWT** in memory (production) or sessionStorage (development)
- **No sticky sessions** — any server instance can handle any request

This enables horizontal scaling and simplifies deployment.

### Account Deactivation: Two Authorities

Deactivating a user pairs two effects that cannot be made transactional together: the `is_active`
write on the `users` row, and a Redis **user-level** revocation marker
(`core/security.py::revoke_all_user_tokens`). Since the database half became **durable** for the
first time, the authority for a deactivated account is **split**, and the split is load-bearing:

| Surface | Authority | Consequence |
| ------- | --------- | ----------- |
| Every **protected** endpoint, via `api/deps.py::get_current_user_dependency` | the **database row** — the dependency re-reads the user on **every** authenticated request and rejects `is_active is False` | a committed deactivation stops the user immediately, independently of Redis |
| `POST /auth/refresh` | the **database row**, co-authoritative with the **Redis user-level marker** — the marker branch runs first and keeps its `TOKEN_REVOKED` contract, then the freshly re-read row is compared | revokes already-issued access *and* refresh tokens without touching the row, and independently refuses a deactivated row whose marker has expired or been flushed |
| `POST /auth/login`, `POST /auth/login/form` | the **database row**, consulted at login | a deactivated user is refused **at login** with `401 AUTHENTICATION_FAILED`, indistinguishable from a wrong password; the marker is deliberately not consulted there, and no freshly signed tokens are issued |

**The ordering is deliberate: the commit lands first, the revocation second.**
`PATCH /admin/users/{user_id}/active` calls `update_user_active_status()`, which commits, and only
then revokes in Redis. Three reasons, in order of weight:

1. **It fails closed on the axis that matters.** A committed deactivation stops the user at every
   protected endpoint on its own. The reverse order fails open: an account believed deactivated
   stays fully usable and merely has its current tokens revoked.
2. **This failure is reported; the reverse one is silent.** A Redis fault after the commit is a
   **500** naming the condition (`INTERNAL_ERROR`, "User was deactivated successfully, but
   revoking the user's tokens failed"), and the endpoint is idempotent, so a retry re-commits the
   same `is_active` and re-issues the marker. With the commit *after* the revocation, a database
   fault would leave `is_active` unchanged, the user would log in again, and nothing in the
   response would say the deactivation never happened.
3. **The residual exposure is bounded and enumerated.** The login gap this paragraph used to name
   was **closed in phase 04** — `is_active` is now authoritative at login and on `POST /auth/refresh`
   — so what remains is narrower and honest. (i) The **reactivate branch never clears the Redis
   user-level marker**: a reactivated account can log in and is then refused at the protected gate
   until the marker expires. That asymmetry belongs to a **later phase** and is deliberately not
   fixed here. (ii) A Redis flush between a deactivation and a request leaves the **database row**
   as the only backstop, which is correct for protected access and for the two token-issuing paths,
   but means the already-issued-token revocation is lost with the marker.

The route's `await db.rollback()` in its `except Exception` handler **stays** and is still correct
for the pre-commit window (a failure inside `update_user_active_status`, where the session does need
one). It can no longer undo the write, and its docstring says so.

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
- `ensure_admin_user()` opens **one top-level transaction** (`async with db.begin()`) and issues a
  single `INSERT ... ON CONFLICT (email) DO NOTHING`. The concurrent-startup race is handled by
  the `ON CONFLICT` clause, **not** by a SAVEPOINT or any nested transaction: there is no
  nested transaction on this path, and the surrounding top-level transaction commits
  unconditionally — it either inserted the row or deliberately did nothing
- Credentials sourced from `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables
- A known-placeholder password **raises** in the production tier and only warns elsewhere; a
  weak *username* only warns, because `Settings.validate_admin_credentials()` and this function
  share the predicate but not the action (see
  [Configuration → Admin Credentials](configuration.md#admin-credentials))
- Because the conflicting insert does nothing, a restart never overwrites an existing admin's
  stored password hash

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

Two sweeps reap processing logs, on **one** configured horizon,
`STALE_PROCESSING_TIMEOUT_MINUTES` (default: **30 minutes**; `get_config().stale_processing_timeout_minutes`
returns the effective value). `DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES = 5` in
`workers/data_worker.py` is only the *signature* default of `cleanup_stale_processing_logs()` and
is a fallback only — `app.py::lifespan` always passes the setting, so **the running value is the
configured one, 30 minutes out of the box**, and the `5` never decides anything.

| Sweep | Status it reaps | When it runs | Horizon |
| ----- | --------------- | ------------ | ------- |
| `mark_orphaned_uploaded_logs_failed()` | `UPLOADED` | **Boot only** — once per process start, lease-guarded | same setting |
| `cleanup_stale_processing_logs()` | `PROCESSING` | Periodically, every `STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS` (default 300 s), lease-guarded | same setting |

Both mark the row `FAILED` with a message naming the cleanup, so a crashed or killed worker becomes
visible instead of leaving a row that reads "processing" forever.

**Why one horizon, and what it fixed.** The `PROCESSING` transition is a **durable commit on its own
session before the work begins**, so a committed `processing` row now exists for the first time and
the periodic sweep finally has input — "prevents indefinite `PROCESSING` states" is now literally
true rather than an intention. Before that, the row read `uploaded` from every other connection
until it jumped to `completed`, so a worker killed mid-job left nothing for the sweep to find. That
same commit changed the *meaning* of a row still reading `UPLOADED`: it now means only "not picked
up yet". The boot-time marker therefore had to adopt the sweep's horizon instead of keeping a
one-minute literal of its own — with a short literal of its own, any worker restart would flip
queued-but-unstarted rows to `FAILED` while the still-queued job would later move them back to
`completed`. The two predicates are disjoint by status (`UPLOADED` vs `PROCESSING`), so they never
contend for the same row; sharing the horizon keeps their *notion of "too old"* from diverging.

**What the horizon bounds, stated honestly: time to first report, not job lifetime.** It is not a
job-duration limit. A legitimately long rebuild that runs past the horizon can be flipped to
`FAILED` by a sweep tick while it is still working, and the worker's own later commit then
overwrites that back to `completed`. The end state is coherent, but the audit trail briefly shows a
false failure. `DATABASE__LOCK_TIMEOUT_MS` must therefore stay well **below** this horizon
(3 minutes against 30 by default) so a rebuild waiting on the rebuild exclusion cannot be swept
while it is legitimately waiting.

**The boot-time marker is boot-only, and stays that way.** It runs once per process start and is
not periodic. Its predicate is "`UPLOADED` and older than the horizon", so a queued orphan that
arrives *after* the boot sweep survives the restart untouched and is only reaped the next time the
horizon has elapsed **and** a later boot happens — in practice, up to a full horizon of quiet.

The production image runs uvicorn with `--workers 4`, so every worker process executes `lifespan` and would otherwise start its own copy of this loop — and run its own boot-time orphan repair. A Redis-backed lease (`core/reconciler_lease.py`) elects a single replica to do both. The lease **fails open**: a replica that cannot reach Redis sweeps anyway, because the cleanup is a monotone, idempotent `UPDATE` and skipping it during an outage would leave nobody sweeping. Only a replica that reached Redis and found the lease held by a live peer suppresses its own sweep. Which replica won the election is published on `/health/detailed`; see [Health API](../05-health/health-api.md).

### Shutdown

- Database engine connections are disposed
- Resources are released cleanly

### Connection-Pool Budget

There are **five** `AsyncEngine` construction sites, but only **three** of them
participate in the steady-state budget. Two are per-call and test-tier gated, so
they never coexist with the production workload; the table classifies all five:

| # | Engine | Location | Pool | Lifetime |
| --- | --- | --- | --- | --- |
| 1 | **Application engine** | `db/session.py::get_async_engine` | `QueuePool`, parameters from `DATABASE__POOL_SIZE` / `MAX_OVERFLOW` / `POOL_TIMEOUT` / `POOL_RECYCLE` | **per-process**, steady-state |
| 2 | **Starter GRANT engine** | `db/starter.py::DatabaseStarter.startup` (`_main_engine`) | `QueuePool` with its own pinned constants `5 + 10 = 15` | **per-process**, steady-state |
| 3 | **Migration engine** | `alembic/env.py` | `NullPool` — one connection per migration run, no budget | **per-call** (migrate container only) |
| 4 | **Test-recreation admin engine** | `db/starter.py::recreate_test_database` (`admin_engine`) | AUTOCOMMIT, SQLAlchemy defaults `5 + 10 = 15` | **per-call**, disposed in `finally` |
| 5 | **Test-recreation grant engine** | `db/starter.py::recreate_test_database` (`test_admin_engine`) | AUTOCOMMIT, SQLAlchemy defaults `5 + 10 = 15` | **per-call**, disposed in `finally` |

Engine 2 exists for a reason that is not size. `DROP DATABASE` / `CREATE DATABASE`
**require an AUTOCOMMIT connection**, and the starter must not share the
application engine: putting start-up reads on the request pool would expose them
to a pool timeout during cold start, the worst possible moment for one. So the
divergence is deliberate and its values are pinned as named constants in
`db/starter.py`, which makes a future drift a visible diff rather than an
accident of SQLAlchemy's defaults.

Engines 4 and 5 cannot appear in the steady-state budget, on two independent
grounds. `recreate_test_database` is reached through `DatabaseStarter.startup` when
the *configured* environment is `test` (or `RECREATE_TEST_DB` selects it within that
tier), and through the documented CLI entry point
`python -m mkobi.db.starter --recreate-test-db`; either way the method refuses
unless the configured environment is `test`, so no production process ever
constructs them. And both are **per-call** — created inside the method and disposed
in its `finally` before it returns — so even in the test tier they hold connections
for the duration of one recreation, not for the process lifetime. They are listed
for completeness, not omitted: the reader should be able to see that the
steady-state count is three *by the code's lifetime*, not by an unstated
assumption. (Adjacent engine 3, the migration engine, is `NullPool` and so carries
no standing pool either; that is a property of engine 3's own lifetime, not an
additional ground for engines 4 and 5.)

Engine 2 is disposed only in `DatabaseStarter.shutdown()`, so it counts toward the
**steady-state** budget, not merely a start-up spike. Its small ceiling is free
only because its five call sites run **sequentially** — if one is ever made
concurrent, the divergence stops being free and becomes a second, unconfigured
budget.

The arithmetic below uses the starting defaults and PostgreSQL 18's shipped
`max_connections` of `100` (with `superuser_reserved_connections` of `3` inside
that figure, leaving 97 for application roles). `DatabaseStarter.startup` runs
inside the FastAPI `lifespan` (`app.py`), so the starter engine exists once per
uvicorn worker; it does **not** run in the `rq-worker`, which reaches the database
only through `get_session()` and therefore carries the application engine, not a
starter engine. The migration container runs `alembic upgrade head` and never the
`lifespan`, so it contributes no application or starter engine.

```
per uvicorn worker:  application engine 10 + 20 = 30    starter GRANT engine 5 + 10 = 15
per rq work horse:   application engine 10 + 20 = 30    no starter engine (no lifespan)

deployment:          4 × 30 = 120  +  4 × 1 = 4  +  1 (work horse, one job at a time)  = 125 reachable
unconstrained:       5 × 30 = 150  +  4 × 15 = 60                                       = 210 ceiling
PostgreSQL 18:       max_connections "typically 100", superuser_reserved_connections 3 inside it
```

**125 > 100 is the finding:** even the demand-shaped figure exceeds
`max_connections`, and the unconstrained ceiling is higher still. These are
*ceilings, not demand*: a `QueuePool` grows only to its concurrent high-water mark,
so a quiet worker holds fewer connections than its budget. The `125` figure is the
reachable estimate for the documented shape — the four uvicorn application pools at
their full `30`, each starter engine at its sequential high-water of `1`, and the
work horse at one connection because RQ processes one job at a time — not a claim
that every pool fills. The `210` ceiling is what the pools may reach if every
process saturates at once; the work horse's own ceiling is `30`, not the `1` of the
reachable estimate.

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

## Aggregate Rebuild Exclusion

Two rebuilds of the same dashboard clear and rewrite the same `aggregated_data` rows, so they must
not interleave. Historically they serialised on an *undeclared* row lock — an accident, with an
unbounded and unlogged wait. It is now a **declared, bounded exclusion**
(`src/mkobi/db/advisory_lock.py`), and its scope is worth stating precisely because it is narrower
than "the rebuild is locked":

- **Per `dashboard_id`, not global.** The key is a stable `blake2b` digest of
  `mkobi:aggregate-rebuild:<dashboard_id>` rendered as a signed int64
  (`dashboard_rebuild_lock_key`). Two rebuilds of *one* dashboard exclude each other; rebuilds of
  different dashboards never wait on each other. It is a digest rather than Python's `hash()`,
  which is salted per process — under `--workers 4` plus `rq-worker` each replica would otherwise
  take a *different* lock and the exclusion would not exist at all.
- **Transaction-scoped.** The worker takes `pg_advisory_xact_lock` as the **first statement inside
  its own `session.begin()` block**, and the transaction releases it — on commit, on rollback, and
  at session end if the connection dies. There is no explicit unlock to leak. The worker's
  failure-compensation handler runs *after* that block has rolled back, so the `FAILED` row is
  written on a fresh session while the lock is already gone.
- **Bounded, per transaction, by `DATABASE__LOCK_TIMEOUT_MS`** (default 180000 ms = 3 minutes).
  It is applied with `set_config('lock_timeout', …, true)` rather than a bare `SET`, because a
  bare `SET` survives `COMMIT` on a pooled connection and would then bound every unrelated lock wait
  in the process.
- **What the bound covers: every lock wait in the worker's transaction, not only the advisory one.**
  PostgreSQL has no per-lock timeout, so a row-lock wait later in the same job that exceeds the bound
  raises the same SQLSTATE `55P03` and is classified the same way. The timeout log line names the
  advisory lock because that is the common case; `pg_locks` remains the operator's window on any
  other waiter.
- **A timeout is not a failure of the job.** It is classified `PROCESSING_IN_PROGRESS` on the
  processing log (not `PROCESSING_FAILED`) and surfaced to the client through the stored
  `error_code`. The 3-minute default must stay **below** `STALE_PROCESSING_TIMEOUT_MINUTES`
  (30 minutes) — a lock wait that outlives the mechanism meant to clean it up is not a bound at
  all.
- `DATABASE__LOCK_TIMEOUT_MS = 0` means **unbounded**, which is PostgreSQL's own sentinel for
  "wait forever". Do not set it in production: a wedged holder would hold a pooled connection
  indefinitely.

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
