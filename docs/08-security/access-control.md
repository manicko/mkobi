---
id: access-control
domain: security
tags:
  - access-control
  - roles
  - permissions
  - dashboard-access
  - enforcement-points
  - route-guards
  - resource-level-access
related:
  - security-overview
  - auth-api
  - dashboards-api
  - schema-access
  - frontend-security
---

# Access Control

## Overview

This document describes the access control model and the specific enforcement points throughout the system. Access control is enforced on **every request** to dashboard-related endpoints — the backend is the security boundary.

> **[HIGH-RISK]** Access control must be enforced consistently on all dashboard-related endpoints. Missing a single enforcement point can expose data across dashboards.

---

## Roles

The system defines three roles, implemented as `StrEnum` in `src/mkobi/models/enums.py`:

| Role | Description | Capabilities |
| --- | --- | --- |
| `admin` | System administrator | Full CRUD on all entities, user management, access management, log viewing |
| `editor` | Data editor | Upload CSV, trigger processing, modify processing configs |
| `viewer` | Read-only user | View dashboards they have been granted access to |

---

## Permission Model

### Dashboard-Level Permissions

The `dashboard_access` table defines granular permissions per user per dashboard:

| Permission | Description |
| --- | --- |
| `view` | Can view the dashboard and its data |
| `edit` | Can view and modify dashboard data (upload, process) |
| `admin` | Full control over the dashboard (CRUD, access management) |

**Schema:**

```sql
dashboard_access (
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    dashboard_id    UUID REFERENCES dashboards(id) ON DELETE CASCADE,
    permission      TEXT NOT NULL CHECK (permission IN ('view', 'edit', 'admin')),
    PRIMARY KEY (user_id, dashboard_id)
);
```

### Role vs. Permission

