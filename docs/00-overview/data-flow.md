---
id: data-flow
domain: overview
tags:
  - data-pipeline
  - upload
  - processing
  - aggregation
  - storage
  - visualization
related:
  - system-overview
  - processing-api
  - schema-core
  - dashboards-api
---

# Data Flow

## End-to-End Flow: Upload to Display

```
User (Browser)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  1. UPLOAD                                              │
│  POST /api/v1/upload/:dashboard_id?mode=overwrite|append │
│  ├─ File saved to temp directory (platformdirs)         │
│  ├─ MIME-type validated (.csv, .csv.gz)                 │
│  ├─ File size checked                                   │
│  └─ Processing task queued (TaskQueue)                  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  2. PARSE                                               │
│  ├─ Read file with Polars (UTF-8 encoding)              │
│  └─ Validate structure against processing config        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  3. TRANSFORM                                           │
│  ├─ Apply transformations per LoaderConfig              │
│  ├─ Custom metrics evaluated (formula parser)           │
│  └─ Data types normalized                               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  4. AGGREGATE                                           │
│  ├─ Per-chart GROUP BY (graph.dims + filter.dims)       │
│  ├─ YoY (Year-over-Year) calculations                   │
│  ├─ Share/ratio computations                            │
│  ├─ Custom metric aggregation                           │
│  ├─ Filter values extracted from aggregated data        │
│  └─ Full recalculation (all aggregates rebuilt)         │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  5. SAVE TO POSTGRESQL                                  │
│  ├─ Write to aggregated_data table (JSONB dims+metrics) │
│  ├─ Write to dashboard_filter_values table (filter UI)  │
│  ├─ JSONB keys normalized (sorted) for UPSERT           │
│  └─ Temp file deleted                                   │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  6. FRONTEND REQUESTS DATA                              │
│  GET /api/v1/data/aggregated                            │
│     ?dashboard_id=:id&graph_id=:id&filters=...          │
│  ├─ Access check (user ↔ dashboard)                     │
│  ├─ Filters applied (backend: SQL/Polars)               │
│  └─ JSON response with chart data                       │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  7. RENDER                                              │
│  ├─ React SPA receives data via TanStack Query          │
│  ├─ Plotly.js React renders charts                      │
│  └─ Filters update all linked graphs                    │
└─────────────────────────────────────────────────────────┘
```

## Upload Details

* **Formats**: `.csv`, `.csv.gz`
* **Encoding**: UTF-8 (or as specified in `processing_config.settings.encoding`)
* **Character Support**: Full Cyrillic and Latin character set support across database, backend, and frontend
* **Date Format**: Standard user-facing format is `dd/mm/yyyy`; processing config supports flexible input parsing via `date_format` setting
* **Lifecycle**: File is uploaded → processed → deleted
* **History**: Not stored (only aggregated results persist)
* **Mode**: `overwrite` (replaces all data) or `append` (adds to existing)
* **CSV parsing**: Separator, encoding, column types, and decimal separator are read from the dashboard's `processing_config` and applied during the parse phase

## Processing Details

* **Trigger**: File upload
* **Pipeline**:
  1. Read with Polars
  2. Transform per dashboard configuration
  3. Aggregate: groupby, YoY, shares, custom metrics
* **Result**: Full recalculation, written to PostgreSQL
* **Background**: Processing runs asynchronously via task queue (in-memory `TaskQueue` for MVP; Redis + RQ for production). See [Task Queue](../03-processing/task-queue.md) for the migration plan.
* **File processing service**: `file_processing.py` handles validation, upload, and task orchestration.
* **Background worker**: `data_worker.py` provides `process_csv_background` (async) and `process_csv_background_sync` (sync RQ wrapper) with mode-aware data persistence (`overwrite` clears old data, `append` keeps it).
* **Status tracking**: `processing_logs` table (`started` → `uploaded` → `processing` → `completed`/`failed`). The `processing` state is committed in its own transaction before the work starts and the terminal state commits with the aggregate write afterwards, so a killed worker's row stays `processing` for the periodic stale-processing sweep to find.
* **Processing config wiring**: The dashboard's `processing_config` (from `processing_configs` table) is automatically fetched and passed through the upload pipeline to the background worker, ensuring transformations use the correct loader settings and custom metrics.
* **Transaction safety**: File move to final path occurs **after** DB commit to prevent orphan files. On commit failure, the file remains at the temp path for cleanup.

## Aggregation Architecture

The aggregation step uses `AggregationService` which performs **per-chart GROUP BY** with Polars. For each graph, the GROUP BY columns include both the graph's dimensions and the dashboard's filter dimensions. This produces one row per unique combination of dimension values with aggregated metric values (sum by default).

After aggregation, sorting is applied to ensure proper chart visualization:
- X-axis sorted chronologically (uses `year`/`month` columns if present, otherwise sorts by X dimension directly)
- Color dimension sorted by total metric volume (descending) so larger values appear at the bottom of stacked bars

The `_apply_chart_sorting()` method calculates color totals via GROUP BY, joins back to the main dataframe, and applies multi-column sort before converting to output records. Helper columns (prefixed with `_`) are excluded from the final metrics output.

After sorting, distinct filter values are extracted from the aggregated records and persisted to the `dashboard_filter_values` table. These values are used to dynamically populate filter UI controls (checkboxes, dropdowns) when the filter's `config.source` is set to `"data"`.

```
CSV data → AggregationService.aggregate_for_dashboard()
         ├─ For each graph: GROUP BY (graph.dims + filter.dims)
         ├─ Produce aggregated records (dims + metrics)
         ├─ Apply chart sorting (_color_total desc, x-axis asc)
         ├─ StorageManager.save_aggregates() → aggregated_data table
         └─ extract_filter_values() → dashboard_filter_values table
```

## Storage Details

* **Only aggregated data is stored** (raw files are not persisted)
* **Structure**: Single `aggregated_data` table using JSONB for all dashboards
  * `dims` — dimension values (key-value for filters and axes)
  * `metrics` — metric values (key-value for display)
* **Filter value cache**: `dashboard_filter_values` stores distinct values per (dashboard, filter_name). Automatically rebuilt on each upload. See [Processing Schema](../09-database/schema-processing.md) for the table definition.
* **Data is shared** (not user-dependent; access controlled via `dashboard_access` table). See [Access Control](../08-security/access-control.md) for the permission model.
* **JSONB normalization**: `dims` keys are sorted recursively before writes to ensure deterministic UPSERT conflict detection

## Related Documentation

* [Technology Stack — overview.md](./overview.md)
* [Auth & Access Control](../01-auth/auth-api.md) — Authentication and role-based access
* [Database Schema](../09-database/schema-core.md) — Core table definitions for `dashboards`, `graphs`, `filters`
* [Processing Configuration](../03-processing/processing-api.md) — Upload, processing pipeline, and data endpoints
* [Security Overview](../08-security/security-overview.md) — Rate limiting, file upload security, credential enforcement
* [Task Queue](../03-processing/task-queue.md) — Background processing and migration plan
