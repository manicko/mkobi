---
id: frontend-auth-flow
domain: frontend
tags:
  - jwt
  - token-storage
  - login-flow
  - registration-flow
  - role-based-access
  - email-validation
  - session-expiration
related:
  - frontend-security
  - pages
  - auth-api
  - frontend-architecture
---

# Frontend Auth Flow

## Overview

Authentication in the frontend is handled by the `auth` feature (`features/auth/`). The flow uses JWT tokens issued by the FastAPI backend, with a `useAuth` hook providing auth state to the entire application.

## JWT Token Storage

Token storage behavior differs between production and development environments, controlled by `import.meta.env.PROD` in `features/auth/model/authToken.ts`:

### Production (Memory-Only)

- Tokens are stored in a **module-level JavaScript variable** (`memoryToken`).
- Tokens are never written to `localStorage` or `sessionStorage`.
- **Security benefit:** Not vulnerable to XSS-based token exfiltration via browser storage APIs.
- **Trade-off:** Tokens are lost on full page reload or navigation (user must log in again).

### Development (sessionStorage Fallback)

- Tokens are stored in `sessionStorage` under the key `access_token`.
- **Convenience benefit:** Tokens survive page refreshes and hot-reloads during development.
- **Security trade-off:** `sessionStorage` is accessible to any JavaScript running on the page (XSS risk).
- Tokens are cleared when the tab is closed.

### Token Expiration Check

Every API request triggers an expiration check via `getTokenWithExpirationCheck()`:

1. Decode the JWT payload (base64).
2. Read the `exp` field.
3. If `Date.now() >= exp * 1000`, the token is removed and `null` is returned.
4. The Axios request interceptor then sends the request without a token, resulting in a `401` from the backend.

## Login Flow

```
Browser                          FastAPI
  │                                │
  │  POST /api/v1/auth/login       │
  │  { email, password }           │
  │ ──────────────────────────────►│
  │                                │ ┌──────────────────────┐
  │                                │ │ Rate limit check      │
  │                                │ │ (5 / 5 min per email, │
  │                                │ │  50 / 5 min per peer) │
  │                                │ └──────────┬───────────┘
  │                                │            │
  │                                │ ┌──────────▼───────────┐
  │                                │ │ Verify bcrypt hash    │
  │                                │ │ Check is_active       │
  │                                │ └──────────┬───────────┘
  │                                │            │
  │                                │ ┌──────────▼───────────┐
  │                                │ │ Create JWT token      │
  │                                │ │ {user_id, email,      │
  │                                │ │  role, exp}           │
  │                                │ └──────────┬───────────┘
  │                                │            │
  │  200 OK                        │            │
  │  { access_token, token_type,    │            │
  │    user: { id, email, role,     │            │
  │      display_name, created_at } │            │
  │  }                              │            │
  │ ◄──────────────────────────────│            │
  │                                │
  │  Store token in memory/storage │
  │  Set user in useAuth state     │
  │  Redirect to /dashboards       │
```

### Steps

