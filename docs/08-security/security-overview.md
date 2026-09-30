---
id: security-overview
domain: security
tags:
  - rate-limiting
  - file-upload-security
  - sql-injection
  - cors
  - credentials
  - secrets-management
  - jwt-security
  - token-revocation
  - password-validation
  - mime-detection
related:
  - access-control
  - auth-api
  - error-format
  - configuration
  - frontend-security
  - processing-api
---

# Security Overview

## Overview

This document describes the security constraints and measures implemented across the system. Security is enforced at multiple layers: network (CORS), application (rate limiting, input validation), and data (parameterized queries, credential management).

> **[HIGH-RISK]** Security constraints are enforced on the **backend**. Frontend validation is a UX convenience only and must never be relied upon as a security boundary.

---

## Rate Limiting

### Overview

Rate limiting is applied to sensitive endpoints to prevent brute-force attacks and abuse. The rate limiter is Redis-based and uses a sliding window algorithm.

### Protected Endpoints

| Endpoint | Rate Limit | Scope |
| --- | --- | --- |
| `POST /api/v1/auth/login` | 5 attempts per 5 minutes | Per IP |
| `POST /api/v1/auth/login/form` | 5 attempts per 5 minutes | Per IP |
| `POST /api/v1/auth/register-request` | 3 attempts per hour | Per IP/email |
| `POST /api/v1/upload/:dashboard_id` | Configured via env | Per user |
| `POST /api/v1/upload/:dashboard_id/process` | Configured via env | Per user |

### Email Enumeration Mitigation

Login rate limiting uses **per-IP** keys (not per-email) to prevent email enumeration attacks. An attacker can determine whether an email is registered by observing which keys are rate-limited. By scoping rate limits to the client IP address, the system prevents this side-channel while maintaining effective brute-force protection.

### Rate Limiter Failure Behavior [HIGH-RISK]

The rate limiter depends on Redis. When Redis is unavailable, the system operates in one of two modes, configurable via the `RATE_LIMITER_FAIL_CLOSED` environment variable:

| Mode | Config Value | Behavior | Log Level | Use Case |
| --- | --- | --- | --- | --- |
| **Fail-open** | `RATE_LIMITER_FAIL_CLOSED=false` | Requests are allowed through when Redis is down | WARNING | Development, availability-first deployments |
| **Fail-closed** (default) | `RATE_LIMITER_FAIL_CLOSED=true` | Requests are rejected with HTTP 429 when the rate limiter cannot be initialized | CRITICAL | Production — prevents rate limit bypass during Redis outages |

**Health tracking:** Rate limiter health is tracked internally. When the rate limiter is disabled due to Redis unavailability, an error-level log is emitted with exception details.

> **Recommendation:** Use **fail-closed** mode in production to prevent attackers from exploiting Redis outages to bypass rate limits.

---

## File Upload Security

### Allowed Formats

| Format | MIME Type | Extension |
| --- | --- | --- |
| CSV | `text/csv` | `.csv` |
| Gzip-compressed CSV | `application/gzip`, `application/x-gzip` | `.csv.gz` |

### Validation Chain

1. **Frontend (UX):** `react-dropzone` filters by MIME type; extension check on filename.
2. **Backend (security boundary):**
   - MIME type detection from file content using `python-magic` (server-side content sniffing from first 2KB of file bytes — does not trust the client `Content-Type` header). Falls back to extension-based detection if `libmagic` is unavailable.
   - File extension validation (`.csv`, `.csv.gz`)
   - Maximum file size enforcement (cumulative byte tracking during streaming — applies even when the client does not provide `Content-Length`, preventing disk exhaustion attacks)
   - Rate limiting on upload endpoints

### File Lifecycle

1. File is uploaded to a temporary directory (via `platformdirs`)
2. File is parsed and processed (Polars)
3. Aggregated data is saved to PostgreSQL
4. **Temporary file is deleted** after processing (success or failure)

> **Critical:** Temporary files MUST always be deleted after processing. Failure to clean up may expose sensitive data on disk.

---

## SQL Injection Prevention

### Rules

- **All SQL queries** must be executed through parameterized queries (SQLAlchemy ORM/Core)
- **String interpolation** for SQL is strictly forbidden (no f-strings, no `.format()`, no concatenation)
- SQLAlchemy models and query builders are the only permitted interface to the database

### Enforcement

This is enforced at the code review level and by the project's linting/type-checking pipeline. The use of raw SQL via f-strings is flagged in `AGENTS.md` as a forbidden practice.

---

## CORS Configuration [HIGH-RISK]

