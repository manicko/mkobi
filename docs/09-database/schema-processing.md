---
id: schema-processing
domain: database
tags:
  - aggregated-data
  - processing-logs
  - processing-configs
  - polars
  - jsonb-normalization
  - upsert
related:
  - schema-core
  - schema-access
  - indexes
  - processing-api
  - enums
---

# Processing Schema

## Overview

The processing schema contains tables related to data processing: aggregated data storage, processing logs, and processing configurations. These tables support the CSV upload, transformation, aggregation, and visualization pipeline.

**Schema file:** `src/mkobi/db/models/`

---

## Storage Context

The system stores only aggregated data — raw CSV files are processed and discarded. The processing pipeline:

1. CSV file uploaded to temporary directory (`platformdirs`)
2. File parsed with **Polars**
3. Data transformed per `processing_configs.settings`
4. Aggregations computed (groupby, YoY, shares, custom metrics)
5. Results stored in `aggregated_data` (`dims` + `metrics` JSONB)
6. Temporary file deleted

**JSONB normalization:** `dims` keys are sorted recursively before write operations to ensure deterministic UPSERT conflict detection. PostgreSQL JSONB equality is sensitive to key ordering; without normalization, records with identical semantics but different key insertion orders would be treated as distinct, causing duplicate data.

---

## Tables

### `aggregated_data` — Aggregated Chart Data (CORE)

Stores pre-computed aggregated data for dashboard graphs. Each row represents one chart data point.

```sql
CREATE TABLE aggregated_data (
    id              BIGSERIAL PRIMARY KEY,
    dashboard_id    UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    graph_id        UUID NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
    dims            JSONB NOT NULL,
    metrics         JSONB NOT NULL
);
```

| Column        | Type         | Constraints                              | Description                    |
| ------------- | ------------ | ---------------------------------------- | ------------------------------ |
| `id`          | `BIGSERIAL`  | `PRIMARY KEY`                            | Auto-incrementing identifier   |
| `dashboard_id`| `UUID`       | `NOT NULL`, `REFERENCES dashboards(id) ON DELETE CASCADE` | Parent dashboard               |
| `graph_id`    | `UUID`       | `NOT NULL`, `REFERENCES graphs(id) ON DELETE CASCADE` | Associated graph               |
| `dims`        | `JSONB`      | `NOT NULL`                               | Dimension values (key-value)   |
| `metrics`     | `JSONB`      | `NOT NULL`                               | Metric values (key-value)      |

**`dims` JSONB example:**
```json
{
  "year": "2024",
  "month": "January",
  "category": "Electronics"
}
```

**`metrics` JSONB example:**
```json
{
  "revenue": 150000.00,
  "cost": 95000.00,
  "profit": 55000.00
}
```

**Indexes:**
- `idx_aggregated_data_graph_id` — B-tree index on `graph_id`
- `idx_aggregated_data_dashboard_id` — B-tree index on `dashboard_id`
- `idx_aggregated_data_dashboard_graph` — Composite B-tree index on `(dashboard_id, graph_id)`
- `idx_aggregated_data_dims_gin` — GIN index on `dims` (for JSONB containment queries)
- `uq_aggregated_data_dashboard_graph_dims` — Unique index on `(dashboard_id, graph_id, dims::text)` for UPSERT conflict detection

**JSONB normalization note:** The `dims` column uses recursive key sorting before writes. This ensures that `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` produce identical JSONB representations, enabling reliable UPSERT operations via the unique index on `dims::text`.

### UPSERT Expression Index

The unique index `uq_aggregated_data_dashboard_graph_dims` is defined as an **expression index**:

```sql
CREATE UNIQUE INDEX uq_aggregated_data_dashboard_graph_dims
ON aggregated_data (dashboard_id, graph_id, ((dims)::text));
```

Because the index includes a PostgreSQL expression (`((dims)::text)`), the `ON CONFLICT` clause in UPSERT statements must use the exact same expression rather than a plain column reference. The code uses `text("((dims)::text)")` in SQLAlchemy to match the expression index:

```python
stmt.on_conflict_do_update(
    index_elements=[
        AggregatedData.dashboard_id,
        AggregatedData.graph_id,
        text("((dims)::text)"),
    ],
    set={"metrics": stmt.excluded.metrics},
)
```

Using `AggregatedData.dims` (a plain column reference) would generate `ON CONFLICT (dashboard_id, graph_id, dims)`, which fails with `InvalidColumnReferenceError` because no unique index matches that plain column specification. The expression index requires the explicit `((dims)::text)` form.

**Affected methods:** `StorageManager.upsert_aggregate()` and `StorageManager._bulk_upsert()`.

---

### `dashboard_filter_values` — Filter Value Cache

Stores distinct filter values extracted from aggregated data during CSV processing. Used to populate filter UI checkboxes when a filter's `config.source` is set to `"data"`.

```sql
CREATE TABLE dashboard_filter_values (
    id              BIGSERIAL PRIMARY KEY,
    dashboard_id    UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    filter_name     VARCHAR(255) NOT NULL,
    filter_value    VARCHAR(1024) NOT NULL
);
```

| Column        | Type         | Constraints                              | Description                    |
| ------------- | ------------ | ---------------------------------------- | ------------------------------ |
| `id`          | `BIGSERIAL`  | `PRIMARY KEY`                            | Auto-incrementing identifier   |
| `dashboard_id`| `UUID`       | `NOT NULL`, `REFERENCES dashboards(id) ON DELETE CASCADE` | Parent dashboard               |
| `filter_name` | `VARCHAR(255)` | `NOT NULL`                             | Filter/dimension name          |
| `filter_value`| `VARCHAR(1024)` | `NOT NULL`                             | Distinct value for the filter  |