1. User submits the login form (`LoginForm.tsx`) with email and password.
2. Form is validated via Zod (`loginSchema`): email format, password min 6 characters.
3. `POST /api/v1/auth/login` is called via Axios.
4. On success (`200`): token is stored, user profile (including `display_name`) is set in `useAuth` state, redirect to `/dashboards`.
5. On failure (`401`/`429`): error alert is displayed. A `401` with detail `Invalid credentials` covers a wrong password **and** a deactivated account alike — the two are deliberately indistinguishable, so this screen cannot be used to discover which accounts exist.
6. On failure (`503`): a backing store — the revocation store in particular — could not be read. The interceptor shows a toast and does **not** sign the user out — see [Session Expiration Handling](#session-expiration-handling).

## Registration Request Flow

```
Browser              FastAPI              Database
  │                    │                    │
  │  POST /auth/       │                    │
  │  register-request  │                    │
  │  { email }         │                    │
  │───────────────────►│                    │
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
  │◄───────────────────│                    │
  │                    │                    │
  │  Show success      │                    │
  │  message           │                    │
```

### Steps

1. User submits the registration form (`RegisterForm.tsx`) with email.
2. Form is validated via Zod (`registerSchema`): email format + domain blocklist check.
3. `POST /api/v1/auth/register-request` is called.
4. On success (`201`): success message is displayed.
5. Admin reviews and approves the request via the Admin Panel.
6. On approval, a temporary password is generated and a **retrieval token** is returned to the admin. The plaintext password is **never** in the approval response; the admin fetches it in a second, one-time call (`POST /api/v1/admin/temp-passwords` with the handle in the request body). The approval response also carries `credential_stored`: if it is `false`, the temporary password never reached the store and the returned token will not work, so the approval has to be repeated.

## Role-Based Access Control

### Route-Level Protection

Two guard components enforce access control at the route level:

**`ProtectedRoute`** (`shared/components/ProtectedRoute.tsx`):
- Checks if `useAuth().user` is set.
- If not authenticated: redirects to `/login` (preserving the intended destination in `location.state`).
- If loading: shows a `CircularProgress` spinner.

**`RoleBasedAccess`** (`shared/components/RoleBasedAccess.tsx`):
- Checks if `useAuth().user.role` is in the allowed `roles` array.
- If authorized: renders children.
- If unauthorized: renders `fallback` (defaults to `null`).

### Route Access Matrix

| Route | Guard | Allowed Roles |
| --- | --- | --- |
| `/login`, `/register` | None | Public |
| `/dashboards` | `ProtectedRoute` | All authenticated |
| `/dashboard/:id` | `ProtectedRoute` | All authenticated |
| `/admin` | `ProtectedRoute` + `RoleBasedAccess` | `admin` only |
| `/profile` | `ProtectedRoute` | All authenticated |
| `/profile/change-password` | `ProtectedRoute` | All authenticated |

### UI-Level Role Checks

Beyond route guards, individual UI elements are conditionally rendered based on role:

- **Upload button** on Dashboard View: visible only for `admin` and `editor`.
- **Delete Account** button on Profile page: visible only for non-admin users.
- **Admin link** in navigation: visible only for `admin`.

## Email Validation

Email validation is applied on both frontend and backend:

### Frontend (Zod)

```typescript
// Login
email: z.string().email('Invalid email format')

// Registration
email: z.string()
  .email('Invalid email format')
  .refine((email) => {
    const domain = email.split('@')[1]
    return domain && !BLOCKED_DOMAINS.includes(domain)
  }, 'This email domain is not allowed')
```

Blocked domains are defined in `shared/types/formSchemas.ts`: `tempmail.com`, `throwawaymail.com`.

### Backend (Pydantic)

The backend independently validates email format and checks against a configurable domain blocklist. Frontend validation is a UX convenience; backend validation is the security boundary.

## Session Expiration Handling

When a session expires (token expires or is invalidated):

1. The next API call returns `401`.
2. The Axios response interceptor catches the `401`.
3. The interceptor attempts a **silent refresh** by calling `POST /api/v1/auth/refresh` with `withCredentials: true` (sending the httpOnly cookie). The response **rotates the refresh cookie**, so the browser must accept the new one.
4. **On successful refresh:** The new access token is stored in memory, and the original request is retried. The user experiences no interruption.
5. **On failed refresh** (no cookie, invalid or revoked cookie, a credential predating the user's revocation marker, a deactivated account, a deleted user): The token is removed from storage, an error toast is displayed ("Session expired. Please login again."), and the user is redirected to `/login`.

### A Store Outage Is Not an Expiration

A refresh that fails because the **revocation store cannot be read** answers `503
SERVICE_UNAVAILABLE`, not `401`. The interceptor treats a `503` as an ordinary error: it raises a
toast and rejects the request, but it does **not** clear the token and does **not** redirect to
`/login`.

This matters because the sign-out path is triggered by the status `401`, not by the message. Were a
Redis degradation reported as a credential failure, every open SPA in the deployment would be
redirected to the login screen and told its session had expired — a self-inflicted mass sign-out
caused by an infrastructure blip. "The store cannot answer" must never be presented to the client
as "your session is not valid".

### Concurrent 401 Handling

When multiple requests fail with `401` simultaneously (e.g., right after token expiry), the axios interceptor ensures only one refresh call is made:

- The first `401` triggers the refresh and sets `isRefreshing = true`.
- Subsequent `401`s are queued in `failedQueue`.
- After the refresh completes, all queued requests are retried with the new access token.
- If the refresh fails, all queued requests are rejected and the user is redirected to login.

### Silent Refresh on App Initialization

On app mount, `useAuth` checks if an access token exists in memory. If not, it attempts a silent refresh using the httpOnly cookie. This keeps users logged in across page refreshes without requiring re-authentication. During the refresh, `ProtectedRoute` shows a loading spinner to prevent a flash of the login page.

## Force Password Change Flow

When a user's `force_password_change` flag is `true` (set by admin password reset or registration approval), the system enforces a password change before granting access to the dashboard.

The redirect below is a **convenience, not the control**. The flag is enforced **server-side** in
`get_current_user_dependency()`, the single dependency every protected route passes through: a
flagged user is refused on every protected route with `403 PERMISSION_DENIED` except a named
allow-list — `POST /api/v1/auth/change-password`, `POST /api/v1/auth/refresh`,
`POST /api/v1/auth/logout`, and `GET /api/v1/auth/me`. The allow-list keeps the completion path, the
silent refresh, logout, and the flag-carrying `/auth/me` reachable; without it a flagged user would
be trapped or the redirect mechanism itself would break. The flag is read from the already-loaded
user row, so the gate adds **no extra query**.

`403` is used rather than `401` for exactly this UI reason: the axios interceptor answers any `401`
with a silent refresh and, on failure, a sign-out back to `/login`, so a `401` refusal would become
a redirect loop instead of a redirect to the change-password page. A `403` produces a toast and
leaves the current location alone.

### Login Redirect

1. User submits login form with valid credentials.
2. Server returns `TokenWithUser` with `force_password_change: true` in the user object.
3. `LoginForm.tsx` checks `response.user.force_password_change` after a successful login.
4. If `true`: redirects to `/profile/change-password?force=true` (instead of `/dashboards`).
5. If `false`: redirects to `/dashboards` (normal flow).

### Silent Refresh Redirect

1. On app mount, if no access token exists, the frontend attempts a silent refresh using the httpOnly cookie.
2. After fetching the profile, the frontend checks `profile.force_password_change`.
3. If `true`: redirects via `window.location.href` to `/profile/change-password?force=true`.
4. This ensures that users with forced password changes are redirected even across page refreshes.

### Change Password Force Mode

The `ChangePasswordPage` reads the `?force=true` query parameter:
- **Info Alert** is shown: "Password change is required. Please set a new password to continue."
- **Cancel button** is disabled — the user must change their password to proceed.
- On successful password change, the backend clears the `force_password_change` flag, and the user is redirected to `/profile`.
- **The backend also revokes every token this user holds**, so the access token that performed the
  change is withdrawn with the rest. The redirect to `/profile` therefore needs a fresh login: the
  SPA's next request is refused until the user authenticates with the new password. This is the
  rotation described in [Authentication API → Change Password](../01-auth/auth-api.md#8-change-password).

---

## Logout Flow

1. User clicks logout in the Header menu.
2. Frontend calls `POST /api/v1/auth/logout` with the access token.
3. Backend validates the token and clears the `mkobi_refresh_token` cookie.
4. Frontend clears the in-memory access token.
5. User is redirected to `/login`.

> The logout API call is fire-and-forget on the frontend — if it fails (network error), the frontend still clears local state and redirects.

## Cross-References

- [Frontend Security](frontend-security.md) — JWT security, CORS, file upload security
- [Pages](pages.md) — Page-level access control details
- [Authentication API](../../01-auth/auth-api.md) — Backend auth endpoint specifications
- [Frontend Architecture](architecture.md) — HTTP client interceptor details
- [Access Control](../../08-security/access-control.md) — Route guards and permission model
- [Admin API](../../04-admin/admin-api.md) — Registration approval flow
