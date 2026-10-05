---
id: schema-core
domain: database
tags:
  - schema
  - users
  - dashboards
  - layouts
  - graphs
  - filters
  - jsonb
  - uuid
related:
  - schema-processing
  - schema-access
  - indexes
  - enums
  - dashboards-api
---

# Core Schema

## Overview

The core schema contains the foundational tables for the BI Dashboard system: users, layouts, dashboards, graphs, and filters. These tables define the structural backbone of the application.

**Schema file:** `src/mkobi/db/models/`

---

## Design Principles

- **UUID primary keys** for all entity tables (except `aggregated_data` which uses `BIGSERIAL`)
- **JSONB columns** for flexible, schema-less data (graph configs, layout definitions, filter configs)
- **PostgreSQL ENUM types** for role, permission, graph type, and filter type columns
- **UTF-8 encoding** for full Cyrillic and Latin character support across all text columns
- **`ON DELETE CASCADE`** for dependent child records (graphs, aggregated data)
- **`ON DELETE SET NULL`** for optional references (layout_id, created_by)
- **`TIMESTAMPTZ`** for all timestamp columns to preserve timezone information
- **`gen_random_uuid()`** as the default for UUID primary keys (PostgreSQL native)

---

## Tables

### `users` — System Users

Stores user accounts with role-based access control.

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            user_role NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    force_password_change BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column          | Type         | Constraints                              | Description                    |
| --------------- | ------------ | ---------------------------------------- | ------------------------------ |
| `id`            | `UUID`       | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `email`         | `VARCHAR(255)` | `UNIQUE`, `NOT NULL`                    | User email address             |
| `password_hash` | `VARCHAR(255)` | `NOT NULL`                              | Bcrypt password hash           |
| `role`          | `user_role`  | `NOT NULL`, `DEFAULT 'viewer'`           | `admin` \| `editor` \| `viewer` |
| `is_active`     | `BOOLEAN`    | `NOT NULL`, `DEFAULT TRUE`               | Account activation flag        |
| `force_password_change` | `BOOLEAN` | `NOT NULL`, `DEFAULT FALSE`       | Forces password change on next login |
| `created_at`    | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Creation timestamp             |
| `updated_at`    | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Last update timestamp          |

**ENUM type:** `user_role` = `('admin', 'editor', 'viewer')`

**Indexes:**
- `idx_users_email` — `UNIQUE` index on `email`
- `idx_users_role` — B-tree index on `role`

> The `force_password_change` column is set to `TRUE` when an admin resets a user's password or approves a registration request. The `change_password()` service method clears this flag (`force_password_change=False`) after a successful password change, preventing an infinite force-change loop. The frontend checks this field in the login response and redirects to `/profile/change-password?force=true` when set.

---

### `layouts` — UI Layouts

Stores dashboard UI composition (grid structure, graph positions, filter bindings) without data bindings. Layouts are reusable across dashboards.

```sql
CREATE TABLE layouts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) UNIQUE NOT NULL,
    definition      JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column       | Type         | Constraints                              | Description                    |
| ------------ | ------------ | ---------------------------------------- | ------------------------------ |
| `id`         | `UUID`       | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `name`       | `VARCHAR(255)` | `UNIQUE`, `NOT NULL`                    | Layout name                    |
| `definition` | `JSONB`      | `NOT NULL`                               | UI structure (grid, graphs, filters, bindings) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Creation timestamp             |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Last update timestamp          |

**`definition` JSONB structure:**
```json
{
  "grid": [{"x": 0, "y": 0, "w": 6, "h": 4}],
  "graphs": ["g1", "g2"],
  "filters": ["year"],
  "bindings": [
    {"filter": "year", "graphs": ["g1", "g2"]}
  ]
}
```

**Indexes:**
- `idx_layouts_name` — `UNIQUE` index on `name`

---

### `dashboards` — Dashboards

Stores dashboard definitions. Each dashboard references a layout and is created by a user.

```sql
CREATE TABLE dashboards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) UNIQUE NOT NULL,
    description     TEXT,
    config          JSONB,
    layout_id       UUID REFERENCES layouts(id) ON DELETE SET NULL,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column        | Type         | Constraints                              | Description                    |
| ------------- | ------------ | ---------------------------------------- | ------------------------------ |
| `id`          | `UUID`       | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `name`        | `VARCHAR(255)` | `UNIQUE`, `NOT NULL`                    | Dashboard name                 |
| `description` | `TEXT`       | Nullable                                 | Dashboard description          |
| `config`      | `JSONB`      | Nullable                                 | Dashboard-level configuration  |
| `layout_id`   | `UUID`       | `REFERENCES layouts(id) ON DELETE SET NULL` | Associated layout (optional)   |
| `created_by`  | `UUID`       | `REFERENCES users(id) ON DELETE SET NULL` | Creator user (optional)        |
| `created_at`  | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Creation timestamp             |
| `updated_at`  | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Last update timestamp          |

