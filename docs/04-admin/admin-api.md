---
id: admin-api
domain: admin
tags:
  - user-management
  - registration-requests
  - processing-logs
  - admin-panel
  - roles
  - approval-flow
related:
  - auth-api
  - dashboards-api
  - processing-api
  - schema-access
  - security-overview
---

# Admin API

## Overview

The admin API provides endpoints for user management, registration request processing, and system monitoring. All admin endpoints require the `admin` role unless otherwise specified.

**Base path:** `/api/v1`

---

## User Management Endpoints

These endpoints allow admins to manage user accounts. Some endpoints are also accessible to non-admin users for self-management.

### 1. List All Users

Retrieve a list of all registered users. Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/users`                |
| **Auth level** | Admin                          |

**Response** (`200 OK`):

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "admin@example.com",
    "role": "admin",
    "is_active": true,
    "force_password_change": false,
    "created_at": "2026-04-24T16:02:46+03:00"
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "email": "editor@example.com",
    "role": "editor",
    "is_active": true,
    "force_password_change": false,
    "created_at": "2026-04-25T10:00:00+03:00"
  }
]
```

---

### 2. Get User Detail

Retrieve a single user by ID. Accessible to the user themselves or to admins.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/users/:id`            |
| **Auth level** | Self or Admin                  |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | User ID            |

**Response** (`200 OK`):

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true,
  "force_password_change": false,
  "created_at": "2026-04-24T16:02:46+03:00"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not self or admin  | Forbidden                    |
| `404`  | User not found               | `User not found`             |

---

### 3. Create User

Directly create a new user account with a specified role. Admin only. This endpoint accepts a JSON request body (Pydantic `UserCreateRequest`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/users`                |
| **Auth level** | Admin                          |

**Request body:**

```json
{
  "email": "newuser@example.com",
  "password": "initial_password123",
  "role": "editor"
}
```

**Response** (`201 Created`): User detail object.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `422`  | Duplicate email              | Validation error             |
| `422`  | Invalid role value           | Validation error             |

---

### 4. Update User Role (via /users)

