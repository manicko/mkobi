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
| `POST /api/v1/auth/login` | 5 attempts per 5 minutes per email, 50 per 5 minutes per peer | Per identifier and per peer |
| `POST /api/v1/auth/login/form` | 5 attempts per 5 minutes per email, 50 per 5 minutes per peer | Per identifier and per peer |
| `POST /api/v1/auth/refresh` | 10 attempts per 5 minutes per presented session (cookie digest), 100 per 5 minutes per peer | Per session and per peer |
| `POST /api/v1/auth/register-request` | 3 attempts per hour per email, 30 per hour per peer | Per identifier and per peer |
| `POST /api/v1/upload/:dashboard_id` | Configured via env | Per user |
| `POST /api/v1/upload/:dashboard_id/process` | Configured via env | Per user |

The refresh identifier is a digest of the presented cookie value, not the value itself, so no
credential is ever written into a rate-limit key.

### Dual Bound [HIGH-RISK]

Every auth site enforces two bounds at **different** thresholds: a per-identifier key **and** a
per-peer key (the client IP). The per-identifier bound stops credential guessing at one account;
the per-peer ceiling is a coarse abuse bound that a botnet cannot escape by rotating accounts. The
peer ceiling is **10x** the identifier bound at every site, so a shared-egress population (a NAT or
gateway) tolerates ten times one user's failures before the peer bound engages, instead of being
locked out when one user exhausts their own budget. Both bounds are enforced in one shared helper,
`_enforce_dual_rate_limit` in `src/mkobi/api/routes/auth.py`, with the key format defined once in
`_rate_limit_keys`; the 10x relationship is a stated ratio rather than three unrelated literals.

Because the identifier is the submitted email rather than the peer alone, a caller cannot infer
whether an address is registered by watching which key is rate-limited.

Two surfaces are **excluded** from the dual bound and keep their own single, peer-keyed limit:
`POST /api/v1/client-errors` and `POST /api/v1/upload/:dashboard_id`. They belong to a later phase
and are deliberately not migrated; `_rate_limit_keys` does not cover them.