- **Roles** (`admin`, `editor`, `viewer`) are global and define what a user can do across the system.
- **Permissions** (`view`, `edit`, `admin`) are per-dashboard and define what a user can do with a specific dashboard.
- An `admin` role user has implicit full access to all dashboards (see [Admin Bypass](#admin-bypass) below).
- An `editor` or `viewer` user only has access to dashboards explicitly granted via `dashboard_access`.

---

## Admin Bypass

Users with the `admin` role bypass all dashboard-level access checks:

- **`GET /api/v1/dashboards/my`** — Returns all dashboards in the system (not just those with explicit `dashboard_access` entries).
- **`GET /api/v1/dashboards/:id`** — Returns any dashboard by ID without checking the `dashboard_access` table.
- **All other dashboard-related endpoints** — Admin bypass is applied consistently across graphs, filters, and data retrieval.

The bypass is implemented at the repository level: `DashboardRepository.get_by_user()` returns all dashboards when `is_admin=True`, and `DashboardService.get_dashboard()` short-circuits the access check for admin users.

> Non-admin users continue to see only dashboards with explicit `dashboard_access` entries. The bypass applies only to the `admin` role.

---

## 403/404 Dual-Signal for Dashboard Access [HIGH-RISK]

The `GET /api/v1/dashboards/:id` endpoint distinguishes between two failure cases:

| Condition | HTTP Status | Detail | Reason |
| --- | --- | --- | --- |
| Dashboard does not exist | `404 Not Found` | `Dashboard not found` | Avoids confirming existence |
| Dashboard exists but user lacks access | `403 Forbidden` | `Access denied` | Informs user they need permission |

**Implementation:** The `DashboardService.get_dashboard()` method uses a dual-signal approach:
1. If the dashboard is not found → returns `None` (mapped to 404 by the route handler).
2. If the dashboard exists but the user has no access → raises `PermissionDeniedException` (mapped to 403 by the route handler).
3. Admin users bypass step 2 entirely.

> This pattern prevents an attacker from enumerating dashboard IDs: a 404 response does not reveal whether the dashboard exists or the user simply lacks access. However, a 403 response confirms the dashboard exists. This is an intentional trade-off to provide meaningful error messages to authorized users.

---

## Enforcement Points [HIGH-RISK]

Access control is enforced on **all** dashboard-related endpoints, not just data retrieval. The following endpoints validate that the user has access to the requested dashboard:

### Data Retrieval Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `GET /api/v1/dashboards/my` | Any authenticated | Returns only dashboards the user has access to; admins see all dashboards |
| `GET /api/v1/dashboards/:id` | Any authenticated | Validates user has access to the specific dashboard; 403 if access denied, 404 if not found; admins bypass access check |
| `GET /api/v1/data/aggregated` | Any authenticated | Validates dashboard access before returning data |

### Dashboard CRUD Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `POST /api/v1/dashboards/` | Admin only | Admin role required for creation; no resource-level check needed (new resource) |
| `PUT /api/v1/dashboards/:id` | Admin or editor | Resource-level access check: admin role bypasses; otherwise requires `edit` or `admin` permission on the dashboard |
| `DELETE /api/v1/dashboards/:id` | Admin only | Admin role required; resource-level access check with admin bypass |

### Filter Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `GET /api/v1/filters` | Editor+ | Filters are only returned if the user has access to the associated dashboard |
| `GET /api/v1/filters/:id` | Editor+ | Same as above |

### Graph Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `GET /api/v1/graphs/` | Any authenticated | Graph definitions are filtered by dashboard access |
| `GET /api/v1/graphs/:id` | Any authenticated | Validates access to the parent dashboard |

### Access Management Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `GET /api/v1/dashboards/:id/access` | Owner or administrator | Resolves `require_dashboard_admin_access`, which requires an `admin` permission on that dashboard and is short-circuited for callers holding the `admin` role |
| `POST /api/v1/dashboards/:id/access` | Owner or administrator | Resolves `require_dashboard_admin_access`, which requires an `admin` permission on that dashboard and is short-circuited for callers holding the `admin` role |
| `DELETE /api/v1/dashboards/:id/access/:user_id` | Owner or administrator | Resolves `require_dashboard_admin_access`, which requires an `admin` permission on that dashboard and is short-circuited for callers holding the `admin` role |

### Upload and Processing Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `POST /api/v1/upload/:dashboard_id` | Editor+ | Verifies dashboard exists (404 if not), then validates user has edit permission on the dashboard |
| `POST /api/v1/upload/:dashboard_id/process` | Editor+ | Validates task ownership and dashboard access |
| `GET /api/v1/upload/status/:task_id` | Editor+ | Validates user has access to the task's dashboard |
| `GET /api/v1/upload/result/:task_id` | Editor+ | Validates user has access to the task's dashboard |

### Admin Endpoints

| Endpoint | Auth Level | Access Check |
| --- | --- | --- |
| `GET /api/v1/admin/users` | Admin only | Full user listing |
| `PATCH /api/v1/admin/users/:id/role` | Admin only | Role modification |
| `DELETE /api/v1/admin/users/:id` | Admin only | User deletion |
| `GET /api/v1/admin/registration-requests` | Admin only | Registration request listing |
| `POST /api/v1/admin/registration-requests/:id/approve` | Admin only | Approve registration |
| `POST /api/v1/admin/registration-requests/:id/reject` | Admin only | Reject registration |
| `GET /api/v1/admin/logs/` | Admin only | Processing log access |

---

## Access Check Function

`require_dashboard_admin_access` in `src/mkobi/api/deps.py` is the single shared dependency the three dashboard access-management routes resolve; it delegates to `check_dashboard_access` with `required_permission="admin"`.

The `check_dashboard_access` function is the central enforcement mechanism:

1. **Input:** `user_id`, `dashboard_id`, required permission level
2. **Logic:**
   - If the user has the `admin` role → access granted (short-circuit)
   - Otherwise, query the `dashboard_access` table for the `(user_id, dashboard_id)` pair
   - Verify the permission level meets or exceeds the required level
3. **Failure:** Returns HTTP 403 Forbidden with an appropriate error message

---

## Forced Password Change Gate

`force_password_change` is enforced server-side in `get_current_user_dependency()` (`src/mkobi/api/deps.py`), the single dependency every protected route passes through. The check runs **after** the `is_active` check and refuses a flagged user with `403 PERMISSION_DENIED` on every protected route except a named allow-list: `POST /api/v1/auth/change-password`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, and `GET /api/v1/auth/me`. The allow-list is expressed by the predicate `is_password_change_completion_path(method, path)` and unit-tested directly. `403` is used rather than `401` because the SPA signs a user out on any `401`, which would turn the refusal into a redirect loop. See [Authentication API](../01-auth/auth-api.md#1-login) for the reason behind each allow-list entry.

---

## Second Identity Path (Not a Live Gate)

`src/mkobi/core/permissions.py::_get_current_user_with_session` (and its public wrapper `get_current_user`) is a second token-to-user path that mirrors part of the dependency's logic. It has **no production caller** — the only callers are its own wrapper and direct unit tests (`tests/test_permissions.py::TestGetCurrentUser`). It is **not** a second live gate:

- It is never invoked by any route or dependency in `src/mkobi/`; the live gate is `get_current_user_dependency`.
- Therefore the `force_password_change` gate described above is **not** enforced on this path, and cannot be, because nothing reaches it.
- Another phase plans to **delete** both `_get_current_user_with_session` and `get_current_user`; this document records the situation rather than assuming a hidden enforcement point.

> Do not treat this module as an alternative enforcement point when auditing access control. The authoritative identity path is `api/deps.py::get_current_user_dependency`.

---

## Frontend Enforcement

The frontend provides UX-level access control that mirrors the backend:

### Route Guards

| Component | Behavior |
| --- | --- |
| `ProtectedRoute` | Redirects unauthenticated users to `/login` |
| `RoleBasedAccess` | Renders children only if the user's role is in the allowed list |

### Access Matrix

| Route | Required Role |
| --- | --- |
| `/login`, `/register` | Public |
| `/dashboards`, `/dashboard/:id` | Any authenticated |
| `/admin` | `admin` only |
| `/profile`, `/profile/change-password` | Any authenticated |

### UI-Level Enforcement

- Upload button: visible only for `admin` and `editor`
- Delete Account button: visible only for non-admin users
- Admin navigation: visible only for `admin`

> **Note:** UI-level role checks are for UX only. The backend enforces authorization on every API request.

---

## User Visibility Rules

- Users can view their own profile (`GET /api/v1/users/:id` where `:id` matches their own)
- Admins can view any user's profile
- Non-admin users cannot see the full user list
- Self-deletion (`DELETE /api/v1/users/me`) is available for non-admin users only

---

## Cross-References

- [Security Overview](security-overview.md) — Rate limiting, CORS, credential enforcement
- [Authentication API](../01-auth/auth-api.md) — Login, registration, JWT handling
- [Dashboard API](../02-dashboards/dashboards-api.md) — Dashboard CRUD and access endpoints
- [Frontend Security](../07-frontend/frontend-security.md) — Route guards, role-based UI
- [Database Schema](../09-database/schema-access.md) — `dashboard_access` table definition
- [Database Enums](../09-database/enums.md) — `UserRole`, `DashboardPermission` StrEnum definitions
- [Admin API](../04-admin/admin-api.md) — User management and role modification