**Lifecycle:** Values are extracted from aggregated data after each CSV upload and cleared/re-populated on subsequent uploads (idempotent overwrite). This table acts as a cache — it contains no data that cannot be regenerated from `aggregated_data`.

**Indexes:**
- `uq_dashboard_filter_values` — `UNIQUE` index on `(dashboard_id, filter_name, filter_value)` for idempotent writes
- `idx_dashboard_filter_values_lookup` — B-tree index on `(dashboard_id, filter_name)` for fast lookup by dashboard + filter name

See [Filter Value Source](../02-dashboards/dashboards-api.md#filter-value-source) for details on how filters use this table vs. static options.

---

### `processing_logs` — Processing History

Tracks the status of data processing tasks from start to completion or failure.

```sql
CREATE TABLE processing_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id    UUID REFERENCES dashboards(id) ON DELETE SET NULL,
    status          processing_status NOT NULL,
    message         VARCHAR(1000),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
```

| Column        | Type            | Constraints                              | Description                    |
| ------------- | --------------- | ---------------------------------------- | ------------------------------ |
| `id`          | `UUID`          | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique identifier              |
| `dashboard_id`| `UUID`          | `REFERENCES dashboards(id) ON DELETE SET NULL` | Associated dashboard (optional) |
| `status`      | `processing_status` | `NOT NULL`                           | Current processing status      |
| `message`     | `VARCHAR(1000)` | Nullable                                 | Error or status message        |
| `started_at`  | `TIMESTAMPTZ`   | Nullable                                 | Processing start timestamp     |
| `finished_at` | `TIMESTAMPTZ`   | Nullable                                 | Processing end timestamp       |

**ENUM type:** `processing_status` = `('started', 'uploaded', 'processing', 'completed', 'failed')`

**Status lifecycle:**
```
started → uploaded → processing → completed
                            ↘ failed
```

There is no `success` value — it was a legacy alias of `completed` and was removed
by revision `4479eb53fd4e`.

**Indexes:**
- `idx_processing_logs_dashboard_id` — B-tree index on `dashboard_id`
- `idx_processing_logs_status_finished_at` — B-tree index on `(status, finished_at)`
- `idx_processing_logs_status_started_at` — B-tree index on `(status, started_at)`
- `idx_processing_logs_started_at` — B-tree index on `started_at`, satisfying the repository's unconditional `ORDER BY started_at DESC`

---

### `processing_configs` — Processing Configuration

Stores data processing settings for each dashboard. One-to-one relationship with `dashboards`.

```sql
CREATE TABLE processing_configs (
    dashboard_id    UUID PRIMARY KEY REFERENCES dashboards(id) ON DELETE CASCADE,
    settings        JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column        | Type         | Constraints                              | Description                    |
| ------------- | ------------ | ---------------------------------------- | ------------------------------ |
| `dashboard_id`| `UUID`       | `PRIMARY KEY`, `REFERENCES dashboards(id) ON DELETE CASCADE` | Dashboard ID (also primary key) |
| `settings`    | `JSONB`      | `NOT NULL`                               | Processing configuration       |
| `updated_at`  | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()`             | Last update timestamp          |

**`settings` JSONB example:**
```json
{
  "loader": "sales_loader",
  "date_column": "event_date",
  "timezone": "UTC",
  "encoding": "UTF-8",
  "separator": ",",
  "decimal_separator": null,
  "column_types": {
    "revenue": "float",
    "cost": "float"
  },
  "date_format": null,
  "metric_agg": "sum"
}
```

**Available settings fields:**
| Field | Type | Description |
| ----- | ---- | ----------- |
| `loader` | string | Loader identifier for data source type |
| `date_column` | string | Primary date column for time-based operations |
| `timezone` | string | Timezone for date processing (default: "UTC") |
| `encoding` | string | File encoding (default: "UTF-8") |
| `separator` | string | CSV delimiter character (default: ",") |
| `decimal_separator` | string | Decimal separator for float columns (e.g., "," for EU format) |
| `column_types` | object | Column type casting map (e.g., `{"age": "int", "price": "float"}`) |
| `date_format` | string | Date format string for parsing input dates |
| `renames` | object | Column renaming map |
| `computed_fields` | array | Computed column expressions via formula parser |
| `filters` | array | Row-level filter conditions |
| `groupby` | array | Columns to group by |
| `aggregations` | array | Aggregation configuration definitions |
| `yoy_config` | object | Year-over-year comparison settings |
| `share_config` | object | Share calculation configuration |
| `custom_metrics` | array | Custom metric formulas |
| `metric_agg` | string | Default aggregation function for metrics (`sum`, `mean`, `min`, `max`, `count`) |

**Note:** This table stores configuration only, not business logic. Processing logic is implemented in the service layer (`src/mkobi/services/`).

---

## Entity Relationship Diagram (Processing)

```
dashboards (1) ──────── (*) aggregated_data
  │                      │
  │                      │ (*)
  │                      │
  │ (1)                  graphs
  │
  │ (1) ──────── (1) processing_configs
  │
  │ (1) ──────── (*) processing_logs
```

---

## Cross-References

- [Core Schema](./schema-core.md) — `users`, `layouts`, `dashboards`, `graphs`, `filters`
- [Access Schema](./schema-access.md) — `dashboard_access`, `registration_requests`, `dashboard_filters`
- [Indexes](./indexes.md) — All index definitions
- [Enums](./enums.md) — All StrEnum definitions
- [Processing API](../03-processing/processing-api.md) — Upload and processing endpoints
- [Task Queue](../03-processing/task-queue.md) — Background processing architecture
- [Data Flow](../00-overview/data-flow.md) — End-to-end data processing pipeline
- [Admin API](../04-admin/admin-api.md) — Processing log viewer
