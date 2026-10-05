---
id: health-api
domain: health
tags:
  - health-check
  - monitoring
  - database
  - kubernetes
  - load-balancer
  - uptime
related:
  - system-overview
  - data-flow
  - deployment
  - backend-architecture
---

# Health Check API

## Overview

The health check API provides endpoints for monitoring application availability and component status. These endpoints are intended for load balancers, container orchestrators (e.g., Kubernetes liveness/readiness probes), and monitoring systems.

**Base path:** `/`

**Auth level:** Public for `/health`. `/health/detailed` **requires an administrator** (`D-15-G` / `SECB-4`): an unauthenticated caller receives `401` and an authenticated non-admin receives `403`, both via the RFC 7807 error path.

---

## Endpoints

### 1. Basic Health Check

Returns the overall application status and database connectivity state.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/health`                      |
| **Auth level** | Public                         |

**Response** (`200 OK`):

```json
{
  "status": "healthy",
  "database": "connected"
}
```

**Response** (`503 Service Unavailable`):

Returned when the database is not reachable.

```json
{
  "status": "unhealthy",
  "database": "disconnected"
}
```

**Behavior:**
- Executes a `SELECT 1` query against the PostgreSQL database to verify connectivity
- Returns `200` with `"status": "healthy"` if the query succeeds
- Returns `503` with `"status": "unhealthy"` if the query fails (database unreachable or connection error)
- Logs the error at `ERROR` level on failure

---

### 2. Detailed Health Check

Returns the overall application status along with per-component health information.

| Attribute      | Value                                             |
| -------------- | ------------------------------------------------- |
| **Method**     | `GET`                                             |
| **Path**       | `/health/detailed`                                |
| **Auth level** | Administrator only (`D-15-G` / `SECB-4`); `401` unauthenticated, `403` non-admin |

> **Reduced body (`D-15-H` / `SECB-4`).** The response no longer discloses the absolute filesystem path of the client bundle or any raw database/Redis driver exception text, because that text can carry a host, port or connection string. The component structure and the operationally useful signals (component name, status, timings, counters, lease state) are kept.

**Response** (`200 OK`):

```json
{
  "status": "healthy",
  "components": {
    "database": {
      "status": "connected",
      "type": "postgresql"
    },
    "static_files": {
      "status": "available"
    },
    "redis": {
      "status": "connected",
      "type": "redis"
    },
    "stale_processing_reconciler": {
      "status": "ok",
      "lease_state": "holder",
      "last_success_at": "2026-10-01T07:05:00+00:00",
      "last_swept_count": 0,
      "sweep_count": 1,
      "unprotected_ticks": 0
    }
  }
}
```

**Response** (`200 OK` with unhealthy status):

Returned when one or more components are unavailable. The overall `status` field is computed from the `database` component only, so a failing non-database component never changes it.

```json
{
  "status": "unhealthy",
  "components": {
    "database": {
      "status": "disconnected",
      "type": "postgresql"
    },
    "static_files": {
      "status": "unavailable"
    }
  }
}
```

**Components checked:**

| Component      | Check                                                      | Type        |
| -------------- | ---------------------------------------------------------- | ----------- |
| `database`     | Executes `SELECT 1` against PostgreSQL                     | Critical    |
| `static_files` | Verifies the resolved bundle directory exists **and** carries `index.html` | Non-critical|
| `redis`        | Sends a `PING` on a short-lived client from `get_async_redis_client()` | Non-critical (reported only) |
| `stale_processing_reconciler` | Reports the background reconciler's lease state and last completed sweep | Observability only |

**Behavior:**
- Database check: same connectivity test as the basic endpoint; the driver exception is logged server-side and is **not** echoed in the response
- Static files check: verifies the configured bundle directory (default `frontend/dist`, populated by `npm run build`) exists **and** contains an `index.html`; reports `"available"` only for that predicate, otherwise `"unavailable"`. The absolute path is **not** disclosed. A `dist` directory without an `index.html` is reported `"unavailable"` because the app registers no catch-all routes in that state — the check and the SPA mount are driven by the same helper, so the health verdict and the route table cannot disagree
- Redis check: sends a `PING` on a client built fresh from `get_async_redis_client()`, mirrors the `database` component's vocabulary (`"connected"` / `"disconnected"`, with `type: "redis"`); the driver exception is logged server-side and is **not** echoed in the response. The client it built is **always closed** so a health poll cannot leak a connection pool. The transport is bounded (see the [Configuration](../06-backend/configuration.md) note on the Redis socket timeouts), so a blackholed Redis reports the outage in roughly one second rather than blocking for a minute
- The overall `status` is computed from the `database` component only: it is `"unhealthy"` if and only if the database check fails. `static_files`, `redis` and the reconciler never change it, and `/health/detailed` always returns `200`
- The reconciler component never changes the overall `status` — see [below](#22-health-is-deliberately-unchanged)
- Redis never changes the overall `status` either: a degraded Redis is reported as `"disconnected"` while the overall `status` stays `"healthy"`. This is the `DP-1` ruling (2026-10-03): Redis is a *detailed* component that never moves liveness

#### 2.1 The `stale_processing_reconciler` Component

The production image runs uvicorn with `--workers 4`, so every worker process would otherwise run its own copy of the periodic stale-processing reconciler. A Redis-backed lease elects exactly one replica; this component makes the outcome of that election observable.

It is **observability only**. It is not a readiness or correctness signal, and it never contributes to the overall `status` field.

**Fields:**

| Field | Meaning |
| ----- | ------- |
| `status` | `not_started` before the lifespan has published any state; otherwise `starting` until the first sweep completes, then `ok` |
| `lease_state` | `unknown`, `holder`, `not_holder` or `unprotected` |
| `last_success_at` | ISO-8601 UTC timestamp of the last **completed** sweep, or `null`. It advances even on a tick that marked zero rows, so a frozen value means the loop has died rather than that it had nothing to do |
| `last_swept_count` | Work items the last completed tick disposed of (may be `0`): processing rows moved to a terminal state **plus** stale temp files removed on the same tick. It is **not** a count of failed rows alone -- a value of `137` may mean 0 rows and 137 files |
| `sweep_count` | Completed ticks since the process started |
| `unprotected_ticks` | Completed ticks that ran without holding the lease because Redis was unreachable |

`lease_state` values:

| Value | Meaning |
| ----- | ------- |
| `holder` | This replica won the lease and is the one sweeping |
| `not_holder` | Redis was reached and the lease belongs to another replica; this replica does not sweep |
| `unprotected` | Redis could not be reached. The lease **fails open**: this replica sweeps anyway, because the sweep is a monotone, idempotent update and skipping it during an outage would leave nobody sweeping |
| `unknown` | No state published yet |

The lease is a load-and-observability optimisation, never a correctness gate: only `not_holder` (proof that a live holder exists) suppresses a sweep.

**Example** (a replica that holds the lease and has completed one tick):

```json
{
  "status": "healthy",
  "components": {
    "database": { "status": "connected", "type": "postgresql" },
    "static_files": { "status": "available" },
    "redis": { "status": "connected", "type": "redis" },
    "stale_processing_reconciler": {
      "status": "ok",
      "lease_state": "holder",
      "last_success_at": "2026-10-01T07:05:00+00:00",
      "last_swept_count": 0,
      "sweep_count": 1,
      "unprotected_ticks": 0
    }
  }
}
```

**Reading this in a multi-worker deployment.** Each of the four workers answers with **its own** state, so a request may land on a replica reporting `not_holder`. That is the expected steady state, not a fault: exactly one replica holds the lease and three do not. To judge the reconciler across the deployment, alert on a frozen `last_success_at` or a rising `unprotected_ticks`, not on `not_holder` alone.

**Before the lifespan runs** (for example in an ASGI test harness that never starts it) the component reports `not_started` with `lease_state: unknown` and `last_success_at: null` — never a guessed state.

#### 2.2 `/health` Is Deliberately Unchanged

`/health` still returns exactly `{"status": "healthy", "database": "connected"}` (or the `503` `unhealthy` variant). It was **not** widened to include the reconciler, and the split is intentional.

`/health` is what the container healthcheck curls and what `nginx` gates on via `depends_on: app: condition: service_healthy`. If reconciler or lease state fed that endpoint, then during any Redis blip three of the four workers would report unhealthy and the reverse proxy would refuse to start — turning a degraded background sweep into a total outage of the API. `/health` therefore keeps meaning one thing only: *the database is reachable*. Redis is deliberately **not** a key on `/health` either, even though every authenticated request depends on it (revocation reads fail closed, so a Redis outage is what makes `GET /api/v1/auth/me` answer `503`). Everything else belongs on `/health/detailed`, which returns `200` regardless and never withholds a component.

**An unauthenticated external monitor must poll `/health` or authenticate.** `/health/detailed` now requires an administrator (`D-15-G` / `SECB-4`): an unauthenticated caller receives `401` and a non-admin `403`. `/health` remains the only endpoint that is unconditionally anonymous.

**The gate is Redis-dependent — a known, accepted consequence (`SECB-4`).** The gate is `api/deps.py::require_admin_role` (not `require_dashboard_admin_access`, which requires a `dashboard_id` path parameter this endpoint has no way to supply). That dependency resolves the current user, which reads the revocation store from Redis: `require_admin_role` → `get_current_user_dependency` → `get_redis_client_dependency` → `RevocationStoreUnavailableError` → `503`. The gate therefore answers **`503` during a full Redis outage** — while `/health` keeps answering `200`. The chosen implementation accepts that 503 rather than authenticating without a Redis revocation read: weakening revocation to keep one probe usable is the larger risk, and `/health` already covers liveness.

**On the nginx layer.** The health `location` block forwards to the application and overrides only the `Host` header, so an application-level gate on `/health/detailed` **is** effective through nginx; there is no separate nginx access control to change. nginx's own comment near that block states which endpoint is anonymous (`/health`) and which is admin-gated (`/health/detailed`), and it no longer describes both as auth-free.

---

### 3. Root Endpoint

Returns basic API identification information.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/`                            |
| **Auth level** | Public                         |

