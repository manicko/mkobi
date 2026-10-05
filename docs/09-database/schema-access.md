---
id: schema-access
domain: database
tags:
  - dashboard-access
  - registration-requests
  - dashboard-filters
  - permissions
  - many-to-many
  - access-control
related:
  - schema-core
  - schema-processing
  - indexes
  - access-control
  - admin-api
---

# Access Schema

## Overview

The access schema contains tables for managing user access to dashboards, registration requests, and the many-to-many relationship between dashboards and filters.

**Schema file:** `src/mkobi/db/models/`

---

## Tables

### `dashboard_access` — Dashboard Access Rights

Manages user permissions for dashboards. Each row grants a user a specific permission level for a specific dashboard.

```sql
CREATE TABLE dashboard_access (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dashboard_id    UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    permission      dashboard_permission_level NOT NULL DEFAULT 'view',
    PRIMARY KEY (user_id, dashboard_id)
);
```

| Column        | Type                        | Constraints                              | Description                    |
| ------------- | --------------------------- | ---------------------------------------- | ------------------------------ |
| `user_id`     | `UUID`                      | `NOT NULL`, `REFERENCES users(id) ON DELETE CASCADE`, `PRIMARY KEY` | User ID                        |
| `dashboard_id`| `UUID`                      | `NOT NULL`, `REFERENCES dashboards(id) ON DELETE CASCADE`, `PRIMARY KEY` | Dashboard ID                   |
| `permission`  | `dashboard_permission_level` | `NOT NULL`, `DEFAULT 'view'`            | Access level                   |

**ENUM type:** `dashboard_permission_level` = `('view', 'edit', 'admin')`

**Permission levels:**

| Level    | Description                                      |
| -------- | ------------------------------------------------ |
| `view`   | Read-only access to dashboard and its data       |
| `edit`   | Can upload data and trigger processing           |
| `admin`  | Full control including dashboard management      |

**Indexes:**
- `dashboard_access_pkey` — Composite primary key `(user_id, dashboard_id)`
- `idx_dashboard_access_user` — B-tree index on `user_id`
- `idx_dashboard_access_dashboard` — B-tree index on `dashboard_id`

**Access control enforcement:** The `check_dashboard_access` function verifies the user's permission against this table on every dashboard-related API request. Users without an entry in this table cannot access the dashboard.

---

### `registration_requests` — Registration Requests

Stores user registration requests submitted via the public registration endpoint. Requests must be approved by an admin before a user account is created.

```sql
CREATE TABLE registration_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    status          registration_status NOT NULL DEFAULT 'pending',
    requested_by_ip INET,
    reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column            | Type            | Constraints                              | Description                    |
| ----------------- | --------------- | ---------------------------------------- | ------------------------------ |
| `id`              | `UUID`          | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `email`           | `VARCHAR(255)`  | `UNIQUE`, `NOT NULL`                     | Requested email address        |
| `status`          | `registration_status` | `NOT NULL`, `DEFAULT 'pending'`    | Request status                 |
| `requested_by_ip` | `INET`          | Nullable                                 | IP address of the requester    |
| `reviewed_by`     | `UUID`          | `REFERENCES users(id) ON DELETE SET NULL` | Admin who reviewed the request |
| `reviewed_at`     | `TIMESTAMPTZ`   | Nullable                                 | Review timestamp               |
| `created_at`      | `TIMESTAMPTZ`   | `NOT NULL`, `DEFAULT now()`             | Request creation timestamp     |

**ENUM type:** `registration_status` = `('pending', 'approved', 'rejected')`

**Status lifecycle:**
```
pending → approved  (user account created with temp password)
        → rejected
```

**Approval flow:**
1. User submits email via `POST /api/v1/auth/register-request`
2. Request created with `status = 'pending'`
3. Admin reviews via `GET /api/v1/admin/registration-requests`
4. Admin approves via `POST /api/v1/admin/registration-requests/:id/approve`
5. System creates user account with random temp password (`secrets.token_urlsafe(16)`)
6. Request updated to `status = 'approved'`

**Indexes:**
- `registration_requests_pkey` — primary key on `id`
- `registration_requests_email_key` — `UNIQUE` index on `email`
- `idx_registration_requests_reviewed_by` — B-tree index on `reviewed_by`

---

### `dashboard_filters` — Dashboard-Filter Links

Many-to-many join table linking dashboards to their associated filters. Filters are reusable across multiple dashboards.

```sql
CREATE TABLE dashboard_filters (
    dashboard_id    UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    filter_id       UUID NOT NULL REFERENCES filters(id) ON DELETE CASCADE,
    PRIMARY KEY (dashboard_id, filter_id)
);
```

| Column        | Type   | Constraints                              | Description                    |
| ------------- | ------ | ---------------------------------------- | ------------------------------ |
| `dashboard_id`| `UUID` | `NOT NULL`, `REFERENCES dashboards(id) ON DELETE CASCADE`, `PRIMARY KEY` | Dashboard ID                   |
| `filter_id`   | `UUID` | `NOT NULL`, `REFERENCES filters(id) ON DELETE CASCADE`, `PRIMARY KEY` | Filter ID                      |

**Indexes:**
- `dashboard_filters_pkey` — Composite primary key `(dashboard_id, filter_id)`; its composite primary key builds this unique index

There is no separate index on `dashboard_filters`. A non-unique index over the
same two columns was dropped by revision `f47ac18b5b9e` because it duplicated
the primary key's column set and only added write overhead.

**Note:** This table is defined in `src/mkobi/db/models/filters.py` using SQLAlchemy's `Table` construct (not a mapped class).

---

## Entity Relationship Diagram (Access)

```
users (*) ──────── (*) dashboard_access (*) ──────── (*) dashboards
  │                                                        │
  │                                                        │ (*)
  │                                                        │
  │                                                   dashboard_filters
  │                                                        │
  │                                                        │ (*)
  │                                                        │
  │                                                   filters
  │
  │                                              dashboard_filter_values (*)
  │
  │ (as reviewer)
  │
registration_requests
```

---

## Cross-References

- [Core Schema](./schema-core.md) — `users`, `layouts`, `dashboards`, `graphs`, `filters`
- [Processing Schema](./schema-processing.md) — `aggregated_data`, `processing_logs`, `processing_configs`
- [Indexes](./indexes.md) — All index definitions
- [Enums](./enums.md) — All StrEnum definitions
- [Auth API](../01-auth/auth-api.md) — Registration request flow
- [Admin API](../04-admin/admin-api.md) — Registration request approval
- [Security](../08-security/access-control.md) — Access control enforcement
- [Security Overview](../08-security/security-overview.md) — Rate limiting and credential enforcement
