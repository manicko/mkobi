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

**Auth level:** Public (no authentication required)

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

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/health/detailed`             |
| **Auth level** | Public                         |

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
      "status": "available",
      "path": "/app/frontend/dist"
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

Returned when one or more components are unavailable. The overall `status` field reflects the worst component state.

```json
{
  "status": "unhealthy",
  "components": {
    "database": {
      "status": "disconnected",
      "error": "connection refused"
    },
    "static_files": {
      "status": "unavailable",
      "path": "/app/frontend/dist"
    }
  }
}
```

**Components checked:**

| Component      | Check                                                      | Type        |
| -------------- | ---------------------------------------------------------- | ----------- |
| `database`     | Executes `SELECT 1` against PostgreSQL                     | Critical    |
| `static_files` | Verifies the resolved bundle directory exists **and** carries `index.html` | Non-critical|
| `stale_processing_reconciler` | Reports the background reconciler's lease state and last completed sweep | Observability only |

**Behavior:**
- Database check: same connectivity test as the basic endpoint; includes the error message in the response on failure
- Static files check: verifies the configured bundle directory (default `frontend/dist`, populated by `npm run build`) exists **and** contains an `index.html`; reports `"available"` only for that predicate, otherwise `"unavailable"`, and the `path` field carries the **resolved absolute path** rather than the configured literal. A `dist` directory without an `index.html` is reported `"unavailable"` because the app registers no catch-all routes in that state — the check and the SPA mount are driven by the same helper, so the health verdict and the route table cannot disagree
- The overall `status` is `"unhealthy"` if any component reports a failure
- The reconciler component never changes the overall `status` — see [below](#22-health-is-deliberately-unchanged)

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
    "static_files": { "status": "available", "path": "/app/frontend/dist" },
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

`/health` is what the container healthcheck curls and what `nginx` gates on via `depends_on: app: condition: service_healthy`. If reconciler or lease state fed that endpoint, then during any Redis blip three of the four workers would report unhealthy and the reverse proxy would refuse to start — turning a degraded background sweep into a total outage of the API. `/health` therefore keeps meaning one thing only: *the database is reachable*. Everything else belongs on `/health/detailed`, which returns `200` regardless and never withholds a component.

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
  "version": "1.0.0"
}
```

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

On failure, the exception message is included in the detailed health check response and logged server-side at `ERROR` level.

---

## Monitoring Integration

These endpoints are designed for integration with:

- **Kubernetes:** Configure as `livenessProbe` and `readinessProbe` targets
- **Load balancers:** Use `/health` for health check pings to determine instance availability
- **Uptime monitors:** Poll `/health` at regular intervals; alert on non-200 responses
- **Admin dashboards:** Use `/health/detailed` for a component-level status overview

**Recommended polling interval:** 10–30 seconds for `/health`.

---

## Cross-References

- [System Overview](../00-overview/overview.md) — Technology stack and architecture summary
- [Data Flow](../00-overview/data-flow.md) — End-to-end data processing pipeline
- [API Responsibilities](../SPEC.md#14-api-responsibilities-fastapi) — Full API endpoint listing
- [Database Schema](../09-database/schema-core.md) — PostgreSQL table definitions and indexes
- [Deployment](../10-deployment/deployment.md) — Production deployment and container orchestration
- [Configuration](../06-backend/configuration.md) — Health check configuration and environment variables