CORS is configured on the backend with explicit allowed methods and headers. Wildcards are **not** used.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,  # From env var or app.yaml (default: localhost)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
```

### Constraints

- **`allow_origins`** must be explicitly configured in production — the application validates CORS configuration at startup and raises an error if origins are not set in production mode
- **No wildcard origins** (`*`) in production
- **Explicit method list:** Only `GET`, `POST`, `PUT`, `DELETE`, `PATCH`
- **Explicit header list:** Only `Authorization`, `Content-Type`, `Accept`

---

## Production Credential Enforcement [HIGH-RISK]

The application **refuses to start** in production mode if default credentials are detected:

| Variable | Default (dev) | Production Requirement |
| --- | --- | --- |
| `ADMIN_USERNAME` | `admin` | Must be explicitly set via environment variable |
| `ADMIN_PASSWORD` | `CHANGE_ME_ADMIN_PASSWORD` | Must be explicitly set; the shipped placeholder is rejected in production |
| `JWT__SECRET_KEY` | — | Must be explicitly set; Docker Compose uses `${JWT__SECRET_KEY:?...}` fail-if-unset syntax |
| `DATABASE__PASSWORD` | — | Must be explicitly set; same fail-if-unset pattern; placeholder validation only applies in production |

In development mode, default credentials are permitted but a **warning** is logged. The `DATABASE__PASSWORD` placeholder check (`postgres`, `password`, etc.) runs **only in production** to allow easier development database setup.

---

## Secrets Management

### Configuration Priority

Configuration is loaded from multiple sources (highest priority first):

1. Environment variables
2. Docker secrets (`_FILE` suffix)
3. `.env` file (development only)
4. `app.yaml` (non-sensitive settings only)
5. Defaults

### Secret Variables

The `_FILE` suffix pattern is honoured **only** for the five names below. Any other
`*_FILE` variable is skipped **without the file being read**: a name that resolves to a
real but non-secret field is ignored **with a warning** naming the variable and the
field (never the value), and a name that resolves to no field at all — `LOGGING__LOG_FILE`
strips to `LOGGING__LOG`, which addresses nothing — is skipped at debug level. A
path-valued or list-valued setting is therefore never read as a secret pointer.

| Variable | Description | `_FILE` name |
| --- | --- | --- |
| `DATABASE__PASSWORD` | Database password | `DATABASE__PASSWORD_FILE=/run/secrets/db_password` |
| `DATABASE__ADMIN_USER` | Database admin username | `DATABASE__ADMIN_USER_FILE=/run/secrets/db_admin_user` |
| `DATABASE__ADMIN_PASSWORD` | Database admin password | `DATABASE__ADMIN_PASSWORD_FILE=/run/secrets/db_admin_password` |
| `JWT__SECRET_KEY` | JWT signing key | `JWT__SECRET_KEY_FILE=/run/secrets/jwt_secret` |
| `REDIS__PASSWORD` | Redis password | `REDIS__PASSWORD_FILE=/run/secrets/redis_password` |

The honoured set is derived from `SECRET_FIELD_REGISTRY` in `src/mkobi/config.py` rather
than hand-written, so it cannot drift from the settings model. Note the double
underscore: `redis` is a nested model, so the single-underscore `REDIS_PASSWORD_FILE`
addresses no field.

- Nested variables use double underscore format: `DATABASE__HOST`, `DATABASE__PORT`, `JWT__SECRET_KEY`
- `app.yaml` contains **only non-sensitive** settings (hosts, ports, paths)

See [Configuration](../06-backend/configuration.md#docker-secrets-support) for the full
behaviour and the change that introduced the allow-list.

---

## Email Domain Blocklist

Registration requests are checked against a configurable email domain blocklist:

- Configured in `app.yaml` (backend)
- Validated on the backend via Pydantic (security boundary)
- Also validated on the frontend via Zod (UX convenience)
- Example blocked domains: `tempmail.com`, `throwawaymail.com`

---

## Password Security

- Passwords are stored as **bcrypt hashes** (never plaintext)
- **Backend strength validation:** Passwords must meet the following requirements, enforced by Pydantic `field_validator` on `ChangePasswordRequest.new_password` and `UserCreateRequest.password`:
  - Minimum length: 8 characters
  - At least one letter (`a-zA-Z`)
  - At least one digit (`0-9`)
- Frontend Zod schema also enforces these rules for UX (real-time feedback)
- Password change requires current password verification
- Users remain logged in after password change (token is not invalidated by password change alone)
- Registration approval generates a cryptographically random temporary password via `secrets.token_urlsafe(16)`

---

## JWT Security

- Tokens are signed and contain expiration (`exp` claim)
- Payload contains: `user_id`, `email`, `role`
- **Access tokens:** 15-minute expiration, stored in memory on the frontend (not in `localStorage` or cookies — XSS-safe)
- **Refresh tokens:** 7-day expiration, stored in httpOnly cookies (`mkobi_refresh_token`), set with `Secure`, `HttpOnly`, and `SameSite=Strict` attributes
- Axios interceptors attach the access token to every request and handle `401` responses by attempting a silent refresh

---

## Token Revocation

### Overview

Tokens can be immediately revoked before their natural expiration. This is implemented using a Redis-backed blacklist with auto-expiring entries, preventing indefinite growth.

### Revocation Triggers

| Trigger | Tokens Revoked | Mechanism |
| --- | --- | --- |
| `POST /api/v1/auth/logout` | Access token + refresh token | Both JTIs added to Redis blacklist with TTL = remaining token lifetime |
| User deactivation (`is_active=false`) | All future requests rejected | `get_current_user_dependency()` checks `is_active` on every request |

### Blacklist Details

- **Access token blacklist:** Redis key `token_blacklist:{jti}` with `SETEX` TTL = access token remaining seconds
- **Refresh token blacklist:** Redis key `refresh_token_blacklist:{jti}` with `SETEX` TTL = refresh token remaining seconds
- **Auto-expiry:** Blacklist entries expire automatically after the token would have expired naturally, preventing indefinite Redis growth
- **Auth check:** `is_token_revoked()` is called in `get_current_user_dependency()` on every authenticated request; `is_refresh_token_revoked()` is called during token refresh

### Security Properties

- Revoked tokens are rejected immediately with HTTP 401, even if they have not yet expired
- Both access and refresh tokens can be individually revoked
- The blacklist is checked before any business logic executes (in the auth dependency)
- If Redis is unavailable, the revocation check degrades gracefully (logged at WARNING level) — see [Rate Limiter Failure Behavior](#rate-limiter-failure-behavior-high-risk) for the general Redis degradation pattern

---

## Temporary Password Delivery

### Overview

The system uses a **retrieval-token pattern** for secure temporary password delivery. Instead of returning plaintext passwords in API responses, the backend stores passwords in Redis and returns a `retrieval_token` (UUID). The admin retrieves the password in a separate step via a one-time retrieval endpoint.

### TempPasswordStore

`TempPasswordStore` (`src/mkobi/core/temp_password_store.py`) provides Redis-backed one-time temporary password storage:

| Property | Value | Description |
| --- | --- | --- |
| Storage backend | Redis (`asyncio`) | Uses `redis.asyncio` pipeline for atomic operations |
| Key pattern | `temp_pwd:{token}` | Token-prefixed keys for namespacing |
| TTL | Configurable via `TEMP_PASSWORD_TTL_SECONDS` (default: 86400 = 24h, minimum: 60s) | Auto-expiring entries prevent indefinite Redis growth |
| Retrieval semantics | Atomic GET+DELETE via pipeline | Single-use: password is deleted upon retrieval |

### Operations

**`store(token, password)`** — Stores a temporary password under the given token with TTL. Fail-open on errors (logs but does not crash).

**`retrieve(token)`** — Atomically retrieves and deletes the password. Returns the password string on success, `None` if not found/expired/already retrieved. Graceful degradation on errors (returns `None`).

### Retrieval Flow

```
Admin Panel                    Backend                     Redis
    │                            │                           │
    │  POST /admin/users/:id/    │                           │
    │  reset-password            │                           │
    │───────────────────────────►│                           │
    │                            │  Generate UUID token     │
    │                            │  Generate temp password  │
    │                            │  Store bcrypt hash in DB │
    │                            │  temp_password_store.    │
    │                            │  store(token, password)  │
    │                            │──────────────────────────►│
    │                            │                           │
    │  200 OK                    │                           │
    │  { retrieval_token }       │                           │
    │◄───────────────────────────│                           │
    │                            │                           │
    │  Admin clicks "Show       │                           │
    │  Password"                 │                           │
    │  GET /admin/temp-          │                           │
    │  passwords/{token}         │                           │
    │───────────────────────────►│                           │
    │                            │  retrieve(token)         │
    │                            │  (atomic GET+DELETE)     │
    │                            │──────────────────────────►│
    │                            │                           │
    │                            │  password (or None)      │
    │                            │◄──────────────────────────│
    │  200 OK { temp_password }  │                           │
    │  (or 404 if expired/used)  │                           │
    │◄───────────────────────────│                           │
