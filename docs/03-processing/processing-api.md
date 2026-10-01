---
id: processing-api
domain: processing
tags:
  - upload
  - csv
  - polars
  - aggregation
  - background-tasks
  - data-endpoints
  - processing-logs
related:
  - task-queue
  - file-cleanup
  - dashboards-api
  - schema-processing
  - data-flow
  - security-overview
---

# Processing API

## Overview

The processing API handles CSV file upload, data processing (via Polars), background task execution, and aggregated data retrieval. All endpoints are part of the `/api/v1` route group.

**Processing trigger:** File upload initiates a full recalculation of all aggregates for the target dashboard.

**Base path:** `/api/v1`

---

## Data Upload

### Upload CSV File

Upload a CSV or CSV.gz file to a specific dashboard. The file is saved to a temporary directory (`platformdirs`), processed, and then deleted. File history is not retained.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/upload/:dashboard_id`                     |
| **Auth level** | Editor+                                            |
| **Query param**| `mode` — `overwrite` (default) or `append`         |
| **Body**       | `multipart/form-data` with file field              |

**Request headers:**

```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Constraints:**

- Allowed file extensions: `.csv`, `.csv.gz`
- Allowed MIME types: `text/csv`, `application/gzip`, `application/x-gzip`
- **MIME type detection:** Server-side content sniffing using `python-magic` (reads first 2KB of file bytes to detect actual MIME type — does not trust client `Content-Type` header). Falls back to extension-based detection if `libmagic` is unavailable.
- **Character Support:** UTF-8 encoding with full Cyrillic and Latin character support. All string data is stored and rendered in Unicode without restrictions.
- **Date Format:** Input dates are parsed according to `processing_config.settings.date_format`. Standard user-facing display format is `dd/mm/yyyy`.
- Rate limiting is enforced on upload endpoints
- Maximum file size is enforced on the backend, including cumulative byte tracking during streaming writes (applies even when the client does not provide `Content-Length`)
- Temporary files are deleted after processing

**Response** (`200 OK`):

```json
{
  "task_id": "<uuid>",
  "filename": "data.csv",
  "dashboard_id": "<uuid>",
  "status": "started",
  "message": "File uploaded successfully. Processing queued.",
  "uploaded_at": "2026-05-31T12:00:00Z"
}
```

The upload endpoint returns a structured `UploadResponse` model (not an ad-hoc dict), providing consistent fields for frontend consumption.

---

## Processing Pipeline

### Pipeline Stages

The data processing pipeline is triggered automatically after file upload or manually via the process endpoint.

```
Upload → Parse (Polars) → Transform (processing_config) → Aggregate → Save to PostgreSQL
```

### Stage Details

