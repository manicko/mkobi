---
id: indexes
domain: database
tags:
  - indexes
  - btree
  - gin
  - jsonb-indexing
  - query-optimization
  - unique-indexes
related:
  - schema-core
  - schema-processing
  - schema-access
  - enums
---

# Database Indexes

## Overview

This document lists all indexes defined across the 10 database tables. Indexes are created in the initial migration (`alembic/versions/7130ecb0388c_true_initial_migration.py`) and through subsequent migrations.

**Total indexes:** 7 (as specified in SPEC.md section 16.2) + additional unique indexes and constraints.

---

## Index Reference

### 1. `idx_aggregated_data_graph_id`

**Table:** `aggregated_data`
**Type:** B-tree
**Column(s):** `graph_id`

```sql
CREATE INDEX idx_aggregated_data_graph_id ON aggregated_data(graph_id);
```

**Purpose:** Accelerates lookups of aggregated data by graph. Used when fetching chart data for a specific graph.

---

### 2. `idx_aggregated_data_dashboard_id`

**Table:** `aggregated_data`
**Type:** B-tree
**Column(s):** `dashboard_id`

```sql
CREATE INDEX idx_aggregated_data_dashboard_id ON aggregated_data(dashboard_id);
```

**Purpose:** Accelerates lookups of aggregated data by dashboard. Used when loading all data for a dashboard view.

---

### 3. `idx_aggregated_data_dashboard_graph`

**Table:** `aggregated_data`
**Type:** B-tree (composite)
**Column(s):** `dashboard_id`, `graph_id`

```sql
CREATE INDEX idx_aggregated_data_dashboard_graph ON aggregated_data(dashboard_id, graph_id);
```

**Purpose:** Accelerates queries that filter by both dashboard and graph simultaneously. Optimizes the most common data retrieval pattern.

---

### 4. `idx_aggregated_data_dims_gin`

**Table:** `aggregated_data`
**Type:** GIN (Generalized Inverted Index)
**Column(s):** `dims`

```sql
CREATE INDEX idx_aggregated_data_dims_gin ON aggregated_data USING GIN (dims);
```

**Purpose:** A GIN index declared on the `dims` column. It is currently **unused by the application**, and that is a recorded, accepted state — not a justification for the index. The backend does **not** emit JSONB containment operators; the query path extracts individual keys with `->>` equality per key, and `->>` does not reach a GIN index of this shape. `pg_stat_user_indexes` reports `idx_scan = 0, idx_tup_read = 0` for this index, so it is unreachable from either predicate form. The index is retained by decision; a separate decision record (`D-14-B`, plan 14) owns that and records the choice to keep it.

**Note:** GIN is not the optimal index type for the queries this schema runs. Neither `@>` (JSONB containment) nor `->>` (key extraction with equality) reaches this index in the measured workload, and the speed comparison that used to be quoted here does not reproduce. GIN index size tracks the number of distinct keys and distinct values per document rather than the row count, so no per-volume write-cost constant can be derived from it.

---

### 5. `idx_dashboard_access_user`

**Table:** `dashboard_access`
**Type:** B-tree
**Column(s):** `user_id`

```sql
CREATE INDEX idx_dashboard_access_user ON dashboard_access(user_id);
```

**Purpose:** Accelerates lookups of all dashboards a user has access to. Used when listing a user's accessible dashboards (`GET /api/v1/dashboards/my`).

---

### 6. `idx_dashboard_access_dashboard`

**Table:** `dashboard_access`
**Type:** B-tree
**Column(s):** `dashboard_id`

```sql
CREATE INDEX idx_dashboard_access_dashboard ON dashboard_access(dashboard_id);
```

**Purpose:** Accelerates lookups of all users who have access to a specific dashboard. Used for access management in the admin panel.

---

### 7. `idx_graphs_dashboard`

**Table:** `graphs`
**Type:** B-tree
**Column(s):** `dashboard_id`

```sql
CREATE INDEX idx_graphs_dashboard ON graphs(dashboard_id);
```

**Purpose:** Accelerates lookups of all graphs belonging to a dashboard. Used when loading graph definitions for a dashboard view.

---

## Additional Indexes