```

### Security Properties

- **No plaintext passwords in API logs**: Reset/approve endpoints return `retrieval_token`, not `temp_password`. Only the retrieval endpoint returns the plaintext password, in a separate API call that can be audited.
- **One-time use**: Passwords are deleted from Redis upon retrieval via atomic pipeline (GET+DEL in single transaction).
- **Auto-expiry**: Redis TTL ensures passwords don't persist indefinitely even if never retrieved.
- **No Redis log entries**: The plaintext password is never logged by the application.
- **Endpoints affected**: `POST /api/v1/admin/users/{id}/reset-password` and `POST /api/v1/admin/registration-requests/{id}/approve` — both return `retrieval_token` instead of `temp_password`.

### Configuration

| Variable | Default | Min | Description |
| --- | --- | --- | --- |
| `TEMP_PASSWORD_TTL_SECONDS` | `86400` (24h) | `60` | TTL for stored temporary passwords. Validated by Pydantic `field_validator`. |

---

## Cookie Security

The `mkobi_refresh_token` cookie is the cornerstone of the refresh token security model. It is used exclusively for storing the refresh token and has the following attributes:

| Attribute | Value | Purpose |
| --- | --- | --- |
| `HttpOnly` | `true` | Prevents JavaScript access, mitigating XSS-based token theft |
| `Secure` | `true` | Cookie is only sent over HTTPS, preventing interception on plaintext connections |
| `SameSite` | `Strict` | Cookie is not sent on cross-site requests, mitigating CSRF attacks |
| `Max-Age` | `604800` (7 days) | Refresh token lifetime |
| `Path` | `/` | Available to all API routes |

### Cookie Lifecycle

1. **Set on login:** `POST /api/v1/auth/login` sets the cookie via `Set-Cookie` header
2. **Read on refresh:** `POST /api/v1/auth/refresh` reads the cookie to obtain the refresh token
3. **Cleared on logout:** `POST /api/v1/auth/logout` sets `Max-Age=0` to clear the cookie
4. **Not accessible to JS:** The `HttpOnly` flag ensures client-side JavaScript cannot read or manipulate the cookie

### Backend Cookie Utilities

The `core/security.py` module provides `set_cookie()` and `delete_cookie()` helper functions that enforce consistent cookie attributes across all auth endpoints. All auth routes use these utilities instead of calling `Response.set_cookie()` directly.

---

## Security Headers Middleware

The FastAPI application includes a `SecurityHeadersMiddleware` that sets defense-in-depth HTTP security headers on every response. While nginx may also set these headers, the application-layer middleware provides protection even when nginx is not deployed or is misconfigured.

| Header | Value | Purpose |
| --- | --- | --- |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing attacks |
| `X-Frame-Options` | `DENY` | Prevents clickjacking by disallowing iframe embedding |
| `X-XSS-Protection` | `1; mode=block` | Enables browser XSS filter (legacy browsers) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer information leakage on cross-origin requests |

---

## Error Response Format

All API error responses follow a consistent format with a machine-readable `error_code` field. This enables programmatic error handling on the frontend and simplifies monitoring/alerting on the backend.

For detailed specification including complete ErrorCode reference table and example responses, see [Error Format](error-format.md).

### Standard Error Fields

```json
{
  "detail": "Human-readable error description",
  "error_code": "MACHINE_READABLE_CODE"
}
```

### Error Code Categories

| Category | HTTP Status | Example Codes |
| --- | --- | --- |
| Authentication | `401` | `HTTP_401`, `INVALID_TOKEN`, `USER_DEACTIVATED` |
| Authorization | `403` | `HTTP_403`, `PERMISSION_DENIED`, `ACCESS_DENIED` |
| Not Found | `404` | `HTTP_404`, `NOT_FOUND`, `DASHBOARD_NOT_FOUND` |
| Validation | `422` | `VALIDATION_ERROR`, `HTTP_422` |
| Rate Limit | `429` | `HTTP_429` |
| Server Error | `500` | `INTERNAL_ERROR`, `HTTP_500` |
| File Upload | `400`/`422` | `FILE_UPLOAD_ERROR` |

---

## Cross-References

- [Authentication API](../01-auth/auth-api.md) — Auth endpoint security, rate limiting details
- [Access Control](access-control.md) — Dashboard-level permission enforcement model
- [Error Format](error-format.md) — RFC 7807 error response format and ErrorCode reference
- [Frontend Security](../07-frontend/frontend-security.md) — JWT handling, CORS, file upload security
- [Configuration](../06-backend/configuration.md) — Secrets management, environment variables
- [Processing API](../03-processing/processing-api.md) — Upload security constraints and rate limiting
- [Client Error Reporting](client-error-reporting.md) — Frontend error logging endpoint for React Error Boundary and uncaught exceptions
