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

Upload a CSV or CSV.gz file to a specific dashboard. The file is saved to a temporary directory (`platformdirs`), read once, and then removed. File history is not retained, and a run that reaches a terminal state leaves nothing on disk to reprocess from — see [Temp File Cleanup](file-cleanup.md#the-terminal-state-rule).

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
- **Admitted MIME types**: exactly the three `MimeTypeEnum` members — `text/csv`, `application/gzip`, `application/x-gzip`. There is **no configuration key** for this set any more: `UPLOAD__ALLOWED_MIME_TYPES` was removed from `config.py` (field and property) and from `settings/app.yaml`, so `MimeTypeEnum` is the **single declaration site** of what is admitted. See [Configuration](../06-backend/configuration.md).
- **MIME type detection:** Server-side content sniffing using `python-magic` (reads the first 2 KB of file bytes; the client `Content-Type` header is not trusted). **libmagic is a hard startup dependency**: `main.check_dependencies` refuses to start the backend when `python-magic` is not importable, so there is **no heuristic fallback** and no host-dependent branch. The admitted set is therefore the **image's**, not the host's — every shipped image (dev, test, prod) installs `libmagic1`, and a host without it can no longer start the backend at all.
- **Rejection is RFC 7807**: a detected type outside the admitted set raises `AppException(ErrorCode.INVALID_FILE_TYPE)`, which answers **`415 Unsupported Media Type`** with `code = INVALID_FILE_TYPE`.
- **Behaviour change — stricter admission.** The deleted heuristic used to admit text as `text/csv`; libmagic does not. Text that the heuristic accepted is now classified by its bytes, and **semicolon-delimited** plain text is the notable casualty: it is `text/plain`, not `text/csv`, so it is now **refused**. A CSV must actually be comma-delimited to be detected as `text/csv`.
- **Character Support:** UTF-8 encoding with full Cyrillic and Latin character support. All string data is stored and rendered in Unicode without restrictions.
- **Date Format:** Input dates are parsed according to `processing_config.settings.date_format`. Standard user-facing display format is `dd/mm/yyyy`.
- Rate limiting is enforced on upload endpoints
- Maximum file size is enforced on the backend, including cumulative byte tracking during streaming writes (applies even when the client does not provide `Content-Length`). The ceiling comes from configuration (`UploadSettings.max_file_size_mb`, default 100 MB), not a literal in the loader, and it applies to the **decompressed** stream for `.csv.gz`: the gzip member is measured through `gzip.open` in bounded chunks and the read aborts the moment it passes the budget, so a small gzip of a multi-gigabyte CSV is rejected rather than fully expanded by the reader. The default value is unchanged.
- The input file is **removed on every terminal state** — see [Temp File Cleanup](file-cleanup.md#the-terminal-state-rule)

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

### What a stored artefact is called

Once the upload is accepted the file is moved to
`{UPLOAD__TEMP_DIR}/{processing_log_id}{extension}` — the processing-log id, plus an
extension **derived from the detector's verdict at admission**, never from the caller's
filename. The mapping lives on `MimeTypeEnum.extension`:

| Detected type | Stored extension |
| ------------- | ---------------- |
| `text/csv` | `.csv` |
| `application/gzip`, `application/x-gzip` | `.csv.gz` |

So a plain CSV the uploader named `*.csv.gz` is stored as `.csv`, and a real gzip the
uploader named `.csv` is stored as `.csv.gz`. **The stored name can never claim a
compression the bytes do not have.** This matters to anyone reading the directory: the
extension is evidence, not decoration.

The `.csv.gz` reader is still selected **by the path**, so the naming rule is what keeps
that selection sound. One residual is stated rather than relied upon: for a path ending
`.gz`, `data/loaders/loader.py::_validate_file_size` reads the gzip stream in pure Python
and fails a mislabelled archive **before either reader is selected**, at any size — not
only above `lazy_threshold_mb`. So the reader's ability to sniff bytes is not a guarantee
any code should depend on, and no branch relies on it.

---

## Processing Pipeline

### Pipeline Stages

The data processing pipeline is triggered by file upload. There is no manual trigger: the
`POST /upload/:dashboard_id/process` endpoint described in earlier revisions of this page
does not exist, and no re-run endpoint exists for an already-uploaded file.

```
Upload → Parse (Polars) → Transform (processing_config) → Aggregate → Save to PostgreSQL
```

### Stage Details

| Stage | Description |
| ----- | ----------- |
| **1. Upload** | File saved to temporary directory (`UPLOAD__TEMP_DIR`, defaults to `platformdirs`; see [Docker Guide](../11-guides/docker.md#application-data-directories) for mounted paths). MIME type and size validated; the stored extension is derived from the detector's verdict, not the caller's filename (see [What a stored artefact is called](#what-a-stored-artefact-is-called)). |
| **2. Parse** | File read using Polars; CSV parsing config (separator, encoding, column_types) applied from `processing_config` |
| **3. Cast and rename** | `column_types` casts applied per column, then `renames` applied. A `column_types` key naming an absent column is logged and skipped; a `date` declared without a `date_format` is not parsed, and the validator reports the uncast dtype as a warning. |
| **4. Validate** | `DataValidator.validate(df)` runs **after** the casts and the renames, so it inspects the namespace the frame actually has. `required_columns` naming a post-rename name resolves; a `column_types` check inspects the post-cast dtype. Failures fail the run with `VALIDATION_ERROR`; warnings are carried into the completion message. |
| **5. Transform** | Row `filters` applied, then base `groupby`, then `computed_fields` |
| **6. Aggregate** | `groupby` + `aggregations`, then `yoy_config`, `share_config`, `custom_metrics` |
| **7. Limit** | `sort_by` / `descending` order the frame, then `limit` truncates it — **after** aggregation |
| **8. Save** | Aggregated records written to `aggregated_data`; filter values written to `dashboard_filter_values` (idempotent overwrite) |
| **9. Cleanup** | The input file is unlinked. On success this happens **after** the transaction commits, never before — see [Temp File Cleanup](file-cleanup.md#the-terminal-state-rule) |

**Important:** Each upload triggers a **full recalculation** — both `aggregated_data`
and `dashboard_filter_values` are rebuilt from scratch. There is no incremental
aggregation. The claim is unconditional because an upload whose selection matches no
graph is a **failed run**, not a silent success: the worker raises before either
clear, names the skipped graphs in the detail, and the previous rows and filter values
survive intact.

### Aggregation Architecture

The `AggregationService` (`src/mkobi/services/aggregation_service.py`) performs per-chart Polars GROUP BY aggregation. Key characteristics:

- GROUP BY columns for each graph = `graph.dimensions` + `dashboard.filters.dimensions`, **de-duplicated in first-seen order** — a filter named like a graph dimension does not repeat the key, and graph dimensions stay ahead of filter-only names
- Dimension values are coerced for JSON serialisation by `_coerce_dim_value` (native scalars preserved, dates and datetimes to ISO, `None` to `""`); the **stored** value is canonicalised one layer down at the write boundary, in `StorageManager._canonicalize_dims`
- The aggregation function comes from `metric_agg`, read from the **top level** of the processing-config payload the producer builds. All ten `AggregationFunctionEnum` members (`sum`, `mean`, `count`, `min`, `max`, `median`, `std`, `var`, `first`, `last`) are reachable and each produces its own value through `AGG_FUNC_MAP`. An unrecognised function name is **rejected** with `VALIDATION_ERROR` rather than silently stored as a sum
- Filter values are extracted after aggregation via `extract_filter_values()` which scans all aggregated records for distinct values per filter name, and are written as text at the storage boundary

### Transformation Semantics

These are the settings keys the worker actually reads, and what each one does.

| Setting | Behaviour |
| ------- | --------- |
| `filters` | Row-level `where` conditions, applied first |
| `groupby` **without** `aggregations` | **Deterministic de-duplication.** Each group collapses to one representative row: the frame is sorted by every remaining (non-group) column in the frame's own column order with `nulls_last=True`, then the first row of each group is taken. The representative is therefore the lexicographic minimum across the non-group columns — reproducible, and independent of input row order |
| `groupby` **with** `aggregations` | Base aggregation; the group key is not de-duplicated |
| `aggregations` | Per-column functions from `AGG_FUNC_MAP`, aliased `{column}_{function}` |
| `yoy_config` | **Supported.** Growth is always computed against the **same entity's** previous period. When `group_cols` is supplied the entity is the group; when it is absent the entity is every column that is neither the year, the value nor the month — discovered from the frame itself, so the group-less case is per-entity rather than against the globally preceding row. `month_column` shifts within the month and the entity columns |
| `share_config` | **Supported.** `value / group total * 100` when `group_cols` is supplied, otherwise against the frame-wide total; a zero total yields `0.0` |
| `custom_metrics` | **Supported.** Formula expressions evaluated by `_add_computed_fields` on the aggregated frame |
| `sort_by` + `descending` | Orders the aggregated frame, so the sort and the limit describe one operation ("top N by this metric"). A configured sort key is commonly an aggregate column that does not exist until aggregation has run |
| `limit` | Applied **after** aggregation, not before. A bare `limit` therefore keeps N groups of a fully aggregated frame instead of aggregating a truncated one. The truncation is **global across the frame** — `limit` is a frame-level setting, not per-graph — and a bare limit without `sort_by` keeps N groups but does not define which |

### Validation Warnings

Validation warnings are no longer discarded. They are summarised into the
`processing_logs.message` of a completed run, appended after the `" | Warnings: "`
separator to the completion sentence and capped at the column's declared length of
**1000** characters:

- The **completion sentence is written first and is never truncated** while it fits on its own — it is the text a client renders.
- The warning summary is the only part shortened. On overflow it is cut to the remaining budget and `...[truncated]` is appended, so a shortened summary is distinguishable from a short one.
- If the completion sentence plus the separator already fills the cap, the summary is **dropped whole** rather than displacing or mangling the sentence.

A declared `float` column is now actually cast to `Float64`, so its type warning stops
firing on every run.

### Failure Classification

Failures are classified by their **error code first**. An exception carrying a usable
`ErrorCode` — an `AppException` above all, including the `VALIDATION_ERROR` raised by
config validation — is reported as that code and is never overwritten by a message
substring. Message matching exists only as a **documented fallback for code-less
driver and library exceptions** (a `SQLAlchemyError`, a Polars exception, a bare
`ValueError`), and a rebuild that contended for the dashboard's exclusion and timed
out is reported as in-progress rather than failed.

| Code | Raised when |
| ---- | ----------- |
| `VALIDATION_ERROR` | `DataValidator` rejected the frame, the processing config is malformed, or an unsupported aggregation function was requested |
| `FILE_UPLOAD_ERROR` | The input file was not found |
| `FILE_PROCESSING_ERROR` | In the worker: an encoding fault, or a CSV read/parse fault. On the **upload** path, separately: the job could not be submitted to RQ |
| `FILE_TOO_LARGE` | The file — the **decompressed** stream for `.csv.gz` — exceeds the configured ceiling |
| `INVALID_FILE_TYPE` | The detected MIME type is not one of `MimeTypeEnum`'s members. On the **upload** path this is an admission refusal (`415`); in the **worker** it is a malformed archive or a path ending `.gz` over non-gzip bytes, refused by the loader's reader boundary |
| `PROCESSING_IN_PROGRESS` | Another rebuild holds this dashboard's exclusion and the wait timed out |
| `PROCESSING_FAILED` | Anything else, including a selection that produced no aggregates for one or more graphs |

The empty-selection detail names up to twenty skipped graphs and then says how many
remain, so the message stays inside the same 1000-character column.

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

A `completed` or `failed` row is also the **end of the file's life**: the input was
removed before the transition was written, so a terminal status and an absent artefact
are the same fact. A run that was **hard-killed** mid-job is the exception — it reaches
no terminal state and no removal, so its file survives until the age-based sweep. See
[Temp File Cleanup](file-cleanup.md#the-terminal-state-rule).

### Task Queue

Background work is submitted to a **Redis-backed RQ queue** and executed by the
`rq-worker` container. `src/mkobi/core/task_queue.py` is the single submission seam
(`enqueue_job`, `get_rq_queue`); the application process holds no queue of its own. The
in-process `asyncio.Queue` implementation was removed in 2026-09-30 and a test asserts
its symbols stay absent. See [Task Queue](task-queue.md) for the historical record and
[Task Queue Migration](../11-guides/task-queue-migration.md) for the migration record.

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

#### `filename` is display-only

`ProcessingStatusResponse.filename` is **display text, not a locator**. Its value is
filled from the processing log's `message` column (falling back to the literal `"unknown"`)
— the *message*, not a stored file name.

- There is **no durable filename anywhere**. `processing_logs` stores no name and no path
  column, and none is being added, because the artefact is scratch space that is removed
  on every terminal state.
- **No code may use this field to open, locate or re-process a file.** It names nothing on
  disk.
- The field's **name and `str` type are unchanged** and it is never `null`, so clients
  that have always received a string here receive a string. That is the whole of its
  contract: wire compatibility.

Two helpers that would have made this field actionable were **deleted** —
`find_task_file` and `DataService.trigger_processing` (with the
`IDataService.trigger_processing` protocol declaration). See
[Temp File Cleanup](file-cleanup.md#the-csv-glob-is-an-age-sweep-not-a-selector).

### Get Processing Result

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/upload/result/:task_id`                   |
| **Auth level** | Editor+                                            |

**Response** (`200 OK`):

```json
{
  "success": true,
  "task_id": "<uuid>",
  "dashboard_id": "<uuid>",
  "rows_processed": 15000,
  "message": "Processing completed successfully"
}
```

The success flag is a **boolean on the result**, not a `ProcessingStatus` value. While
the run is not `COMPLETED` the endpoint answers `200` with `success: false`, `rows_processed: 0`,
and a message naming the current status. `ProcessingStatus` itself never takes the
value `success`.

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
| `graph_id` | UUID | No | Specific graph (returns all graphs if omitted). The graph must belong to `dashboard_id`: a `graph_id` for another dashboard's graph is reported as `404 GRAPH_NOT_FOUND`, so access to one dashboard cannot read another's graph. |
| `filters` | JSON string | No | Filter values. A **scalar** value is one `->>` equality; a **list** of strings is a membership union over the listed values, and an **empty list** imposes no constraint. Bounded: at most 20 keys, 64-character key names, 256-character values **per element**, 4 KB serialised (`PRF-5`; see [Filter payload bounds](../02-dashboards/dashboards-api.md#filter-payload-bounds-prf-5)). See [Filter values and admissibility](#filter-values-and-admissibility) below. |

**Response** (`200 OK`):

The response is an `AggregatedDataResponse`: a **list of graphs**, each carrying its own
rows, its served column names, its layout and its row counts, plus two
dashboard-level counts.

```json
{
  "graphs": [
    {
      "graph_id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "bar",
      "name": "Sales by Category",
      "data": [
        {"year": "2024", "category": "A", "revenue_sum": 100000, "cost_sum": 60000}
      ],
      "metrics": ["revenue_sum", "cost_sum"],
      "dimensions": ["year", "category"],
      "returned_rows": 1,
      "total_rows": 5000,
      "rows_truncated": true,
      "layout": {"title": "Sales by Category"},
      "config": {"x": "category", "metrics": ["revenue"], "orientation": "v"}
    }
  ],
  "total_rows": 5000,
  "truncated": true
}
```

**`data` rows are flat and merged.** A row is one dict holding the record's dimension
keys and its metric keys **in the same object** — there is no nested `dims` /
`metrics` pair on the wire. When a dimension and a measure share a name the metric
value wins, because the merge is `{**dims, **metrics}`.

**Notes:**

- Data is filtered on the backend (SQL/Polars)
- Global filters (year, category, brand) apply to all graphs
- Rows are returned in a deterministic order: ascending row id. Under `overwrite` this reproduces the computed chart order, because the dashboard's rows are deleted before the rebuild re-inserts them.
- **Append-mode limitation.** Ascending id is *wrong* for `append`: an upsert updates an existing `(dashboard_id, graph_id, dims)` row in place and keeps its original id, while new rows take fresh, larger ids. A re-ranked existing row keeps a stale position and new rows sort after all existing ones, so the read order diverges from the freshly computed chart order. Closing that needs a dedicated `aggregated_data.ordinal` column populated from the chart order — schema DDL that another phase owns. This limitation is recorded here and in the repository module, not fixed here.
- `dims` values are stored canonically stringified, so one category is one row. `dims` keys are sorted recursively before writes, but that is cosmetic: JSONB canonicalises object key order itself, so the sorting is not what makes the UPSERT work.

---

### Served measure and dimension names

Each graph entry carries two name lists. They are the single source of truth for
"which columns can this chart read", and they are **correct by construction**:

| Field | Meaning |
| ----- | ------- |
| `metrics` | The **post-alias measure keys actually present on the rows in `data`**, in first-seen order over the whole bounded page. |
| `dimensions` | The **post-alias dimension keys actually present on the rows in `data`**, same order. |

Both are read directly off the stored aggregate row's `metrics` / `dims` columns —
the same two columns the rows were merged from — so every name they list is a key
on a served row. Nothing is derived from the graph's `config`, and no `_{metric_agg}`
suffix rule is applied or implied.

> **The distinction that is easy to get backwards.**
> A top-level `metrics` on this
> response is the **served, post-alias** key set. `config["metrics"]` on the *same
> object* is the operator's **pre-alias input**. They routinely differ: an operator
> who writes `"metrics": ["revenue"]` under a `mean` aggregation receives rows keyed
> `revenue_mean`, so the response says `metrics: ["revenue_mean"]` while `config`
> still says `["revenue"]`. **A client reads the served names and applies no suffix
> rule to them.**

> **The number of stored graphs whose `config` names a column the served rows no longer
> carry is UNKNOWN.** Measuring it needs a query nobody is authorised to run, so no
> magnitude is stated here — not an estimate, and not zero. Nothing about the contract
> depends on it: the served names are correct by construction for every graph, affected
> or not.

Both fields are **optional with an empty default**, so neither appears in the
OpenAPI `required` list. A graph with no served rows serves `[]` for both — and such
a graph **still appears** in the response, carrying its counts and an empty `data`
list. It is not omitted.

### How a client resolves the measure, axis and colour columns

The resolution rule is one rule, applied to a configured name against the served
names (`chartStates.ts::resolveColumnName`):

- a configured name that **is** among the served names wins;
- an **absent or empty** served list is no authority at all, so the configured name stands;
- otherwise the configured name is **unresolved**.

| Role | Resolution | If unresolved |
| ---- | ---------- | -------------- |
| Measure (`y`) | `config.metrics[0]` if served, else the **first served metric** | Nothing resolves, which only happens when the served `metrics` list is absent or empty; the writer skips any group with no measure, so a non-empty row set carries at least one |
| Axis (`x`) | `config.x` if served, else the **first served dimension** | Falls back to the literal column name `x`, which no row carries |
| Colour (`color`) | `config.color` if it is among the served **dimension** names | **No grouping.** The chart draws one ungrouped trace — never a guessed dimension |

The measure resolution is shared with the render-state predicate, so the trace and
the state classification can never disagree about which column is the measure.

### Layout

`layout` is the graph's stored `config["layout"]`, served **as stored** and validated
as `ChartLayoutConfig`. It is `null` when the graph stored no layout.

It is **not** a merge of `config["title"]`, `config["showlegend"]`, `config["xaxis"]`
or `config["yaxis"]`. Those config-level twins are separate declared keys, and the
two axis twins are deliberately unwired — see
[Extend Graphs](../11-guides/extend-graphs.md#the-config-vocabulary). A bar chart's
axis type is `'category'` unless a stored layout supplies one.

`AxisConfig.label` is a reserved key inside the layout: the client's converter reads
`title`, `type` and `range` only, so a stored `label` survives the wire and is
dropped at render time.

---

### Filter values and admissibility

Two independent rules apply to a submitted `filters` payload, and they are decided
in two different layers.

**Shape** — enforced by `AggregatedFiltersRequest` in `src/mkobi/models/data.py`. A
value is a scalar (`str`, `int`, `float`, `bool`) or a `list[str]`. The bounds
(20 keys, 64-character key names, 256 characters **per element**, 4 KB serialised)
apply to lists element-wise, so a multi-element list is not refused by the scalar
branch's length check; the payload-size bound still caps the total.

**Admissibility** — enforced by `DataService.validate_filter_values`, from the
dashboard's stored `config["filters"]`. Per submitted key:

| Declared type of the key | Submitted value | Outcome |
| ------------------------ | --------------- | ------- |
| absent, or the dashboard declares no filters | anything | Permitted |
| not declared among the stored filters' `field` values | anything | Permitted |
| `range` | anything, scalar or list | **Refused by name** |
| not `multiselect` | a `list` | **Refused by name** |
| `multiselect` | a `list` | Permitted — matched as a membership union |
| `select`, `date`, `multiselect` | a scalar | Permitted — matched as `->>` equality |

A refusal is an RFC 7807 **`422`** with `code = VALIDATION_ERROR`, a `detail` naming
the filter and its reason, and `details` carrying `{filter, declared_type, reason}`.

**Semantics of a list value.** A `list[str]` means *membership*: the returned rows
are the union over the listed values, compiled as one `->> … IN (…)` predicate over
the **same** `->>` operator a scalar uses, so a `select` and a `multiselect` over one
dimension can never disagree. An **empty list imposes no constraint** and returns
everything; it is deliberately not `IN ()`, which would blank every chart with no
visible cause.

### Bound: the retired `range` type is not fully closed

The `range` filter type is **retired**. It has no control in the filters panel, and a
stored `range` filter is refused by name on both a dashboard save and this read. The
`FilterType.RANGE` enum member and the `filter_type` PostgreSQL label both still
exist and are inert; their removal is deferred to phase 14 (`C14-17`). See
[Database Enums](../09-database/enums.md#4-filtertype).

What is **not** closed is the value union, and this is a bound rather than a closed
hole:

- A filter value of two strings — for example `["0", "100"]` — is
  **indistinguishable on the wire** from a legitimate two-value multiselect.
- A dashboard that declares **no** filters at all, and receives such a value, is
  **permitted** and matched as a membership test. An undeclared filter carries no
  type to discriminate with.
- That path is **unreachable from any input the application itself produces** (the
  range slider is gone, so nothing in the product emits a `number[]`), and it is
  **not covered for a non-browser client**.

No value union can discriminate the two forms, because the wire shape is identical.
This is stated as a bound; it is not a claim that the hole is closed.

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

**Note:** The `metric_agg` field is exposed at the top level of the processing config response, defining the default aggregation function for metrics. It accepts any of the ten `AggregationFunctionEnum` values (`sum`, `mean`, `count`, `min`, `max`, `median`, `std`, `var`, `first`, `last`); anything else is rejected.

### Update Processing Configuration

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `PUT`                                              |
| **Path**       | `/api/v1/processing-configs/:dashboard_id`         |
| **Auth level** | Editor+                                            |

**Request body:** JSON with a `settings` object and an optional top-level `metric_agg`.

**Declared settings keys.** `ProcessingConfigBase.settings` is `ProcessingSettingsModel`,
configured `extra="forbid"`. It declares **twenty-two** keys: the nineteen the pipeline
reads, plus three kept only for stored payloads.

| Read by | Keys |
| ------- | ---- |
| The worker, directly | `separator`, `encoding`, `column_types`, `required_columns`, `decimal_separator`, `date_format`, `renames`, `computed_fields`, `metric_agg` |
| Reached through `ProcessingConfig` | `filters`, `groupby`, `aggregations`, `sort_by`, `descending`, `limit`, `yoy_config`, `share_config`, `custom_metrics`, `metrics` |
| Declared, read by nothing in `src/` | `loader`, `date_column`, `timezone` — kept because the development seeder writes them and stored payloads may carry them |

**An unknown key is a `422`.** A `settings` object containing a key the model does not
declare is rejected at the request boundary with `code = VALIDATION_ERROR`. The RFC 7807
`detail` is the generic `"Request validation failed"`; the unknown key is named in
`errors[].loc`, not in `detail`. This is a **request-body contract, not a new response**:
the route already declared its `422` before the boundary tightened, so no status code
was added and no OpenAPI response entry is new. Previously an unknown key was silently
dropped, so a misspelled setting had no effect and no diagnostic.

> **Note:** No default is given to `timezone`, `encoding` or `separator`. A default the
> stored column never had would make a read model assert something the database does not say.

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
| **Path**       | `/api/v1/admin/logs/`                              |
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

- `dims` — dimension values (key-value pairs for filters and axes), canonicalised to strings at the write boundary
- `metrics` — metric values (key-value pairs for display); **not** canonicalised, because the numbers are the data
- One row equals one data point for a graph
- Data is shared across users (not user-specific)

---

## Cross-References

- [Task Queue](task-queue.md) — Historical record of the in-process queue and its removal
- [Task Queue Migration](../11-guides/task-queue-migration.md) — The RQ migration decision record and operational documentation
- [Temp File Cleanup](file-cleanup.md) — Temp file cleanup architecture and the age-based reconciler sweeps
- [Dashboards API](../02-dashboards/dashboards-api.md) — Dashboard, graph, and filter CRUD
- [Authentication API](../01-auth/auth-api.md) — JWT auth and role definitions
- [Database Schema](../09-database/schema-core.md) — `aggregated_data`, `processing_configs`, `processing_logs` table definitions
- [Security Overview](../08-security/security-overview.md) — Rate limiting, MIME-type validation, file size limits
- [Overview](../00-overview/overview.md) — System architecture and data flow
- [Data Flow](../00-overview/data-flow.md) — End-to-end upload-to-display pipeline
- [Upload UI](../07-frontend/upload-ui.md) — Frontend upload modal and file handling