| Stage | Description |
| ----- | ----------- |
| **1. Upload** | File saved to temporary directory (`UPLOAD__TEMP_DIR`, defaults to `platformdirs`; see [Docker Guide](../11-guides/docker.md#application-data-directories) for mounted paths). MIME type and size validated. |
| **2. Parse** | File read using Polars; CSV parsing config (separator, encoding, column_types) applied from `processing_config` |
| **3. Transform** | Post-read transformations applied (e.g., decimal separator normalization for float columns) |
| **4. Aggregate** | Per-chart GROUP BY via `AggregationService`: for each graph, GROUP BY columns = graph.dimensions + dashboard.filter.dimensions; metric values summed |
| **5. Filter Value Extraction** | Distinct values for each dashboard filter dimension extracted from aggregated records |
| **6. Save** | Aggregated records written to `aggregated_data` table; filter values written to `dashboard_filter_values` table (idempotent overwrite) |
| **7. Cleanup** | Temporary file deleted |

**Important:** Each upload triggers a **full recalculation** — both `aggregated_data` and `dashboard_filter_values` are rebuilt from scratch. There is no incremental aggregation.

### Aggregation Architecture

The `AggregationService` (`src/mkobi/services/aggregation_service.py`) performs per-chart Polars GROUP BY aggregation. Key characteristics:

- GROUP BY columns for each graph = `graph.dimensions` + `dashboard.filters.dimensions`
- All dimension values stored as strings (`str()` conversion) for consistent JSON serialization
- Metric aggregation default: `sum` (configurable via `metric_agg` parameter)
- Filter values are extracted after aggregation via `extract_filter_values()` which scans all aggregated records for distinct values per filter name

### Processing Configuration Wiring

The upload pipeline automatically fetches the dashboard's `processing_config` from the database and passes it through to the background worker. This ensures that data transformations (LoaderConfig, custom metrics, timezone settings defined in `processing_configs.settings` JSONB) are applied consistently without manual intervention. When no config exists, the pipeline uses safe defaults.

### Processing Modes

| Mode | Enum Value | Description |
| ---- | ----------- | ----------- |
| Overwrite | `UploadMode.OVERWRITE` | Replaces all existing aggregated data for the dashboard |
| Append | `UploadMode.APPEND` | Adds to existing aggregated data |

---

## Background Processing

CSV loading and processing runs asynchronously through a background task queue.

### Task Lifecycle

```
started → uploaded → processing → completed/failed
```

The worker's transition to `processing` is committed in its own short
transaction *before* the pipeline runs, and the terminal transition commits
with the aggregate write in the main transaction. The row is therefore truthful
to an independent reader for the whole run, and a worker killed mid-job leaves
the row in `processing` for the periodic stale-processing sweep to find.

| Status | Enum Value | Description |
| ------ | ----------- | ----------- |
| Started | `ProcessingStatus.STARTED` | Task created, file upload initiated |
| Uploaded | `ProcessingStatus.UPLOADED` | File saved to temporary storage, not yet picked up by a worker |
| Processing | `ProcessingStatus.PROCESSING` | Pipeline execution in progress |
| Completed | `ProcessingStatus.COMPLETED` | Processing completed successfully |
| Failed | `ProcessingStatus.FAILED` | Processing encountered an error |

`GET /upload/status/{task_id}` can now genuinely return `status="processing"`
with `progress=50` mid-job; previously the row stayed `uploaded` until it
jumped straight to `completed`, so that branch was unreachable.

### Task Queue

The current implementation uses an in-memory `TaskQueue` (MVP). For production, a migration to Redis/RQ is planned. See [Task Queue Migration](task-queue.md) for the complete migration plan.

### Trigger Processing (Manual)

Manually trigger processing for a previously uploaded file.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/upload/:dashboard_id/process`             |
| **Auth level** | Editor+                                            |
| **Query param**| `task_id` — UUID of the processing task            |

**Constraints:**

- **Task ownership validation:** The endpoint validates that the requested task belongs to the specified dashboard. If the task's `dashboard_id` does not match the URL parameter, the request is rejected. This prevents cross-dashboard task triggering.

**Response** (`200 OK`):

```json
{
  "task_id": "<uuid>",
  "status": "processing"
}
```

### Check Processing Status

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/upload/status/:task_id`                   |
| **Auth level** | Editor+                                            |

**Response** (`200 OK`):

 ```json
 {
   "task_id": "<uuid>",
   "status": "processing",
   "progress": 50,
   "message": "Aggregating data...",
   "started_at": "2026-05-18T12:00:00Z",
   "finished_at": null
 }
 ```

### Get Processing Result

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/upload/result/:task_id`                   |
| **Auth level** | Editor+                                            |

**Response** (`200 OK`):

```json
{
  "task_id": "<uuid>",
  "status": "success",
  "rows_processed": 15000,
  "graphs_affected": 4
}
```

> The `ProcessingResult` model also includes an optional `data` field with details about the processed data (columns, row count, preview). See [Data Models](#data-models) below.

---

## Custom Metrics (Formula Parser)

Custom metrics are defined as formulas referencing column names with basic arithmetic operators.

### Supported Syntax

- Simple binary expressions with column names: `revenue - cost`, `profit / revenue * 100`
- **Numeric literals** (e.g., `100`, `3.14`, `-50`) are supported and can be used directly in expressions like `revenue * 100` or `cost + 50`
- Operators: `+`, `-`, `*`, `/`

### Limitations [HIGH-RISK]

The formula parser has the following limitations:

- **Not supported:** parentheses, nested expressions
- **Not supported:** column names with special characters or spaces
- **Not supported:** unary operators (except negative numeric literals like `-50` in expressions)

Formulas are validated before processing. Invalid formulas produce clear error messages indicating the position and nature of the syntax error.

---

## Data Endpoints

### Get Aggregated Data

Retrieve aggregated data for dashboard visualization. Supports filtering by graph and dimension values.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/data/aggregated`                          |
| **Auth level** | Viewer+                                            |
| **Query params**| `dashboard_id`, `graph_id`, `filters` (optional)  |

**Request headers:**

```
Authorization: Bearer <token>
```

**Query parameters:**

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `dashboard_id` | UUID | Yes | Target dashboard |
| `graph_id` | UUID | No | Specific graph (returns all graphs if omitted) |
| `filters` | JSON string | No | Filter values (e.g., `{"year": "2024", "category": "A"}`) |

**Response** (`200 OK`):

```json
{
  "dashboard_id": "<uuid>",
  "graph_id": "<uuid>",
  "data": [
    {
      "dims": {"year": "2024", "category": "A"},
      "metrics": {"revenue": 100000, "cost": 60000}
    }
  ]
}
```

**Notes:**

- Data is filtered on the backend (SQL/Polars)
- Global filters (year, category, brand) apply to all graphs
- `dims` keys are sorted recursively before storage to ensure deterministic UPSERT conflict detection (PostgreSQL JSONB equality is sensitive to key ordering)

---

## Upload Endpoint Version History

| Version | Date       | Change Description                              |
| ------- | ---------- | ----------------------------------------------- |
| 2.0     | 2026-04-24 | Initial upload endpoint: `POST /api/v1/upload/:dashboard_id` |
| 2.1     | 2026-05-10 | Added multipart/form-data support, file validation |
| 2.2     | 2026-05-16 | Integrated with processing pipeline, task tracking |
| 2.3     | 2026-05-18 | Added `mode` query param (overwrite/append), processing_log_id in response |
| 2.4     | 2026-05-19 | **UploadModal implementation** - modal dialog instead of page navigation, inline progress feedback, react-hot-toast notifications |

---

## Processing Config Endpoints

### Get Processing Configuration

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/processing-configs/:dashboard_id`         |
| **Auth level** | Viewer+                                            |

**Response** (`200 OK`):

```json
{
  "dashboard_id": "<uuid>",
  "settings": {
    "loader": "sales_loader",
    "date_column": "event_date",
    "timezone": "UTC"
  },
  "metric_agg": "sum",
  "updated_at": "2026-05-18T12:00:00Z"
}
```

**Note:** The `metric_agg` field is exposed at the top level of the processing config response, defining the default aggregation function for metrics (`sum`, `mean`, `min`, `max`, `count`).

### Update Processing Configuration

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `PUT`                                              |
| **Path**       | `/api/v1/processing-configs/:dashboard_id`         |
| **Auth level** | Editor+                                            |

**Request body:** JSON with `settings` object.

### Delete Processing Configuration

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `DELETE`                                           |
| **Path**       | `/api/v1/processing-configs/:dashboard_id`         |
| **Auth level** | Editor+                                            |

---

## Processing Logs (Admin)

### List Processing Logs

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/admin/logs`                               |
| **Auth level** | Admin                                              |
| **Query params**| `status_filter`, `dashboard_id`, `date_from`, `date_to`, `skip`, `limit`     |

**Response** (`200 OK`): List of `ProcessingLogRead` objects, filtered and sorted by `started_at` DESC.

### Get Single Processing Log

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/admin/logs/:log_id`                       |
| **Auth level** | Admin                                              |

---

## Data Storage

Only aggregated data is stored. The structure uses a single `aggregated_data` table with JSONB columns for all dashboards:

- `dims` — dimension values (key-value pairs for filters and axes)
- `metrics` — metric values (key-value pairs for display)
- One row equals one data point for a graph
- Data is shared across users (not user-specific)

---

## Cross-References

- [Task Queue Migration](task-queue.md) — In-memory to Redis/RQ migration plan
- [Temp File Cleanup](file-cleanup.md) — Temp file cleanup architecture
- [Dashboards API](../02-dashboards/dashboards-api.md) — Dashboard, graph, and filter CRUD
- [Authentication API](../01-auth/auth-api.md) — JWT auth and role definitions
- [Database Schema](../09-database/schema-core.md) — `aggregated_data`, `processing_configs`, `processing_logs` table definitions
- [Security Overview](../08-security/) — Rate limiting, MIME-type validation, file size limits
- [Overview](../00-overview/overview.md) — System architecture and data flow
- [Data Flow](../00-overview/data-flow.md) — End-to-end upload-to-display pipeline
- [Upload UI](../07-frontend/upload-ui.md) — Frontend upload modal and file handling
