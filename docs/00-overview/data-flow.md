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
│  └─ Processing task submitted to Redis / RQ             │
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
│  ├─ Dim VALUES stringified, so one category is one row  │
│  └─ Temp file unlinked AFTER the commit                 │
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
* **Background**: Processing runs asynchronously on a **Redis-backed RQ queue**. The application process only *submits*; the `rq-worker` container is the only executor. `src/mkobi/core/task_queue.py` is a thin RQ seam (`enqueue_job`, `get_rq_queue`) and holds no queue of its own. There is no in-process queue: the in-memory `asyncio.Queue` implementation was removed, and a test asserts the retired symbols are absent. See [Task Queue](../03-processing/task-queue.md) for the history and [Task Queue Migration](../11-guides/task-queue-migration.md) for the migration record.
* **File processing service**: `file_processing.py` handles validation, upload, and task orchestration.
* **Background worker**: `data_worker.py` provides `process_csv_background` (async) and `process_csv_background_sync` (sync RQ wrapper) with mode-aware data persistence (`overwrite` clears old data, `append` keeps it).
* **Status tracking**: `processing_logs` table. The vocabulary is exactly the five `ProcessingStatus` members — `started` → `uploaded` → `processing` → `completed` / `failed`. There is **no** `success` member; the retired database value was removed by a landed migration. The `processing` state is committed in its own transaction before the work starts and the terminal state commits with the aggregate write afterwards, so a killed worker's row stays `processing` for the periodic stale-processing sweep to find.
* **Processing config wiring**: The dashboard's `processing_config` (from `processing_configs` table) is automatically fetched and passed through the upload pipeline to the background worker, ensuring transformations use the correct loader settings and custom metrics.
* **Transaction safety**: The accepting path in `process_upload_with_session` **commits first**, then moves the file, then enqueues. The commit is the transaction boundary: a failure before it leaves no job in RQ and no file at a final path, and neither effect can be retracted by a rollback once done. A commit failure therefore leaves the file at the temp path, where the upload route's `finally` unlinks it; if the process dies before that, the age-based startup sweep reclaims it. The residual runs the other way: a failure between the commit and the move leaves a committed `uploaded` row with no file and no job, and a failure between the move and the enqueue leaves a file with no job (the enqueue handler unlinks the moved file). Both are reclaimed later by the orphan sweep, which now runs on the **periodic** reconciler loop rather than only at boot — see [Temp File Cleanup](../03-processing/file-cleanup.md).
* **Full recalculation is unconditional, because an empty selection now fails**: every upload rebuilds both `aggregated_data` and `dashboard_filter_values` from scratch. A selection that matches no graph is a **failed run**, not a silent success: the worker raises before either clear, names the skipped graphs in the detail, and leaves the previous rows and filter values in place.

## Aggregation Architecture

The aggregation step uses `AggregationService` which performs **per-chart GROUP BY** with Polars. For each graph, the GROUP BY columns include both the graph's dimensions and the dashboard's filter dimensions. The list is **de-duplicated in first-seen order**, so a filter whose name coincides with a graph dimension does not repeat the key (graph dimensions stay ahead of filter-only names). This produces one row per unique combination of dimension values with aggregated metric values (sum by default).

After aggregation, sorting is applied to ensure proper chart visualization:
- X-axis sorted chronologically (uses `year`/`month` columns if present, otherwise sorts by X dimension directly)
- Color dimension sorted by total metric volume (descending) so larger values appear at the bottom of stacked bars

The `_apply_chart_sorting()` method calculates color totals via GROUP BY, joins back to the main dataframe, and applies multi-column sort before converting to output records. Helper columns (prefixed with `_`) are excluded from the final metrics output.

After sorting, distinct filter values are extracted from the aggregated records and persisted to the `dashboard_filter_values` table. These values are used to dynamically populate filter UI controls (checkboxes, dropdowns) when the filter's `config.source` is set to `"data"`.

```
CSV data → AggregationService.aggregate_for_dashboard()
         ├─ For each graph: GROUP BY (graph.dims + filter.dims, de-duplicated)
         ├─ Produce aggregated records (dims + metrics)
         ├─ Apply chart sorting (_color_total desc, x-axis asc)
         ├─ StorageManager.save_aggregates() → aggregated_data table
         ├─ extract_filter_values() → dashboard_filter_values table
         └─ (no records for a graph) → run FAILS, naming the skipped graphs
```

## Storage Details

* **Only aggregated data is stored** (raw files are not persisted)
* **Structure**: Single `aggregated_data` table using JSONB for all dashboards
  * `dims` — dimension values (key-value for filters and axes)
  * `metrics` — metric values (key-value for display)
* **Filter value cache**: `dashboard_filter_values` stores distinct values per (dashboard, filter_name). Automatically rebuilt on each upload. See [Processing Schema](../09-database/schema-processing.md) for the table definition.
* **Data is shared** (not user-dependent; access controlled via `dashboard_access` table). See [Access Control](../08-security/access-control.md) for the permission model.
* **Dimension value canonicalisation**: every scalar `dims` value is stringified at the storage boundary (`StorageManager._canonicalize_dims` / `_canonicalize_dim_scalar`), so the same logical category is one row whether the frame held it as `Utf8` or `Int64`. `None` becomes `""`; a `date`/`datetime` keeps its ISO `T` separator; `metrics` are **not** canonicalised, because numbers there are the data.
* **Key sorting is cosmetic, not the identity rule**: `dims` keys are still sorted recursively before writes, but JSONB canonicalises object key order itself, so the sorting never provided index stability. What makes the UPSERT work is the scalar rule above. See the hand-over note in [Processing Schema](../09-database/schema-processing.md).
* **Read order is a stated contract**: the aggregated-data read paths order by ascending row id, which under `overwrite` reproduces the computed chart order because the dashboard's rows are deleted before re-inserting. `append` mode is the documented exception — see [Processing API](../03-processing/processing-api.md).

## Related Documentation

* [Technology Stack — overview.md](./overview.md)
* [Auth & Access Control](../01-auth/auth-api.md) — Authentication and role-based access
* [Database Schema](../09-database/schema-core.md) — Core table definitions for `dashboards`, `graphs`, `filters`
* [Processing Configuration](../03-processing/processing-api.md) — Upload, processing pipeline, and data endpoints
* [Security Overview](../08-security/security-overview.md) — Rate limiting, file upload security, credential enforcement
* [Task Queue](../03-processing/task-queue.md) — Historical record of the in-process queue and its removal
