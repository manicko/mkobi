---
id: auth-api
domain: auth
tags:
  - authentication
  - jwt
  - login
  - registration
  - rate-limiting
  - password
  - security
  - cookies
  - refresh-tokens
  - token-revocation
  - password-validation
related:
  - security-overview
  - access-control
  - admin-api
  - frontend-auth-flow
---

# Authentication API

## Overview

The authentication API provides endpoints for user login, registration, token management, password changes, and logout. All endpoints are part of the `/api/v1/auth` route group.

**Authentication method:** JWT (JSON Web Token) with bcrypt password hashing. Access tokens are short-lived (15 minutes) and stored in memory on the frontend. Refresh tokens are long-lived (7 days) and stored in httpOnly cookies. See [Frontend Auth Flow](../07-frontend/auth-flow.md) for token storage strategy and login flow details.

**Base path:** `/api/v1/auth`

---

## Endpoints

### 1. Login

Authenticate a user by email and password.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/login`                       |
| **Auth level** | Public                                     |
| **Rate limit** | 5 attempts per 5 minutes per email, **50** per 5 minutes per IP (10x the identifier bound) |

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "secure_password123"
}
```

**Response** (`200 OK`):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "role": "viewer",
    "display_name": "user",
    "force_password_change": false,
    "created_at": "2026-04-24T16:02:46+03:00"
  }
}
```

> The login response includes the full user profile (`TokenWithUser` model), eliminating the need for a separate `/auth/me` call after login. The `display_name` field is computed from the email prefix (text before `@`). The `force_password_change` field indicates whether the user must change their password on next login — when `true`, the frontend redirects to `/profile/change-password?force=true`.

> **Server-side enforcement:** `force_password_change` is enforced by the **server**, not only by the frontend. The flag is evaluated in `get_current_user_dependency()` (the single dependency every protected route passes through, `src/mkobi/api/deps.py`) **after** the `is_active` check. A flagged user is refused on any protected route **outside the allow-list** with `403 PERMISSION_DENIED`. `403` is deliberate: the SPA's axios interceptor answers any `401` with a silent refresh and, on failure, a sign-out back to `/login`, so a `401` refusal would become a redirect loop. The allow-list is enumerated from the auth router and kept reachable for a flagged user:
>
> | Route | Reason |
> | --- | --- |
> | `POST /api/v1/auth/change-password` | The only way to complete the change; without it the user is trapped |
> | `POST /api/v1/auth/refresh` | Keeps the SPA's silent refresh working, so the user is redirected rather than signed out |
> | `POST /api/v1/auth/logout` | Lets a trapped user leave |
> | `GET /api/v1/auth/me` | Carries the flag to the SPA, which is how the frontend decides to redirect |
>
> The allow-list is expressed by the named predicate `is_password_change_completion_path(method, path)`, which is unit-tested directly without a request pipeline. The flag is read from the already-loaded `UserRead`, so no extra database query is added.

> **Cookie:** On success, the server also sets an httpOnly cookie `mkobi_refresh_token` containing the refresh token (7-day TTL). The cookie uses `Secure`, `HttpOnly`, and `SameSite=Strict` attributes.

**Error responses:**

| Status | Condition            | Detail                       |
| ------ | -------------------- | ---------------------------- |
| `401`  | Invalid credentials  | `Invalid credentials`        |
| `429`  | Rate limit exceeded  | `Too many login attempts...` |

> **A deactivated account is not distinguishable from a wrong password.** `AuthService.login_user`
> returns `None` for both, and `_handle_login` turns that single `None` into the `401
> AUTHENTICATION_FAILED` above. The Redis revocation marker is deliberately **not** consulted here;
> `is_active` alone decides, so no freshly signed token is ever issued for a deactivated row and the
> response cannot be used to enumerate accounts.

---

### 2. Login (OAuth2 Form)

Authenticate a user via OAuth2 password flow (form-encoded).

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/login/form`                  |
| **Auth level** | Public                                     |
| **Rate limit** | 5 attempts per 5 minutes per email, **50** per 5 minutes per IP (10x the identifier bound) |

**Request:** `application/x-www-form-urlencoded` with `username` (email) and `password` fields.