A request whose client peer is absent or unparseable falls back to a shared `unknown` sentinel
bucket rather than raising — a malformed peer is still rate-limited and can never become a bypass.

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
   - MIME type detection from file content using `python-magic` (server-side content sniffing from first 2KB of file bytes — does not trust the client `Content-Type` header). `libmagic` is a **hard startup dependency**: `main.check_dependencies` refuses to start the backend when it is unavailable, so there is **no fallback** and a host without libmagic cannot start the backend. The accepted set is `MimeTypeEnum`'s members alone; the `UPLOAD__ALLOWED_MIME_TYPES` key and its unread property were removed.
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
- **A successful password change revokes the user's existing sessions.** The committed change
  invalidates the old credential, so every access and refresh token issued **at or before** it is
  refused on its next use. The revocation is a non-transactional Redis write placed **after** the
  service's commit — the same ordering `PATCH /admin/users/{user_id}/active` uses — so a rollback
  can never leave a live marker behind. A session minted **after** the change (by logging in again
  with the new password) is newer than the marker and works immediately, so this is a rotation,
  not a lock-out. See [Token Revocation](#token-revocation).
- Registration approval generates a cryptographically random 16-character temporary password
  (letters + digits, at least one of each) with `secrets.choice`

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
| `POST /api/v1/auth/logout` | Access token + refresh token | Both JTIs added to the per-`jti` Redis blacklist with TTL = remaining token lifetime |
| Password change (`POST /api/v1/auth/change-password`) | Every credential issued at or before the change | Timestamped user-level marker written **after** the service's commit |
| Admin password reset (`POST /api/v1/admin/users/{user_id}/reset-password`) | Every credential of the **target** issued at or before the reset | Same marker, same ordering |
| User deactivation (`is_active=false`) | Every credential issued at or before the deactivation, **plus every future request** | Same marker, plus the `is_active` checks on both token-issuing paths and on the protected gate |

### Two Blacklist Shapes

| Shape | Key | Value | Used by |
| --- | --- | --- | --- |
| Per-`jti` | `token_blacklist:{jti}`, `refresh_token_blacklist:{jti}` | literal `"revoked"` | Logout and explicit single-token revocation |
| Per-user marker | `user_tokens_revoked:{user_id}` | the epoch **millisecond** of the revocation | Password rotation and deactivation |

The marker is **not** a blanket lock-out. A credential is rejected only when its `iat` is **at or
before** the marker, so a token minted after the withdrawal works immediately and **no marker
clearing is needed** — including on the reactivate path, which never clears the marker. Two arms
**fail closed**: a marker value that is not an integer, and a credential with no usable `iat`. Both
are refused rather than admitted, so a rolling deploy that has not yet restarted cannot re-admit a
withdrawn session. Millisecond precision is load-bearing for the same reason: at one-second
granularity a re-login in the same second as the rotation would share the marker's instant and be
rejected by that comparison.

The marker TTL is `max(access_ttl, refresh_ttl)` — it only has to outlive the oldest credential
that can still be presented, and nothing issued after it is affected.

`POST /api/v1/auth/refresh` **rotates the refresh cookie** on every successful refresh. The
presented token's `jti` is deliberately **not** revoked, so a previous cookie stays usable until its
own TTL expires. Reuse detection (revoking the presented `jti` when a new one is minted) is
**not implemented**: it would add a server-side rejection path whose false positive — two tabs
refreshing concurrently — is a client concern. The per-`jti` blacklists are unchanged by any of this.

### Blacklist Details

- **Access token blacklist:** Redis key `token_blacklist:{jti}` with `SETEX` TTL = access token remaining seconds
- **Refresh token blacklist:** Redis key `refresh_token_blacklist:{jti}` with `SETEX` TTL = refresh token remaining seconds
- **Auto-expiry:** Blacklist entries expire automatically after the token would have expired naturally, preventing indefinite Redis growth
- **Auth check:** `is_token_revoked()` is called in `get_current_user_dependency()` on every authenticated request; `is_refresh_token_revoked()` and `is_user_tokens_revoked()` are called during token refresh

### Security Properties

- Revoked tokens are rejected immediately with HTTP 401, even if they have not yet expired
- Both access and refresh tokens can be individually revoked
- The blacklist is checked before any business logic executes (in the auth dependency)
- Rotating a credential withdraws **every** session the user holds, including the one that made the change. The caller must log in again with the new credential; that is the intended effect, not an oversight.

### Revocation-Read Failure Behavior [HIGH-RISK]

A fault reading the revocation store is a **dependency outage**, not a credential verdict. The readers `is_token_revoked`, `is_refresh_token_revoked`, and `is_user_tokens_revoked` (`src/mkobi/core/security.py`) raise a dedicated `RevocationStoreUnavailableError` when the store cannot be read; callers map that to `503 SERVICE_UNAVAILABLE`. The direction is **fail-closed** — a Redis outage never silently re-admits a revoked session — but the outcome is distinguishable from a refusal:

| Path | Store healthy | Store fault |
| --- | --- | --- |
| Protected request (`get_current_user_dependency`) | 401 `TOKEN_REVOKED` if revoked, otherwise proceeds | 503 `SERVICE_UNAVAILABLE` |
| `POST /api/v1/auth/refresh` | 401 `TOKEN_REVOKED` if revoked, otherwise proceeds | 503 `SERVICE_UNAVAILABLE` |

> A Redis outage therefore produces **`503`, not a mass `401`**. Converting a store fault into `401` would turn a Redis degradation into an API-wide sign-out, because the SPA answers any `401` with a silent refresh and, on failure, a sign-out back to `/login`. The "cannot answer" case must never be blurred into "the answer is no". The value semantics of the readers are unchanged: the per-`jti` readers keep their literal `"revoked"` + `exists` semantics, and the user-level marker keeps its timestamped comparison with both fail-closed arms.

### Account Deactivation

`is_active` is authoritative on **both token-issuing paths**, not only on the protected gate:

- `POST /api/v1/auth/login` and `POST /api/v1/auth/login/form` — `AuthService.login_user` refuses a
  deactivated row by returning `None`, exactly as it does for a wrong password. The route turns that
  `None` into `401 AUTHENTICATION_FAILED` with the existing detail `"Invalid credentials"`, so a
  deactivated account is **not** an account-existence oracle and no freshly signed token is ever
  issued for it. The Redis marker is deliberately not consulted at login.
- `POST /api/v1/auth/refresh` — the row is re-read and compared **after** the Redis marker branch,
  which keeps its `401 TOKEN_REVOKED` contract byte-identically. A deactivated-and-marked user
  therefore always sees the revocation verdict; a deactivated user whose marker has expired or been
  flushed is refused with `AUTHENTICATION_FAILED` / `"User account is deactivated"` — the same
  detail the protected gate uses.
- Every protected endpoint — `get_current_user_dependency` re-reads the row on every request and
  raises `401 AUTHENTICATION_FAILED` / `"User account is deactivated"`.

Which surface consults which authority is tabulated in
[Backend Architecture → Account Deactivation: The Database Row Is Authoritative](../06-backend/architecture.md#account-deactivation-the-database-row-is-authoritative).

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
| Retrieval semantics | Atomic GET+DELETE inside one `pipeline(transaction=True)` | Single-use: the password is deleted on retrieval. The one-winner outcome is structural — Redis's MULTI/EXEC decides the race. The in-process test runs against a fake that does not model transactions and so cannot fail by construction; a separate integration test observes the guarantee against a real server and **skips** when one is not available. |

### Operations

The two operations deliberately differ, because by the time a **write** runs the caller has already
committed a real credential, and a **read** costs nothing to surface.

**`store(token, password) -> bool`** — Stores a temporary password under the given token with TTL.
**Fails open**: it never raises. It returns `true` when the `SET` completed without a client-visible
Redis error, and `false` when a fault was caught and swallowed. `true` is **not** proof that the
value is durable and readable.

**`retrieve(token) -> str | None`** — Atomically retrieves and deletes the password. Returns the
password on success, `None` if the key is absent, already spent, or expired. **Fails loud**: a store
fault raises `TempPasswordStoreUnavailableError` (a plain `Exception` declared in
`core/temp_password_store.py`, so the store never imports the API or the error-enum layer) rather
than degrading to `None`. The retrieval route maps that exception to **`503 SERVICE_UNAVAILABLE`**,
while a missing, spent or expired key answers **`404`**. Reporting "not found" during an outage
would be a lie the caller cannot detect; a caller that wants the fail-open behaviour must ask for it
by handling the exception.

### `credential_stored`

Both credential-issuing operations — `AuthService.reset_password_admin` and
`AuthService.approve_registration_request` — propagate the store's verdict to the caller as a
`credential_stored` key in the `200` response body, and log an `ERROR` naming the affected user and
the administrator when it is `false`. `false` covers **both** a swallowed Redis fault **and** the
case where no store was wired at all.

| `credential_stored` | Meaning |
| --- | --- |
| `true` | The `SET` completed. The returned `retrieval_token` should work. |
| `false` | The write faulted, or no store was wired. **The returned token is not a working handle** — the account exists with a credential nobody can read, and the reset must be repeated. |

**The status stays `200`.** The status describes the password change, which is committed and
durable either way; the credential handoff is a separate, non-transactional side effect performed
after that commit. `credential_stored` **reports** the failed handoff; it does not **prevent** it.
An administrator can still hold a retrieval token for a credential that was never stored.

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
    │                            │  COMMIT                  │
    │                            │  temp_password_store.    │
    │                            │  store(token, password)  │
    │                            │──────────────────────────►│
    │                            │                           │
    │  200 OK                    │                           │
    │  { retrieval_token,        │                           │
    │    credential_stored }     │                           │
    │◄───────────────────────────│                           │
    │                            │                           │
    │  Admin clicks "Show       │                           │
    │  Password"                 │                           │
    │  POST /admin/temp-         │                           │
    │  passwords                │                           │
    │  { retrieval_token }       │                           │
    │───────────────────────────►│                           │
    │                            │  retrieve(token)         │
    │                            │  (atomic GET+DELETE)     │
    │                            │──────────────────────────►│
    │                            │                           │
    │                            │  password (or None)      │
    │                            │◄──────────────────────────│
    │  200 OK { temp_password }  │                           │
    │  (404 absent/spent/expired,│                           │
    │   503 store fault)         │                           │
    │◄───────────────────────────│                           │
```

The handle is carried in the **request body** of `POST /api/v1/admin/temp-passwords`, so it never
appears in the request line and therefore never reaches the **application's** access log. The legacy
`GET /api/v1/admin/temp-passwords/{retrieval_token}` still serves and is marked **deprecated**, with
removal named for release **1.0.9**. Both operations share one implementation, so their `403` /
`404` / `503` behaviour is identical.

### Security Properties

- **No plaintext passwords in API logs**: Reset/approve endpoints return `retrieval_token`, not `temp_password`. Only the retrieval endpoint returns the plaintext password, in a separate API call that can be audited.
- **One-time use**: Passwords are deleted from Redis upon retrieval via atomic pipeline (GET+DEL in single transaction).
- **Auto-expiry**: Redis TTL ensures passwords don't persist indefinitely even if never retrieved.
- **No Redis log entries**: The plaintext password is never logged by the application. Only the handle's first eight characters are logged, and a prefix is not a replayable handle.
- **Commit-then-store ordering**: The Redis write happens **after** the database commit that makes the credential real. A credential written first would survive a database rollback and unlock a password for a user that does not exist; the chosen order inverts that into a recoverable state.
- **Endpoints affected**: `POST /api/v1/admin/users/{id}/reset-password` and `POST /api/v1/admin/registration-requests/{id}/approve` — both return `retrieval_token` instead of `temp_password`.
- **Partially fixed at the proxy**: The retrieval handle no longer reaches the application's request line, but `docker/nginx/nginx.conf` declares no `log_format` and writes the full request line to its **own** access log in the default `combined` format, so a legacy `GET` path still appears there. That file belongs to another phase; this is recorded as a hand-over, not as a closed finding.

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
3. **Rotated on every successful refresh:** the same response sets a **new** refresh cookie. The presented token is not revoked, so a superseded cookie stays usable until its own TTL — see [Token Revocation](#token-revocation) for why reuse detection is absent.
4. **Cleared on logout:** `POST /api/v1/auth/logout` sets `Max-Age=0` to clear the cookie. `POST /api/v1/auth/refresh` also clears it when the user-level marker refuses the presented token.
5. **Not accessible to JS:** The `HttpOnly` flag ensures client-side JavaScript cannot read or manipulate the cookie

### Backend Cookie Utilities

The `core/security.py` module provides `set_secure_cookie()` and `delete_secure_cookie()` helper functions that enforce consistent cookie attributes across all auth endpoints. All auth routes use these utilities instead of calling `Response.set_cookie()` directly.

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

All API error responses follow the RFC 7807 Problem Details format with a machine-readable `code`
field. This enables programmatic error handling on the frontend and simplifies
monitoring/alerting on the backend.

[Error Format](error-format.md) is the single source of truth for the format and the complete
`ErrorCode` reference table.

### Standard Error Fields

```json
{
  "type": "https://api.mkobi.com/errors/authentication_failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "User account is deactivated",
  "code": "AUTHENTICATION_FAILED"
}
```

### Error Code Categories

Every code below is a member of `ErrorCode` in `src/mkobi/models/enums.py`; the HTTP status is
derived from it by `_ERROR_CODE_STATUS_MAP` in `src/mkobi/utils/exceptions.py`. A deactivated
account is **not** a separate code — it is `AUTHENTICATION_FAILED`, and at `POST /auth/login` it is
indistinguishable from a wrong password because both share the detail `"Invalid credentials"`.

| Category | HTTP Status | Example Codes |
| --- | --- | --- |
| Authentication | `401` | `AUTHENTICATION_FAILED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `TOKEN_REVOKED` |
| Authorization | `403` | `PERMISSION_DENIED`, `INSUFFICIENT_PERMISSIONS`, `ACCESS_DENIED` |
| Not Found | `404` | `NOT_FOUND`, `USER_NOT_FOUND`, `DASHBOARD_NOT_FOUND` |
| Validation | `422` | `VALIDATION_ERROR`, `INVALID_EMAIL`, `INVALID_PASSWORD` |
| Rate Limit | `429` | `RATE_LIMIT_EXCEEDED` |
| Dependency Outage | `503` | `SERVICE_UNAVAILABLE` |
| Server Error | `500` | `INTERNAL_ERROR`, `PROCESSING_FAILED` |
| File Upload | `400`/`413`/`415` | `FILE_UPLOAD_ERROR`, `FILE_TOO_LARGE`, `INVALID_FILE_TYPE` |
| Conflict | `409` | `EMAIL_ALREADY_EXISTS`, `DUPLICATE_RESOURCE` |

---

## Cross-References

- [Authentication API](../01-auth/auth-api.md) — Auth endpoint security, rate limiting details
- [Access Control](access-control.md) — Dashboard-level permission enforcement model
- [Error Format](error-format.md) — RFC 7807 error response format and ErrorCode reference
- [Frontend Security](../07-frontend/frontend-security.md) — JWT handling, CORS, file upload security
- [Configuration](../06-backend/configuration.md) — Secrets management, environment variables
- [Processing API](../03-processing/processing-api.md) — Upload security constraints and rate limiting
- [Client Error Reporting](client-error-reporting.md) — Frontend error logging endpoint for React Error Boundary and uncaught exceptions