**Indexes:**
- `idx_dashboards_name` — `UNIQUE` index on `name`
- `idx_dashboards_layout_id` — B-tree index on `layout_id`
- `idx_dashboards_created_by` — B-tree index on `created_by`

**Cascading behavior:** Deleting a dashboard removes all associated graphs, aggregated data, access entries, filter links, and processing configs via `ON DELETE CASCADE`.

---

### `graphs` — Graph Definitions

Stores chart configurations within a dashboard. Each graph belongs to exactly one dashboard.

```sql
CREATE TABLE graphs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id    UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    type            graph_type NOT NULL,
    config          JSONB NOT NULL,
    dimensions      JSONB NOT NULL,
    metrics         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dashboard_id, name)
);
```

| Column        | Type         | Constraints                              | Description                    |
| ------------- | ------------ | ---------------------------------------- | ------------------------------ |
| `id`          | `UUID`       | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `dashboard_id`| `UUID`       | `NOT NULL`, `REFERENCES dashboards(id) ON DELETE CASCADE` | Parent dashboard               |
| `name`        | `VARCHAR(255)` | `NOT NULL`                              | Graph name (unique per dashboard) |
| `type`        | `graph_type` | `NOT NULL`                               | `bar` \| `line` \| `pie` \| `table` |
| `config`      | `JSONB`      | `NOT NULL`                               | Axis config, colors, display options |
| `dimensions`  | `JSONB`      | `NOT NULL`                               | List of dimension fields       |
| `metrics`     | `JSONB`      | `NOT NULL`                               | List of metric fields          |
| `created_at`  | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Creation timestamp             |

**ENUM type:** `graph_type` = `('bar', 'line', 'pie', 'table')`

**`config` JSONB example:**
```json
{
  "x_axis": "month",
  "y_axis": "revenue",
  "orientation": "v",
  "barmode": "group",
  "colors": ["#1f77b4", "#ff7f0e"],
  "sort_x": {"by": "month", "direction": "asc"},
  "sort_color": {"by": "revenue_sum", "direction": "desc"}
}
```

**Indexes:**
- `idx_graphs_dashboard_name` — `UNIQUE` index on `(dashboard_id, name)`
- `idx_graphs_dashboard` — B-tree index on `dashboard_id`

---

### `filters` — Global Filters

Stores reusable filter definitions. Filters are not tied to a specific dashboard; they are linked via the `dashboard_filters` many-to-many join table.

```sql
CREATE TABLE filters (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) UNIQUE NOT NULL,
    type            filter_type NOT NULL,
    config          JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column       | Type         | Constraints                              | Description                    |
| ------------ | ------------ | ---------------------------------------- | ------------------------------ |
| `id`         | `UUID`       | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `name`       | `VARCHAR(255)` | `UNIQUE`, `NOT NULL`                    | Filter name                    |
| `type`       | `filter_type` | `NOT NULL`                              | `select` \| `multiselect` \| `range` \| `date` |
| `config`     | `JSONB`      | `NOT NULL`                               | Filter configuration           |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Creation timestamp             |

**ENUM type:** `filter_type` = `('select', 'multiselect', 'range', 'date')`

**`config` JSONB example:**
```json
{
  "field": "year",
  "source": "dims",
  "multi": false
}
```

**Indexes:**
- `idx_filters_name` — `UNIQUE` index on `name`

---

## Entity Relationship Diagram (Core)

```
users                  layouts
  │ 1                    │ 1
  │                      │
  │ *                    │ *
dashboards ─────────── layouts (layout_id)
  │ 1
  │
  │ *
graphs
  │
  │ (referenced by aggregated_data)

filters
  │
  │ (linked via dashboard_filters)
dashboards
```

---

## Cross-References

- [Processing Schema](./schema-processing.md) — `aggregated_data`, `processing_logs`, `processing_configs`
- [Access Schema](./schema-access.md) — `dashboard_access`, `registration_requests`, `dashboard_filters`
- [Indexes](./indexes.md) — All index definitions
- [Enums](./enums.md) — All StrEnum definitions
- [Dashboards API](../02-dashboards/dashboards-api.md) — API endpoints using these tables
- [Auth API](../01-auth/auth-api.md) — Authentication and user management
- [Data Flow](../00-overview/data-flow.md) — How data flows through these tables
- [Access Control](../08-security/access-control.md) — Permission model and enforcement