**Response** (`200 OK`): Same as [Login](#1-login), including the `user` field and the `mkobi_refresh_token` cookie.

---

### 3. Registration Request

Submit a registration request for a new account. The request must be approved by an admin before the user can log in.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/register-request`            |
| **Auth level** | Public                                     |
| **Rate limit** | 3 attempts per hour per email, **30** per hour per IP (10x the identifier bound) |

**Request body:**

```json
{
  "email": "user@example.com"
}
```

**Response** (`201 Created`):

```json
{
  "message": "Request submitted",
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Error responses:**

| Status | Condition                        | Detail                                  |
| ------ | -------------------------------- | --------------------------------------- |
| `422`  | Email already registered         | Validation error message                |
| `422`  | Email domain blocklisted         | Validation error message                |
| `429`  | Rate limit exceeded              | `Too many registration requests...`     |

**Side effects:**
- Creates a row in the `registration_requests` table with status `pending`
- Records the requester's IP address (`requested_by_ip`)

---

### 4. Register (Admin Only)

Directly create a new user account. Requires admin role. This endpoint is deprecated for public use — public users should use `/auth/register-request` instead.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/register`                    |
| **Auth level** | Admin                                      |

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "secure_password123",
  "role": "viewer"
}
```

**Response** (`201 Created`):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `422`  | Validation error             | Error message                |
| `500`  | Registration/token error     | `Registration error`         |

---

### 5. Refresh Token

Refresh an expired or soon-to-expire JWT access token using the httpOnly refresh cookie.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/refresh`                     |
| **Auth level** | Public (requires valid refresh cookie)     |
| **Rate limit** | 10 attempts per 5 minutes per presented session (cookie digest), **100** per 5 minutes per IP (10x the identifier bound) |

**Request:** The refresh token is read from the `mkobi_refresh_token` httpOnly cookie. No request body is needed.

> **Security:** The refresh token is stored in an httpOnly cookie, making it inaccessible to JavaScript and resistant to XSS-based token theft. The cookie is set with `Secure`, `HttpOnly`, and `SameSite=Strict` attributes.

**Response** (`200 OK`):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

The response also sets a **new** `mkobi_refresh_token` cookie: the refresh cookie is **rotated on every refresh**. The presented token is **not** revoked, so the previous cookie remains usable until its own 7-day TTL. This bounds nothing beyond the token's own lifetime — reuse detection (revoking the presented `jti` when a new one is minted) is deliberately **not** implemented.

**Error responses:**

| Status | Condition                    | Code                        | Detail                       |
| ------ | ---------------------------- | --------------------------- | ---------------------------- |
| `401`  | Missing refresh cookie       | `AUTHENTICATION_FAILED`     | `Refresh token not found`    |
| `401`  | Invalid or expired cookie    | `INVALID_TOKEN`             | `Invalid token`              |
| `401`  | User no longer exists        | `AUTHENTICATION_FAILED`     | `User not found`             |
| `401`  | Revoked refresh token        | `TOKEN_REVOKED`             | `Refresh token has been revoked` |
| `401`  | Credential predates the user's revocation marker | `TOKEN_REVOKED` | `Token has been revoked` |
| `401`  | Account deactivated          | `AUTHENTICATION_FAILED`     | `User account is deactivated` |
| `429`  | Either rate-limit bound exceeded | `RATE_LIMIT_EXCEEDED` | `Too many refresh attempts. Try again later.` |
| `503`  | Revocation store unreachable | `SERVICE_UNAVAILABLE`       | `Authentication service is temporarily unavailable` |

**Behavior:**
- Reads the refresh token from the `mkobi_refresh_token` cookie
- Validates the JWT signature and expiration
- Checks the per-`jti` refresh blacklist, then re-reads the user row, then compares the credential's `iat` against the user's timestamped revocation marker, then compares `is_active`
- Issues a new access token with fresh 15-minute expiration
- Mints a new refresh token and sets it as the rotated `mkobi_refresh_token` cookie; the presented token is not revoked
- A refusal at the marker step also clears the refresh cookie; a refusal at the `is_active` step does not

> **Ordering is deliberate.** The marker branch runs **before** the `is_active` comparison, so a
> deactivated-and-marked user keeps receiving `TOKEN_REVOKED` byte-identically. The `is_active` check
> exists to refuse a deactivated row whose marker has expired, been flushed, or never existed —
> without it, deactivation would depend entirely on a Redis key. See
> [Backend Architecture → Account Deactivation: The Database Row Is Authoritative](../06-backend/architecture.md#account-deactivation-the-database-row-is-authoritative).
>
> **A store fault is not a verdict.** If the revocation store cannot be *read*, the endpoint answers
> `503 SERVICE_UNAVAILABLE`, never `401`. Blurring "cannot answer" into "the answer is no" would turn
> a Redis degradation into an API-wide sign-out.

---

### 6. Logout

Log out the current user by clearing the refresh token cookie.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/logout`                      |
| **Auth level** | Any authenticated user                     |

**Request:** Requires valid JWT access token in the `Authorization` header.

**Response** (`200 OK`):

```json
{
  "message": "Logged out successfully"
}
```

**Side effects:**
- Revokes the access token by adding its `jti` to a Redis-backed blacklist (auto-expiring after the token's remaining TTL)
- Revokes the refresh token by adding its `jti` to a separate Redis-backed blacklist (auto-expiring after the refresh token's remaining TTL)
- Clears the `mkobi_refresh_token` cookie
- The frontend also clears the in-memory access token

> Once revoked, the token is immediately rejected on any subsequent authenticated request, even if it has not yet expired. See [Token Revocation](../08-security/security-overview.md#token-revocation) for details.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `401`  | Invalid or missing token     | Unauthorized                 |

---

### 7. Get Current User

Retrieve the currently authenticated user's profile.

> **Note:** This endpoint is retained for backward compatibility. The preferred approach is to use the `user` field returned directly in the login response, which avoids an extra round-trip.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `GET`                                      |
| **Path**       | `/api/v1/auth/me`                          |
| **Auth level** | Any authenticated user                     |

**Request:** Requires `Authorization: Bearer <token>` header.

**Response** (`200 OK`):

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "role": "viewer",
  "display_name": "user",
  "force_password_change": false,
  "created_at": "2026-04-24T16:02:46+03:00"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `401`  | Invalid or missing token     | Unauthorized                 |

---

### 8. Change Password

Change the current user's password.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/auth/change-password`             |
| **Auth level** | Any authenticated user                     |

**Request body:**

```json
{
  "current_password": "old_password123",
  "new_password": "new_secure_password456",
  "confirm_password": "new_secure_password456"
}
```

**Response** (`200 OK`):

```json
{
  "message": "Password changed successfully"
}
```

**Error responses:**

| Status | Condition                              | Code                     | Detail                                   |
| ------ | -------------------------------------- | ------------------------ | ---------------------------------------- |
| `422`  | Confirmation mismatch                  | `VALIDATION_ERROR`       | `Passwords do not match`                 |
| `422`  | New password below the strength floor  | `VALIDATION_ERROR`       | Error message                            |
| `401`  | Current password incorrect             | `AUTHENTICATION_FAILED`  | Error message                            |
| `500`  | Server error                           | `INTERNAL_ERROR`         | `Password change error`                  |

The confirmation check is a Pydantic `model_validator` on `ChangePasswordRequest`, so a mismatch is a
request-validation failure and therefore `422`, not `400`.

**Notes:**
- A successful password change records a **timestamped revocation** for the user: every access and refresh token issued **at or before** the change is refused with a revocation error, so all other devices are signed out too. A session minted **after** the change (that is, by logging in again with the new password) is unaffected and works normally. The marker is not a blanket lock-out; re-login restores access. **The caller's own session is revoked too** — including the one that made the change — so the SPA must log in again with the new password.
- The marker is written **after** the service's commit, not before. The revocation is a non-transactional Redis write, so the reverse order would leave a live marker behind on a password change that then rolled back. `PATCH /admin/users/{id}/active` uses the same ordering.
- Two cases **fail closed**: a marker value that is not an integer, and a credential with no usable `iat` claim. Both are refused rather than admitted, so a rolling deploy that has not yet restarted cannot re-admit a withdrawn session. No marker clearing is ever required.
- The same revocation applies to the admin reset (`POST /api/v1/admin/users/{user_id}/reset-password`): the **target** user's tokens issued before the reset are revoked once it is committed, in addition to the temporary-password handoff described in [Admin API](../04-admin/admin-api.md#6-reset-user-password-admin). Account **deactivation** uses the same marker but is persistent — the `is_active` checks reject any later session until the account is reactivated.
- New password must meet backend strength requirements: at least 8 characters, at least one letter, and at least one digit. Enforced by Pydantic `field_validator` — returns 422 if requirements are not met. The frontend change-password form additionally requires an **uppercase** letter; a password the API would accept may be refused in the browser.
- The `force_password_change` flag is automatically cleared on the backend after a successful password change. This prevents an infinite force-change loop when a user is required to change their password (e.g., after admin reset or registration approval).
- While `force_password_change` is `true`, the server refuses every protected route except the allow-list (`change-password`, `refresh`, `logout`, `me`) with `403 PERMISSION_DENIED`. After the password change clears the flag (and following a fresh login, which the timestamped revocation requires), normal access resumes.
- If the user was in force-change mode (redirected via `?force=true`), they are redirected back to `/profile` after successfully changing their password.

---

## Login Flow

```
Browser                          FastAPI
  │                                │
  │  POST /api/v1/auth/login       │
  │  { email, password }           │
  │ ──────────────────────────────►│
  │                                │ ┌─────────────────────────┐
  │                                │ │ Rate limit check         │
  │                                │ │ (5 / 5 min per email,    │
  │                                │ │  50 / 5 min per IP)      │
  │                                │ └───────────┬─────────────┘
  │                                │             │
  │                                │ ┌───────────▼─────────────┐
  │                                │ │ Verify email exists      │
  │                                │ │ Check bcrypt hash        │
  │                                │ │ Check is_active          │
  │                                │ └───────────┬─────────────┘
  │                                │             │
  │                                │ ┌───────────▼─────────────┐
  │                                │ │ Create access token (15m)│
  │                                │ │ Create refresh token (7d)│
  │                                │ └───────────┬─────────────┘
  │                                │             │
  │  200 OK                        │             │
  │  { access_token, token_type,   │             │
  │    user: { ... } }             │             │
  │  + Set-Cookie: mkobi_refresh_  │             │
  │    token=...; HttpOnly; Secure │             │
  │ ◄──────────────────────────────│             │
  │                                │
  │  Store access token in memory  │
  │  Set user in useAuth state     │
  │  Redirect to /dashboards       │
```

1. User submits email and password via the login form (`/login` page)
2. Server applies rate limiting (5 attempts per 5-minute window per email; the shared-IP ceiling is 50 per 5-minute window)
3. Server looks up user by email, verifies the bcrypt password hash, and refuses a deactivated row with the same `401` a wrong password produces
4. On success, server creates a JWT access token (15-minute expiration) and a refresh token (7-day expiration)
5. Server sets the refresh token as an httpOnly cookie (`mkobi_refresh_token`) with `Secure`, `HttpOnly`, and `SameSite=Strict` attributes
6. Server returns `TokenWithUser` — the access token plus the full user profile (including computed `display_name` and `force_password_change` flag)
7. Client stores the access token in memory and sets user state immediately (no separate `/me` call needed)
8. **If `force_password_change` is `true`:** Client redirects to `/profile/change-password?force=true`
9. **Otherwise:** Client redirects to the dashboard list page

---

## Token Refresh Flow

```
Browser                          FastAPI
  │                                │
  │  POST /api/v1/auth/refresh     │
  │  Cookie: mkobi_refresh_token=… │
  │ ──────────────────────────────►│
  │                                │ ┌─────────────────────────┐
  │                                │ │ Read refresh cookie      │
  │                                │ │ Validate JWT signature   │
  │                                │ │ Check expiration         │
  │                                │ │ Check per-jti blacklist  │
  │                                │ │ Verify user exists in DB │
  │                                │ │ Compare the credential   │
  │                                │ │   against the revocation │
  │                                │ │   marker, then is_active │
  │                                │ └───────────┬─────────────┘
  │                                │             │
   │  200 OK                        │             │
   │  { access_token, token_type }  │             │
   │  + Set-Cookie: mkobi_refresh_  │             │
   │    token=<new> (rotated)       │             │
   │ ◄──────────────────────────────│             │
   │                                │
   │  Replace access token in memory│
   │  Replace refresh cookie        │
   │  Retry original request        │
```

---

## Logout Flow

```
Browser                          FastAPI
  │                                │
  │  POST /api/v1/auth/logout      │
  │  Authorization: Bearer …       │
  │ ──────────────────────────────►│
  │                                │ ┌─────────────────────────┐
  │                                │ │ Validate access token    │
  │                                │ │ Revoke both JTIs         │
  │                                │ │ Clear refresh cookie     │
  │                                │ └───────────┬─────────────┘
  │                                │             │
  │  200 OK                        │             │
  │  { "Logged out successfully" } │             │
  │  + Set-Cookie: mkobi_refresh_  │             │
  │    token=; Max-Age=0           │             │
  │ ◄──────────────────────────────│             │
  │                                │
  │  Clear access token from memory│
  │  Redirect to /login            │
```

---

## Registration Flow

```
Browser              FastAPI              Database
  │                    │                    │
  │  POST /register-   │                    │
  │  request { email } │                    │
  │ ──────────────────►│                    │
  │                    │  Rate limit check  │
  │                    │  (3/hour per email,│
  │                    │   30/hour per IP)  │
  │                    │                    │
  │                    │  Validate email    │
  │                    │  Check blocklist   │
  │                    │                    │
  │                    │  INSERT            │
  │                    │───────────────────►│
  │                    │  registration_     │
  │                    │  requests          │
  │                    │  (status=pending)  │
  │                    │◄───────────────────│
  │                    │                    │
  │  201 Created       │                    │
  │  { message, id }   │                    │
  │ ◄──────────────────│                    │
  │                    │                    │
  │  User waits for    │                    │
  │  admin approval    │                    │
  │                    │                    │
  │         Admin Panel│                    │
  │         POST /admin/registration-       │
  │         requests/:id/approve            │
  │                    │───────────────────►│
  │                    │  Create user       │
  │                    │  Update request    │
  │                    │  (status=approved) │
  │                    │◄───────────────────│
  │                    │                    │
  │  Admin receives    │                    │
  │  retrieval_token   │                    │
  │  via response      │                    │
  │                    │                    │
  │  Admin retrieves   │                    │
  │  temp_password via │                    │
  │  POST /admin/temp- │                    │
  │  passwords         │                    │
  │  (handle in body)  │                    │
  │  and communicates  │                    │
  │  it to new user    │                    │
```

1. User submits their email on the registration page (`/register`)
2. Server applies rate limiting (3 requests per hour per email; the shared-IP ceiling is 30 per hour)
3. Server validates the email format and checks against the domain blocklist
4. Server creates a `registration_requests` record with status `pending`
5. Admin reviews pending requests via the admin panel (`/admin`)
6. Admin approves the request — a user account is created with a random temporary password
7. The user's `force_password_change` flag is set to `True`, requiring them to change their password on first login
8. The response includes a `retrieval_token` (UUID) instead of the plaintext password, plus `credential_stored`
9. Admin retrieves the temporary password via `POST /api/v1/admin/temp-passwords` with `{ "retrieval_token": "…" }` in the request body (one-time, admin only). A `credential_stored` of `false` means the token will not work and the approval must be repeated.
10. Admin communicates the temporary password to the new user
11. New user logs in and is redirected to `/profile/change-password?force=true` to set a new password

---

## Security Constraints

- **Password hashing:** bcrypt (never stored in plaintext)
- **Password strength validation (backend):** Passwords must be at least 8 characters and contain at least one letter and one digit. Enforced by Pydantic `field_validator` on `ChangePasswordRequest.new_password` and `UserCreateRequest.password` — rejects weak passwords at the model level before they reach the service layer. **The frontend form is stricter than the backend:** its Zod schema additionally requires at least one **uppercase** letter (`/[A-Z]/`). Since `AUTH-003` made that form the only path forward for a flagged user, a password that satisfies the backend rule but lacks an uppercase letter is accepted by the API yet rejected in the browser. The backend rule is the weaker of the two and the one that actually governs the API surface.
- **JWT:** Signed tokens with expiration; payload contains `user_id`, `email`, `role`. Access tokens expire after **15 minutes**.
- **Refresh tokens:** Stored in httpOnly cookies (`mkobi_refresh_token`) with `Secure`, `HttpOnly`, and `SameSite=Strict` attributes. 7-day expiration. Not accessible to JavaScript.
- **Token revocation:** Redis-backed blacklist with auto-expiring entries. Revoked tokens are rejected immediately, even if they have not expired. Logout revokes both access and refresh tokens. A successful **password change** and an **admin password reset** record a timestamped revocation that rejects tokens issued at or before it, so other sessions must log in again while a fresh login works. On **refresh**, the refresh cookie is rotated but the presented token is not revoked. See [Token Revocation](../08-security/security-overview.md#token-revocation) for details.
- **Rate limiting:** Redis-based and **fail-closed by default** (`Settings.rate_limiter_fail_closed` defaults to `True`; set `RATE_LIMITER_FAIL_CLOSED=false` for fail-open). Every auth site enforces **two bounds at different thresholds**: one keyed on the client **peer** (IP) and one keyed on an **identifier** — a digest of the submitted value, never the raw value. For `login` and `register-request` the identifier is the submitted email, so the identifier bound **is** the security control (it stops credential guessing at one account). For `refresh` the identifier is a digest of the presented cookie, a value a guessing attacker can vary freely, so the identifier bound there is **not** a per-account control and the effective bound is the **peer ceiling**. That residual is real and is scoped explicitly: `refresh` admits **100** failed attempts per 5 minutes per peer, up from 10 before AB-6 — a 10× widening of the effective guess ceiling on that one site, bounded by the peer. The identifier key is a SHA-256 digest (`_identifier_digest`), so no email address or cookie is written into a Redis key. The peer bound is a **coarse abuse ceiling** (rotating accounts cannot escape it) and is deliberately **10x** the identifier bound so a shared-egress population tolerates ten times one user's failures before it engages. The ratio, rather than three unrelated literals, makes the relationship legible and the tuning reviewable. Thresholds: `login` 5/300 s per identifier, **50/300 s** per peer; `refresh` 10/300 s per identifier, **100/300 s** per peer; `register-request` 3/3600 s per identifier, **30/3600 s** per peer. The key derivation lives in one place (`_rate_limit_keys` in `src/mkobi/api/routes/auth.py`); `client_errors.py` and `upload.py` are out of scope and derive their peer keys separately.
- **Email blocklist:** Configurable domain blocklist for registration requests
- **CORS:** Explicit allowed methods and headers (no wildcards in production)
- **Production credentials:** Default credentials (`admin`/`admin`) are rejected in production
- **User deactivation:** Deactivated users (`is_active=false`) are refused on **all three** paths. On any protected endpoint the check in `get_current_user_dependency()` runs on every request and answers `401` with detail `"User account is deactivated"`. At `POST /auth/login` (and `/login/form`) `AuthService.login_user` refuses the row exactly as it refuses a wrong password, so the client sees `401 AUTHENTICATION_FAILED` with the shared detail `"Invalid credentials"` — a deactivated account is not an account-existence oracle, and no token is issued. On `POST /auth/refresh` the row is compared **after** the Redis marker branch, so a deactivated-and-marked user still sees `TOKEN_REVOKED`; a deactivated user whose marker is gone is refused with the same `"User account is deactivated"` detail as the gate. Which authority each surface consults is tabulated in [Backend Architecture](../06-backend/architecture.md#account-deactivation-the-database-row-is-authoritative).
- **Forced password change:** A user with `force_password_change=true` receives HTTP **403 `PERMISSION_DENIED`** on every protected route except the allow-list described in [Login](#1-login). The check runs in `get_current_user_dependency()` after the `is_active` check. `403` is used instead of `401` so the SPA's sign-out interceptor is not triggered into a redirect loop.

---

## Cross-References

- [Security Overview](../08-security/) — CORS, rate limiting, credential enforcement, cookie security
- [Auth & Access Control](./) — Authorization flows and role-based access
- [Access Control](./) — Dashboard-level permission enforcement
- [API Responsibilities](../SPEC.md#14-api-responsibilities-fastapi) — Full API endpoint listing
- [Frontend Auth Flow](../07-frontend/auth-flow.md) — JWT handling, login/registration flows, cookie-based refresh
- [Access Control](../08-security/access-control.md) — Dashboard-level permission model and enforcement points
- [Admin API](../04-admin/admin-api.md) — User management and registration approval