Change the role of an existing user. Admin only. This endpoint accepts a JSON request body (Pydantic `UserUpdateRequest`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `PATCH`                        |
| **Path**       | `/api/v1/users/{user_id}/role` |
| **Auth level** | Admin                          |

**Path parameters:**

| Parameter  | Type   | Description        |
| ---------- | ------ | ------------------ |
| `user_id`  | UUID   | User ID            |

**Request body:**

```json
{
  "role": "editor"
}
```

**Response** (`200 OK`): Updated user detail object.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `404`  | User not found               | `User not found`             |
| `422`  | Invalid role value           | Validation error             |

**Valid roles:** `admin`, `editor`, `viewer` (defined by `UserRole` StrEnum)

---

### 5. Delete User

Delete a user account. Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/users/:id`            |
| **Auth level** | Admin                          |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | User ID            |

**Response** (`204 No Content`)

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `404`  | User not found               | `User not found`             |

---

### 6. Reset User Password (Admin)

Admin-triggered password reset. Generates a temporary password for the target user and sets `force_password_change=True`, requiring the user to change their password on next login.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/admin/users/{user_id}/reset-password`     |
| **Auth level** | Admin                                              |

**Path parameters:**

| Parameter  | Type   | Description        |
| ---------- | ------ | ------------------ |
| `user_id`  | UUID   | Target user ID     |

**Response** (`200 OK`):

```json
{
  "message": "Password reset successfully",
  "user_id": "880e8400-e29b-41d4-a716-446655440003",
  "retrieval_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "credential_stored": true
}
```

**Error responses:**

| Status | Condition                        | Detail                                    |
| ------ | -------------------------------- | ----------------------------------------- |
| `422`  | Admin attempts self-reset        | `Admin cannot reset own password` (`VALIDATION_ERROR`) |
| `404`  | User not found                   | `User not found` (`USER_NOT_FOUND`)      |
| `500`  | Unexpected server error          | `Error resetting user password` (`INTERNAL_ERROR`) |

**Side effects:**
- Generates a 16-character cryptographically secure temporary password (letters + digits, at least one of each)
- Stores the bcrypt hash of the temporary password in the `users` table
- Sets `force_password_change=True` on the target user
- Stores the **plaintext** temporary password in Redis via `TempPasswordStore` under the `retrieval_token`
- Returns `retrieval_token` (UUID) in the response instead of `temp_password`
- Returns `credential_stored`: `false` when the Redis write failed or no store was wired, in which case the returned `retrieval_token` is **not** a working handle and a second reset is required; the status stays `200` because the password change itself is committed and durable
- **Revokes the target user's existing tokens.** Once the new password is committed every credential
  the target holds is stale, so a timestamped user-level marker is written **after** the commit —
  the same ordering, and the same non-transactional-write caveat, as
  `PATCH /admin/users/{id}/active`. A token issued before the reset is refused; the target logs in
  again with the new credential and works immediately. A Redis fault at this step is **guarded
  separately**, exactly as it is on the deactivation path: the endpoint answers `500` with the
  distinct detail `Password was reset successfully, but revoking the user's sessions failed; a
  second reset is required.` rather than falling into the blanket handler, so the operator is told
  the reset landed and must be repeated. This is **orthogonal** to `credential_stored`:
  the reset landed either way, even when the temporary-password handoff did not. See
  [Authentication API → Change Password](../01-auth/auth-api.md#8-change-password).

> **Security:** The temporary password is **never returned in the response**. Instead, a `retrieval_token` is returned. The admin retrieves the password via `POST /api/v1/admin/temp-passwords` with the handle in the body when needed. This ensures the plaintext password never appears in API response logs, and the handle stays out of the application access log. The password is stored in Redis with TTL (default: 24h, configurable via `TEMP_PASSWORD_TTL_SECONDS`) and is deleted upon retrieval (single-use).

---

### 7. Delete Own Account (Self-Deletion)

Allow a non-admin user to delete their own account.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/users/me`             |
| **Auth level** | Any authenticated user (non-admin only) |

**Response** (`204 No Content`)

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is admin              | Admins cannot self-delete    |

---

## Admin-Only Endpoints

These endpoints are exclusively available under the `/api/v1/admin` path and require the `admin` role.

### 8. Admin: List Users

Admin-specific user listing (alternative to `/api/v1/users`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/admin/users`          |
| **Auth level** | Admin                          |

**Response** (`200 OK`): Same format as [List All Users](#1-list-all-users).

---

### 9. Admin: Update User Role

Admin-specific role update (alternative to `/api/v1/users/:id/role`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `PATCH`                        |
| **Path**       | `/api/v1/admin/users/:id/role` |
| **Auth level** | Admin                          |

**Request body:**

```json
{
  "role": "viewer"
}
```

**Response** (`200 OK`): Updated user detail object.

---

### 10. Admin: Delete User

Admin-specific user deletion (alternative to `/api/v1/users/:id`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/admin/users/:id`      |
| **Auth level** | Admin                          |

**Response** (`204 No Content`)

---

### 11. List Registration Requests

Retrieve all registration requests, optionally filtered by status.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/admin/registration-requests` |
| **Auth level** | Admin                          |

**Query parameters:**

| Parameter | Type   | Required | Description                                |
| --------- | ------ | -------- | ------------------------------------------ |
| `status`  | string | No       | Filter by status: `pending`, `approved`, `rejected` |

**Response** (`200 OK`):

```json
[
  {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "email": "applicant@example.com",
    "status": "pending",
    "requested_by_ip": "192.168.1.1",
    "reviewed_by": null,
    "reviewed_at": null,
    "created_at": "2026-05-18T10:00:00Z"
  }
]
```

---

### 12. Approve Registration Request

Approve a pending registration request. Creates a new user account with a randomly generated temporary password.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/admin/registration-requests/:id/approve` |
| **Auth level** | Admin                          |

**Path parameters:**

| Parameter | Type   | Description              |
| --------- | ------ | ------------------------ |
| `id`      | UUID   | Registration request ID  |

**Response** (`200 OK`):

```json
{
  "message": "Registration approved",
  "user_id": "880e8400-e29b-41d4-a716-446655440003",
  "retrieval_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "credential_stored": true
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `404`  | Request not found            | `Registration request not found` |
| `409`  | Request already processed    | `Request already <status>` (`DUPLICATE_RESOURCE`), where `<status>` is the request's current status — for example `Request already approved` |

**Side effects:**
- Creates a new user in the `users` table with the email from the request
- Sets the user's password to a cryptographically random temporary password
- Sets `force_password_change=True` on the new user
- Updates the `registration_requests` record: status → `approved`, `reviewed_by` → admin user ID, `reviewed_at` → current timestamp
- **Commits**, and only then stores the plaintext temporary password in Redis via `TempPasswordStore` under the `retrieval_token`
- The response also carries `credential_stored`, which is `false` when the Redis write faulted or no store was wired

The same `409` covers a request that exists but is not `pending`, and a request that disappeared
between the existence check and the service call; the detail interpolates the status the route
actually read, so the client is told which state it found.

The first four steps happen inside a single transaction owned by
`AuthService.approve_registration_request`; the route does not open, commit or
roll back a transaction itself. See [Registration Approval Flow](#registration-approval-flow)
for why the Redis write is deliberately last.

> **Security Note:** The `retrieval_token` (UUID) is returned instead of a plaintext `temp_password`. The admin retrieves the actual password via `POST /api/v1/admin/temp-passwords` with the handle in the body when needed. This ensures the plaintext password never appears in API response logs, and the handle stays out of the application access log. The password is stored in Redis with TTL (default: 24h) and is single-use.

---

### 13. Reject Registration Request

Reject a pending registration request.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/admin/registration-requests/:id/reject` |
| **Auth level** | Admin                          |

**Path parameters:**

| Parameter | Type   | Description              |
| --------- | ------ | ------------------------ |
| `id`      | UUID   | Registration request ID  |

**Response** (`200 OK`):

```json
{
  "message": "Registration rejected"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `404`  | Request not found            | `Registration request not found` |
| `409`  | Request already processed    | `Request already <status>` (`DUPLICATE_RESOURCE`) |

**Side effects:**
- Updates the `registration_requests` record: status → `rejected`, `reviewed_by` → admin user ID, `reviewed_at` → current timestamp

---

### 14. Retrieve Temporary Password

Retrieve a one-time temporary password by its retrieval token. Admin only. The password is deleted from Redis upon retrieval (single-use). Two operations share the same retrieval logic, `404`/`403`/`503` behaviour, and admin guard.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/admin/temp-passwords`                     |
| **Auth level** | Admin                                              |

**Request body:**

```json
{
  "retrieval_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Response** (`200 OK`):

```json
{
  "temp_password": "xK9mP2nQ5rT8vW1y"
}
```

**Error responses:**

| Status | Condition                                | Detail                                        |
| ------ | ---------------------------------------- | --------------------------------------------- |
| `403`  | Caller is not admin                       | Forbidden (`INSUFFICIENT_PERMISSIONS`)        |
| `404`  | Token not found / expired / already used | `Temporary password not found or already retrieved` (`NOT_FOUND`) |
| `503`  | Temporary-password store unreachable     | Temporary password store is temporarily unavailable (`SERVICE_UNAVAILABLE`) |

An expired, already-retrieved and never-existed token are indistinguishable by
design and all answer `404`; a **store fault is not one of them** and answers
`503`, so a retry loop against a `404` is never mistaken for an outage.

#### 14a. Legacy Retrieve Temporary Password (Deprecated)

> **Deprecated — removal in release 1.0.9.** This operation carries the retrieval
> handle in the request line. Use `POST /api/v1/admin/temp-passwords`, which
> carries it in the request body. The path operation is retained for one release
> so existing callers keep working; it is otherwise byte-identical in behaviour.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET` (deprecated)                                 |
| **Path**       | `/api/v1/admin/temp-passwords/{retrieval_token}`   |
| **Auth level** | Admin                                              |

**Path parameters:**

| Parameter          | Type   | Description              |
| ------------------ | ------ | ------------------------ |
| `retrieval_token`  | UUID   | The retrieval token from a reset/approve response |

**Response** (`200 OK`): same as the `POST` operation above.

**Side effects (both operations):**
- The password is **deleted** from Redis (single-use via atomic GET+DELETE pipeline)
- Subsequent requests with the same token return 404
- The retrieval **token**'s first 8 characters are logged at INFO level; the plaintext password is **never** written to a log. The reset issuance route (`POST /admin/users/{user_id}/reset-password`) logs the same 8-character **prefix** — a prefix is not the handle and cannot be replayed. The approve route does **not**: it logs the request id, not a token prefix.

> **Security:** This is the **only** API operation that returns the plaintext `temp_password`. It requires admin authentication. The password is accessible only once — after retrieval, it is permanently deleted from Redis. Tokens auto-expire after `TEMP_PASSWORD_TTL_SECONDS` (default: 24h) if never retrieved. If Redis is unreachable the operation answers `503`, not `404`; the store's `GET`+`DELETE` run inside one Redis transaction.
>
> **Partially fixed.** Moving the handle to a request body removes it from the
> **application's** request line and therefore from the application access log.
> It is **still not fixed** at the proxy: `docker/nginx/nginx.conf` declares no
> `log_format` and writes the full request line to its own access log in the
> default `combined` format, so a `POST` body does not appear there but a legacy
> `GET` path still does. That file belongs to another phase; this phase records
> the change as a hand-over and does not edit it.

---

### 15. List Processing Logs

Retrieve processing logs with filtering and pagination. Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/admin/logs`           |
| **Auth level** | Admin                          |

**Query parameters:**

| Parameter      | Type      | Required | Description                                |
| -------------- | --------- | -------- | ------------------------------------------ |
| `status_filter`       | string    | No       | Filter by status: `started`, `uploaded`, `processing`, `success`, `failed`, `completed` |
| `dashboard_id` | UUID      | No       | Filter by dashboard                        |
| `date_from`    | datetime  | No       | Filter logs with started_at >= this date    |
| `date_to`      | datetime  | No       | Filter logs with started_at <= this date    |
| `skip`         | integer   | No       | Number of records to skip (default: 0)     |
| `limit`        | integer   | No       | Maximum records to return (default: 100)  |

**Response** (`200 OK`):

```json
[
  {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "success",
    "message": "Processing completed successfully",
    "started_at": "2026-05-18T12:00:00Z",
    "finished_at": "2026-05-18T12:01:30Z"
  }
]
```

---

### 15. Get Single Processing Log

Retrieve a single processing log entry by ID. Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/admin/logs/:log_id`   |
| **Auth level** | Admin                          |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `log_id`  | UUID   | Processing log ID  |

**Response** (`200 OK`): Single processing log object.

---

## Registration Approval Flow

The registration approval flow is a multi-step process that bridges the authentication system and the admin panel.

```
Browser (User)        FastAPI              Database
  │                     │                     │
  │  POST /auth/        │                     │
  │  register-request   │                     │
  │  { email }          │                     │
  │────────────────────►│                     │
  │                     │  INSERT             │
  │                     │  registration_      │
  │                     │  requests           │
  │                     │────────────────────►│
  │                     │  (status=pending)   │
  │                     │◄────────────────────│
  │  201 Created        │                     │
  │  { message, id }    │                     │
  │◄────────────────────│                     │
  │                     │                     │
  │  ... Admin reviews request in panel ...   │
  │                     │                     │
  │  Browser (Admin)    │                     │
  │  POST /admin/       │                     │
  │  registration-      │                     │
  │  requests/:id/      │                     │
  │  approve            │                     │
  │────────────────────►│                     │
  │                     │                     │
  │                     │  Generate temp      │
  │                     │  password           │
  │                     │  (secrets.choice)   │
  │                     │                     │
  │                     │  INSERT users       │
  │                     │────────────────────►│
  │                     │  (bcrypt hash of    │
  │                     │   temp_password,    │
  │                     │   force_password_   │
  │                     │   change=TRUE)      │
  │                     │◄────────────────────│
  │                     │                     │
  │                     │  UPDATE             │
  │                     │  registration_      │
  │                     │  requests           │
  │                     │────────────────────►│
  │                     │  (status=approved,  │
  │                     │   reviewed_by,      │
  │                     │   reviewed_at)      │
  │                     │◄────────────────────│
  │                     │                     │
  │                     │  COMMIT             │
  │                     │────────────────────►│
  │                     │◄────────────────────│
  │                     │                     │
  │                     │  SET temp_pwd:{     │
  │                     │  {token} in Redis   │
  │                     │  — AFTER the commit,│
  │                     │    non-transactional│
  │                     │                     │
  │  200 OK             │                     │
  │  { message,         │                     │
  │    user_id,         │                     │
  │    retrieval_token, │                     │
  │    credential_      │                     │
  │    stored }         │                     │
  │◄────────────────────│                     │
  │                     │                     │
  │  Admin retrieves    │                     │
  │  temp_password via  │                     │
  │  POST /admin/temp-  │                     │
  │  passwords          │                     │
  │  (handle in body)   │                     │
  │  and communicates   │                     │
  │  it to new user     │                     │
```

### Approval Sequence and Transaction Ownership

The route is transport only. `AuthService.approve_registration_request` owns the
sequence and, with it, the transaction:

```
generate temp password  (service-private helper)
      ↓
create user             ┐
set force_password_change│  one transaction,
update request status   ┘  opened and committed by the service
      ↓
COMMIT
      ↓
store temp password in Redis   ← deliberately after the commit
      ↓
return { message, user_id, retrieval_token, credential_stored }
```

The ordering is the point. Redis is not transactional, so a credential written
before the commit becomes durable independently of the database. The old
sequence wrote it in the middle of the transaction: a failure at the status
update or at the commit rolled the database back but not Redis, leaving a live
`retrieval_token` that unlocked a credential for a user that did not exist, for
the full TTL. Writing after the commit inverts the failure mode — a store
failure now leaves a real, committed user whose temporary password is not yet
retrievable. That state is visible to an admin and recoverable; the old one was
neither.

`TempPasswordStore.store` still fails open and never raises: it catches every
exception and returns. It now also **reports**: it returns `true` on a write that
did not fault and `false` on a swallowed fault, and `AuthService` propagates that
verdict twice — as `credential_stored` in the response body and as an `ERROR` log
naming both the affected user and the administrator. The user is never rolled
back, because a post-commit failure must not undo a committed account; a read of
the same store does the opposite and raises, because there is nothing to protect
there.

The status code and every error code are unchanged by this move (still `200`).
The body gains one key, `credential_stored`, which says whether the plaintext
temporary password actually reached Redis under the returned `retrieval_token`.
It is `false` whenever the store swallowed a Redis fault **or** no store was
wired. A `false` value means the token is **not** a working handle — the account
exists with a new password nobody can read, and a second reset is required.

**`credential_stored` reports; it does not prevent.** The endpoint still returns a
`retrieval_token` on a `false`, so an administrator can hold a handle for a
credential that was never stored. Nothing consumes `credential_stored`
automatically: reading it is the admin's responsibility, and the failure mode it
describes — an account whose password nobody can read — is recoverable only
because a second reset is possible. That is the accepted cost of failing open
after a commit, and it is recorded rather than hidden.
Other admin routes still commit in the transport layer; that inconsistency is
recorded, not resolved here.

`AuthService.reset_password_admin` — behind
`POST /api/v1/admin/users/{user_id}/reset-password` — was reordered the same way.

### Temporary Password Generation

When a registration request is approved, `AuthService` generates a cryptographically secure 16-character temporary password (letters + digits, at least one of each) using its own private `_generate_temp_password()` helper. Generation is internal to the service: the route neither calls the helper nor handles the plaintext password. This password:

- Is generated using `secrets.choice(string.ascii_letters + string.digits)` with up to 3 attempts to produce a password passing Pydantic validation
- Is **not** returned in plaintext by the approval response; that response carries a `retrieval_token` plus `credential_stored`, and the password is fetched separately from `POST /api/v1/admin/temp-passwords` with the handle in the request body
- Is stored as a bcrypt hash in the `users` table (never in plaintext)
- The user's `force_password_change` flag is set to `True`, requiring a password change on first login
- Must be communicated to the new user by the admin through an available channel
- Should be changed by the user upon first login (enforced by the frontend redirect to `/profile/change-password?force=true`)

---

## Admin Panel UI Pages

The admin panel is accessible at the `/admin` route and provides the following sections:

### User Management (`/admin`)

Displays a table of all users with the ability to change roles, reset passwords, and delete users.

**Key operations:**
- View all users (email, role, active status, creation date)
- Change user role via dropdown (calls `PATCH /api/v1/admin/users/:id/role`)
- Reset user password (calls `POST /api/v1/admin/users/:id/reset-password`) — generates a temporary password, sets `force_password_change=True`, shows result in `ResetPasswordResultDialog` with copy-to-clipboard
- Delete a user (calls `DELETE /api/v1/admin/users/:id`)

**Related API endpoints:**
- `GET /api/v1/admin/users` — List all users
- `PATCH /api/v1/admin/users/:id/role` — Update role (body: `{"role": "editor"}`)
- `POST /api/v1/admin/users/:id/reset-password` — Reset password (returns `{ message, user_id, retrieval_token, credential_stored }`)
- `DELETE /api/v1/admin/users/:id` — Delete user

### Registration Requests (`/admin`)

Displays pending registration requests with approve/reject actions.

**Key operations:**
- View pending requests (email, IP, date submitted)
- Approve a request (calls `POST /api/v1/admin/registration-requests/:id/approve`)
- Reject a request (calls `POST /api/v1/admin/registration-requests/:id/reject`)
- View approved/rejected requests (filtered by status)

**Related API endpoints:**
- `GET /api/v1/admin/registration-requests` — List requests
- `POST /api/v1/admin/registration-requests/:id/approve` — Approve (returns `{ message, user_id, retrieval_token, credential_stored }`)
- `POST /api/v1/admin/registration-requests/:id/reject` — Reject
- `POST /api/v1/admin/temp-passwords` — Retrieve temporary password (admin only, one-time; handle in body)
- `GET /api/v1/admin/temp-passwords/{retrieval_token}` — Deprecated alias, removed in release 1.0.9

### Dashboard Management (`/admin`)

Provides CRUD operations for dashboards, layouts, graphs, and filters.

**Related documentation:** [Dashboards API](../02-dashboards/dashboards-api.md)

### Log Viewer (`/admin`)

Displays processing logs with filtering and pagination.

**Key operations:**
- View processing logs (status, dashboard, timestamps)
- Filter by status (`started`, `uploaded`, `processing`, `success`, `failed`, `completed`)
- Filter by dashboard
- Filter by date range (`date_from`, `date_to`)
- Paginated navigation

**Related API endpoints:**
- `GET /api/v1/admin/logs` — List logs with filters (supports `status_filter`, `dashboard_id`, `date_from`, `date_to`, `skip`, `limit`)
- `GET /api/v1/admin/logs/:log_id` — Get single log entry

### Dashboard Access Management (`/admin`)

Provides endpoints for managing user access to dashboards.

**Related API endpoints:**
- `POST /api/v1/dashboards/{id}/access` — Grant access
- `GET /api/v1/dashboards/{id}/access` — List access records
- `DELETE /api/v1/dashboards/{id}/access/{user_id}` — Revoke access

### Dashboard-Filter Binding (`/admin`)

Provides endpoints for binding filters to dashboards.

**Related API endpoints:**
- `POST /api/v1/dashboards/{id}/filters?filter_id=:id` — Bind filter
- `DELETE /api/v1/dashboards/{id}/filters/{filter_id}` — Unbind filter
- `GET /api/v1/dashboards/{id}/filters` — List bound filters

---

## Role & Permission Summary

| Role       | User CRUD | Registration Mgmt | Processing Logs | Dashboard CRUD |
| ---------- | --------- | ----------------- | --------------- | -------------- |
| `admin`    | Full      | Full              | Full            | Full           |
| `editor`   | None      | None              | None            | None           |
| `viewer`   | None      | None              | None            | None           |

All admin API endpoints enforce role-based access control. Requests without the `admin` role receive a `403 Forbidden` response.

---

## Cross-References

- [Authentication API](../01-auth/auth-api.md) — JWT auth, registration request submission, password change
- [Dashboards API](../02-dashboards/dashboards-api.md) — Dashboard, graph, and filter CRUD
- [Processing API](../03-processing/processing-api.md) — Processing logs, upload, and data endpoints
- [Database Schema](../09-database/schema-core.md) — `users`, `registration_requests`, `processing_logs` table definitions
- [Security Overview](../08-security/) — Rate limiting, credential enforcement, CORS
- [Access Control](../08-security/access-control.md) — Role-based access control and enforcement points
- [Database Enums](../09-database/enums.md) — `UserRole`, `RegistrationStatus` StrEnum definitions