The following indexes are also defined in the schema but are not part of the 7 core indexes listed in SPEC.md section 16.2:

| Index Name                                | Table                | Type      | Column(s)              | Purpose                          |
| ----------------------------------------- | -------------------- | --------- | ---------------------- | -------------------------------- |
| `idx_users_email`                         | `users`              | `UNIQUE`  | `email`                | Enforce unique emails            |
| `idx_users_role`                          | `users`              | B-tree    | `role`                 | Filter users by role             |
| `idx_layouts_name`                        | `layouts`            | `UNIQUE`  | `name`                 | Enforce unique layout names      |
| `idx_dashboards_name`                     | `dashboards`         | `UNIQUE`  | `name`                 | Enforce unique dashboard names   |
| `idx_graphs_dashboard_name`               | `graphs`             | `UNIQUE`  | `dashboard_id`, `name` | Enforce unique graph names per dashboard |
| `idx_filters_name`                        | `filters`            | `UNIQUE`  | `name`                 | Enforce unique filter names      |
| `idx_dashboard_filters_dashboard_filter`  | `dashboard_filters`  | `UNIQUE`    | `dashboard_id`, `filter_id` | Primary key index (replaces redundant non-unique index) |
| `idx_processing_logs_dashboard_id`        | `processing_logs`    | B-tree    | `dashboard_id`         | Filter logs by dashboard         |
| `uq_aggregated_data_dashboard_graph_dims` | `aggregated_data`    | `UNIQUE`  | `dashboard_id`, `graph_id`, `((dims)::text)` | UPSERT conflict detection (expression index) |
| `uq_dashboard_filter_values`              | `dashboard_filter_values` | `UNIQUE` | `dashboard_id`, `filter_name`, `filter_value` | Idempotent filter value writes |
| `idx_dashboard_filter_values_lookup`      | `dashboard_filter_values` | B-tree | `dashboard_id`, `filter_name` | Fast lookup of filter values by dashboard + name |
| `idx_processing_logs_status_finished_at` | `processing_logs` | B-tree | `status`, `finished_at` | Optimized status-based filtering for cleanup queries |

---

## Expression Indexes

### `uq_aggregated_data_dashboard_graph_dims`

This is a **unique expression index** — it includes a PostgreSQL expression rather than a plain column reference:

```sql
CREATE UNIQUE INDEX uq_aggregated_data_dashboard_graph_dims
ON aggregated_data (dashboard_id, graph_id, ((dims)::text));
```

The `((dims)::text)` expression casts the JSONB `dims` column to text for deterministic comparison. This is necessary for UPSERT conflict detection because PostgreSQL JSONB equality is sensitive to key ordering. Combined with recursive key sorting in the application layer, this ensures that dimension sets with identical semantics produce identical text representations.

**Important:** The `ON CONFLICT` clause in SQLAlchemy UPSERT statements must use the matching expression:

```python
text("((dims)::text)")
```

A plain column reference (`AggregatedData.dims`) would fail with `InvalidColumnReferenceError` because no unique index matches that specification.

---

## Index Strategy Summary

| Pattern                    | Index Type | Tables Affected                          |
| -------------------------- | ---------- | ---------------------------------------- |
| Primary key lookups        | Hash (implicit) | All tables                          |
| Foreign key lookups        | B-tree     | `aggregated_data`, `dashboard_access`, `graphs`, `processing_logs` |
| JSONB containment queries  | GIN        | `aggregated_data` (dims)                 |
| Unique constraints         | `UNIQUE`   | `users`, `layouts`, `dashboards`, `graphs`, `filters`, `aggregated_data` |
| Composite filters          | B-tree     | `aggregated_data`, `dashboard_access`, `dashboard_filters` |

---

## Cross-References

- [Core Schema](./schema-core.md) — Core table definitions
- [Processing Schema](./schema-processing.md) — Processing table definitions
- [Access Schema](./schema-access.md) — Access table definitions
- [Enums](./enums.md) — All StrEnum definitions
- [Dashboards API](../02-dashboards/dashboards-api.md) — Query patterns using these indexes
- [Processing API](../03-processing/processing-api.md) — Data retrieval and filter query patterns