**Response** (`200 OK`):

```json
{
  "message": "BI Dashboard API",
  "status": "active",
  "version": "<the installed distribution's declared version>"
}
```

The `version` value is **not a literal**: it is resolved from the installed distribution's metadata (`pyproject.toml` declares `1.0.8`) and is overridable through `APP__VERSION`. See [Configuration](../06-backend/configuration.md) for the precedence chain. The same value is published as the schema document's `info.version`.

---

## Database Connectivity Check

Both `/health` and `/health/detailed` verify database connectivity by executing a lightweight `SELECT 1` query through the SQLAlchemy async session. This confirms:

1. The database server is reachable over the network
2. The connection pool can acquire a connection
3. The database is in a state that accepts queries

**Failure modes:**

| Condition               | HTTP Status | `database` field      |
| ----------------------- | ----------- | --------------------- |
| Database unreachable    | 503         | `disconnected`        |
| Connection pool exhausted | 503       | `disconnected`        |
| Database does not exist | 503         | `disconnected`        |
| Normal operation        | 200         | `connected`           |

On failure, the exception is logged server-side at `ERROR` level and the raw driver text is **not** included in the detailed health check response.

---

## Monitoring Integration

These endpoints are designed for integration with:

- **Kubernetes:** Configure as `livenessProbe` and `readinessProbe` targets
- **Load balancers:** Use `/health` for health check pings to determine instance availability
- **Uptime monitors:** Poll `/health` at regular intervals; alert on non-200 responses
- **Admin dashboards:** Use `/health/detailed` for a component-level status overview. It requires an administrator (`D-15-G` / `SECB-4`); an anonymous uptime monitor must poll `/health` or authenticate (see [above](#22-health-is-deliberately-unchanged))

**Recommended polling interval:** 10–30 seconds for `/health`.

---

## Cross-References

- [System Overview](../00-overview/overview.md) — Technology stack and architecture summary
- [Data Flow](../00-overview/data-flow.md) — End-to-end data processing pipeline
- [API Responsibilities](../SPEC.md#14-api-responsibilities-fastapi) — Full API endpoint listing
- [Database Schema](../09-database/schema-core.md) — PostgreSQL table definitions and indexes
- [Deployment](../10-deployment/deployment.md) — Production deployment and container orchestration
- [Configuration](../06-backend/configuration.md) — Health check configuration and environment variables
