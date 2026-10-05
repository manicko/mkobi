---
id: create-dashboard
domain: guides
tags:
  - guide
  - admin
  - dashboard-creation
  - workflow
  - howto
related:
  - dashboards-api
  - processing-api
  - schema-core
  - data-flow
  - docker
  - extend-graphs
  - extend-filters
---

## Purpose

This guide walks administrators through the end-to-end process of creating a new dashboard in the mkobi BI Dashboard System — from pre-creation planning through configuration, first upload, access management, and ongoing operations. It assumes familiarity with the application UI and focuses on workflow rather than detailed API field specifications, which are covered in the [Dashboards API](../02-dashboards/dashboards-api.md) reference.

## Prerequisites

You must have the Admin role to create dashboards. Additionally, you should:

- Have identified the data source (CSV or CSV.gz file) that will populate the dashboard
- Understand the column structure of your data (dimensions and metrics)
- Know which graph types best represent your data for analysis

## Pre-Creation Planning

Before creating a dashboard, plan the following:

- **Data source:** Identify the CSV/CSV.gz file that will provide the data. Each dashboard expects data with specific column structures.
- **Columns:** Determine which columns represent dimensions (categorical data used for grouping and filtering) versus metrics (numerical values to aggregate).
- **Graph types:** Decide which graphs to create — bar, line, pie, or table — based on how you want to visualize each data relationship.
- **Processing config:** Prepare the processing configuration that defines how CSV columns are parsed (separator, encoding, column types, date format, etc.). See [Processing API](../03-processing/processing-api.md) for details on settings structure.
- **Filters:** Plan which dimensions users should be able to filter by. Filters can have static options (`source: "dims"`) or dynamic values extracted from data (`source: "data"`).

## Create the Dashboard

Navigate to the Admin page and use the dashboard creation form. The endpoint is `POST /api/v1/dashboards/`.

**Request body:**

```json
{
  "name": "Sales Dashboard",
  "description": "Quarterly sales metrics",
  "config": {
    "graph_types": ["bar", "line"]
  }
}
```

**Fields:**

| Field | Required | Description |
| ---- | -------- | ----------- |
| `name` | Yes | Unique name (3–100 chars, alphanumeric + spaces + hyphens) |
| `description` | No | Brief description (max 200 chars) |
| `config` | No | Dashboard configuration object (defaults to `{"graph_types": ["bar"]}`) |
| `layout_id` | Optional | UUID of an existing layout template |

The `config` field is a `DashboardConfig` object with the following structure:

| Field | Type | Description |
| ---- | ---- | ----------- |
| `graph_types` | `GraphType[]` | List of allowed graph types (at least one required). Controls which graph types can be created for this dashboard. |
| `filters` | `object[]` | Optional filter configuration presets |
| `aggregations` | `object[]` | Optional aggregation presets |
| `charts` | `object[]` | Optional chart presets |
| `title` | `string` | Optional display title |
| `description` | `string` | Optional display description |

**What happens on creation:**

1. The dashboard is created in the `dashboards` table
2. The creating user is automatically granted `admin` permission on the dashboard via the `dashboard_access` table
3. The response includes the full dashboard object with `permission: "admin"`

See [Dashboards API](../02-dashboards/dashboards-api.md) for field-level details.

## Configure the Layout

Layouts define the UI composition of a dashboard through a grid system. Each layout organizes graphs in rows and columns. Layouts are reusable — multiple dashboards can reference the same layout.

Key concepts:

- **Grid:** A responsive grid system where graphs are positioned
- **Graph slots:** Each slot in the layout corresponds to a graph
- **Layouts are optional:** A dashboard can be created without a layout (`layout_id` is nullable)

To attach a layout to a dashboard, include `layout_id` in the create request or update the dashboard later via `PUT /api/v1/dashboards/{id}`. Layouts are managed separately via `POST/GET/PUT/DELETE /api/v1/layouts`. See [Dashboards API](../02-dashboards/dashboards-api.md#layout-endpoints) for layout CRUD operations.

## Add Graphs

Graphs are the visualizations within a dashboard. Each graph belongs to exactly one dashboard.

**Graph types available:**

| Type | Description |
| ---- | ----------- |
| `bar` | Vertical or horizontal bar charts for comparing values across categories |
| `line` | Line charts for trend analysis over time or continuous data |
| `pie` | Pie or donut charts for showing proportions of a whole |
| `table` | Tabular display of aggregated data |

**Creating a graph:**

Use the dashboard-scoped endpoint `POST /api/v1/dashboards/{dashboard_id}/graphs`:

```json
{
  "name": "Revenue by Category",
  "type": "bar",
  "dimensions": ["category"],
  "metrics": ["revenue"],
  "config": {
    "x": "category",
    "metrics": ["revenue"],
    "orientation": "v"
  }
}
```

**Fields:**

| Field | Required | Description |
| ---- | -------- | ----------- |
| `name` | Yes | Graph name |
| `type` | Yes | Graph type (`bar`, `line`, `pie`, `table`) |
| `dimensions` | Yes | List of dimension column names for GROUP BY |
| `metrics` | Yes | List of metric column names to aggregate |
| `config` | Yes | Chart configuration |

**Dimensions vs. Metrics:**

- **Dimensions** are categorical fields used for grouping and X-axis values (e.g., `month`, `category`, `region`)
- **Metrics** are numerical fields that are aggregated (summed by default) for display on the Y-axis (e.g., `revenue`, `cost`, `profit`)

The aggregation pipeline groups by `graph.dimensions + dashboard.filter.names` and sums all metric columns. See [Dashboards API](../02-dashboards/dashboards-api.md#graph-endpoints) for complete details.

**`config` is a closed vocabulary.** It accepts exactly fifteen declared keys, and an
undeclared key is **refused by name** with a `422`. Several declared keys are
**reserved** — accepted, stored, returned, and read by nothing — so a key being accepted
does not mean it changes the chart. Six of them are reserved, plus the config-level axis
twins, which are deliberately unwired. The full classification is in
[Extend Graphs → The config vocabulary](./extend-graphs.md#the-config-vocabulary).

**`config.metrics` names the pre-alias column; the response reports the served name.**
The aggregation aliases every aggregate as `{column}_{function}`, so an operator who
writes `"revenue"` under a `mean` aggregation receives rows keyed `revenue_mean`. The
response's top-level `metrics` / `dimensions` are read off the rows and are therefore
correct by construction; a client reads those and applies no suffix rule. See
[Processing API → Served measure and dimension names](../03-processing/processing-api.md#served-measure-and-dimension-names).

**No graph-editing UI exists.** Every graph reference in the frontend is a read, so
graphs are created through the API above rather than through a form.

## Add/Bind Filters

Filters allow users to interactively narrow down the data displayed in graphs.

**Filter types available:**

| Type | Description | UI Control | Value shape sent |
| ---- | ----------- | ---------- | ---------------- |
| `select` | Single value selection from a dropdown | Dropdown | Scalar |
| `multiselect` | Multiple values selection | Multi-select with chips | **`list[str]`** — a membership union; an empty list constrains nothing |
| `date` | Date selection | Date picker | Scalar |

There is **no** `range` type. The `range` filter type is **retired**: it has no control
in the panel, a stored `range` filter is refused **by name** with a `422` on a dashboard
save, and the aggregate read refuses it too. A dashboard that already stores one renders
a **non-blocking warning inside the filters panel** and sends no value — the dashboard is
**not** blanked, and it is **not** an empty state. The `FilterType.RANGE` enum member and
the `filter_type` PostgreSQL label still exist and are inert; their removal is deferred to
phase 14 (`C14-17`). See [Database Enums](../09-database/enums.md#4-filtertype) and
[Processing API → Filter values and admissibility](../03-processing/processing-api.md#filter-values-and-admissibility).

**Filter value source:**

Filters can receive their option values from two sources, controlled by `config.source`:

| Source | Description |
| ------ | ----------- |
| `"dims"` (default) | Static options defined in `config.options` array |
| `"data"` | Dynamic values extracted from aggregated data during CSV processing, stored in `dashboard_filter_values` table |

When `source === "data"`, the frontend fetches values from `GET /api/v1/dashboards/{dashboard_id}/filter-values?filter_name={name}`. Values are automatically rebuilt on each upload. That option list is cached for the process lifetime and invalidated explicitly when an upload completes, so it never describes the previous file; every other query keeps its normal refetch behaviour.

**Creating and binding filters:**

Filter records are seeded directly into the `filters` table (the development
seeder upserts them); there is **no global-filter creation HTTP endpoint** —
the `/api/v1/filters` CRUD routes were removed as orphaned and
`src/mkobi/api/routes/filters.py` is now a placeholder that holds no route.

1. A filter row has this shape:

```json
{
  "name": "category",
  "type": "multiselect",
  "config": {
    "field": "category",
    "source": "data",
    "multi": true
  }
}
```

2. Bind the filter to your dashboard via `POST /api/v1/dashboards/{dashboard_id}/filters?filter_id={filter_id}`

3. List bound filters via `GET /api/v1/dashboards/{dashboard_id}/filters`

4. Unbind via `DELETE /api/v1/dashboards/{dashboard_id}/filters/{filter_id}`

Once bound, filters appear in the dashboard's filter panel and apply to all graphs. See [Dashboards API](../02-dashboards/dashboards-api.md#filter-endpoints) for the complete API specification.

## Set Up Processing Config

The processing config defines how CSV data is parsed and transformed before aggregation. It is stored in the `processing_configs` table with a `settings` JSONB object.

**Key settings:**

| Setting | Type | Default | Description |
| ------- | ---- | ------- | ----------- |
| `loader` | `string` | — | Identifier for the processing profile (e.g., `"sales_loader"`) |
| `date_column` | `string` | — | Name of the column containing dates for YoY calculations |
| `timezone` | `string` | `"UTC"` | Timezone for date operations |
| `encoding` | `string` | `"UTF-8"` | Character encoding |
| `separator` | `string` | `","` | CSV delimiter character |
| `decimal_separator` | `string` | — | Decimal separator (e.g., `","` for EU format) |
| `column_types` | `object` | — | Column type casting map (e.g., `{"age": "int", "price": "float"}`) |
| `date_format` | `string` | — | Date format string for parsing date columns |
| `renames` | `object` | — | Column renaming map |
| `computed_fields` | `object[]` | — | Computed column expressions |
| `filters` | `object[]` | — | Row-level filters applied during processing |
| `groupby` | `string[]` | — | GROUP BY columns for pre-aggregation |
| `aggregations` | `object[]` | — | Aggregation config (sum, avg, count, etc.) |
| `yoy_config` | `object` | — | Year-over-year comparison config |
| `share_config` | `object` | — | Share calculation config |
| `custom_metrics` | `object[]` | — | Custom metric formulas |

`metric_agg` is a **top-level** field of the processing-config request and response, not
a key inside `settings`. It selects the default aggregation function and accepts any of
the ten `AggregationFunctionEnum` values; an unrecognised name is rejected rather than
stored as a sum.

**An unknown `settings` key is a `422`.** The settings model forbids extras, so a
misspelled setting is named in the error rather than silently dropped.

**Important:** The upload pipeline automatically fetches the dashboard's processing config and passes it to the background worker. No manual wiring is needed.

**Character Support:** All text fields support both Cyrillic and Latin characters through UTF-8 encoding. Russian and English content can be displayed side-by-side in dashboard data, chart labels, and filter values.

**Date Format:** The standard date format for user-facing displays is `dd/mm/yyyy` (e.g., `31/12/2024`). The `date_format` setting in processing config defines how input dates are parsed from CSV files (e.g., `%d.%m.%Y`, `%Y-%m-%d`).

Set up the processing config via `PUT /api/v1/processing-configs/{dashboard_id}`. See [Processing API](../03-processing/processing-api.md) for annotated examples.

## Upload Data

After setting up graphs, filters, and processing config, upload your CSV data to populate the dashboard.

**Endpoint:** `POST /api/v1/upload/{dashboard_id}`

| Attribute | Value |
| --------- | ----- |
| **Method** | `POST` |
| **Path** | `/api/v1/upload/{dashboard_id}` |
| **Auth level** | Editor+ |
| **Query param** | `mode` — `overwrite` (default) or `append` |
| **Body** | `multipart/form-data` with file field |

**File constraints:**

- Allowed extensions: `.csv`, `.csv.gz`
- Allowed MIME types: `text/csv`, `application/gzip`, `application/x-gzip`
- MIME type detection uses server-side content sniffing (`python-magic`), not the client header
- Maximum file size enforced on the backend (including during streaming writes), measured on the **decompressed** stream for `.csv.gz`
- Rate limiting enforced on the upload endpoint

**Upload modes:**

- **overwrite** — Clears all existing aggregated data for the dashboard, then stores new aggregates
- **append** — Keeps existing aggregated data and adds new records

**Processing pipeline:**

When a file is uploaded, the following happens automatically:

1. File is streamed to temporary storage (8KB chunks)
2. File is validated (MIME type, extension, size)
3. A processing log entry is created with status `started`
4. Status is updated to `uploaded`
5. File is moved to final location
6. Background job is enqueued
7. The background worker (`data_worker.py`):
   - Parses CSV using Polars with processing config settings (separator, encoding, column_types)
   - Applies transformations (decimal separator, column renames, computed fields)
   - Applies processing config (filters, aggregations, YoY, custom metrics)
   - For each graph, performs GROUP BY on `graph.dimensions + dashboard.filter.names`
   - Stores results in `aggregated_data` table
   - Extracts distinct filter values and stores in `dashboard_filter_values` table
   - Deletes the temporary file
   - Updates processing log to `completed` or `failed`

**Task lifecycle:**

```
started → uploaded → processing → completed/failed
```

Check processing status via `GET /api/v1/upload/status/{task_id}`. There is **no**
`success` status; a successful run reports `completed`. See [Processing API](../03-processing/processing-api.md) for complete endpoint details.

## Verify Results

After upload completes, verify the results:

**Check processing status:**

Use `GET /api/v1/upload/status/{task_id}`. A successful status returns `"completed"` with a `rows_processed` count.

**View uploaded data:**

Open the dashboard view to see graphs rendered with your data. If graphs show data, the upload and processing completed successfully.

**Test filters:**

Select values in the filter panel to verify that:
- Filter options populate correctly (especially for `source: "data"` filters)
- Graph data updates appropriately based on selections
- Multiple filters work together as expected

**Read the render states.** A chart that shows data is not the only success signal. The
dashboard distinguishes four states plus one more after a failed refetch — no charts, a
chart with no rows, a chart whose measure is **absent** from the served data (drawn as a
gap, with a per-chart note naming the column), a chart rendered normally, and retained
data marked out of date. A present **zero is never** the absent state. See
[UI Pages → Dashboard View Page](../07-frontend/pages.md#4-dashboard-view-page-dashboardid).

See [Data Flow](../00-overview/data-flow.md) for the complete end-to-end pipeline.

## Grant Dashboard Access

Share your dashboard with other users by granting access permissions.

**Endpoint:** `/api/v1/dashboards/{dashboard_id}/access`

| Action | Method | Auth level |
| ------ | ------ | ---------- |
| Grant access | `POST` | Owner or administrator |
| List access | `GET` | Owner or administrator |
| Revoke access | `DELETE` | Owner or administrator |

**Permission levels:**

| Level | Description |
| ----- | ----------- |
| `view` | Read-only access to dashboard and its data |
| `edit` | Can upload data and trigger processing |
| `admin` | Full control including dashboard management and access grants |

**Grant access request body:**

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "dashboard_id": "660e8400-e29b-41d4-a716-446655440001",
  "permission": "view"
}
```

Note: The `dashboard_id` in the request body must match the URL path parameter.

**Re-granting is a write.** Granting over an existing `(user_id, dashboard_id)` pair
applies the requested permission and updates the stored row — it is not a no-op, and the
response echoes the requested permission because that is what the boundary admitted.

**Revoke access:** `DELETE /api/v1/dashboards/{dashboard_id}/access/{user_id}`

See [Dashboards API](../02-dashboards/dashboards-api.md#dashboard-access-management) for API details and [Access Schema](../09-database/schema-access.md) for the table structure.

## Ongoing Operations

Dashboard management continues after initial setup. Common ongoing tasks include:

**Re-uploading data:**

Upload new data files at any time. Each upload triggers a full recalculation of aggregates. Use `overwrite` mode to replace existing data or `append` mode to add to it. The `dashboard_filter_values` table is also rebuilt on each upload, and the client's cached option lists are invalidated with it.

**Modifying processing config:**

Update the processing configuration via `PUT /api/v1/processing-configs/{dashboard_id}` when your CSV format changes. Changes take effect on the next upload.

**Managing filters:**

- Bind/unbind filters via `POST/DELETE /api/v1/dashboards/{id}/filters`
- Re-upload data to update dynamic filter values (when `source: "data"`)
- Filter **rows** have no update endpoint — the `/api/v1/filters` CRUD routes were removed as orphaned. Change a filter's `type` through the dashboard's `config.filters` on a dashboard save, or rewrite the row directly

**Re-granting access:**

Access permissions are persistent. Users retain their permission level until revoked. You can change a user's permission level by granting a new level (the system upserts the record).

## Troubleshooting

Common issues and their resolutions:

**Upload rejected:**

- Verify file extension is `.csv` or `.csv.gz`
- Check that the file content matches allowed MIME types (server-side detection)
- Ensure file size is within backend limits
- Confirm you have Editor+ role on the dashboard

**Processing stuck in `processing` state:**

- Check processing logs via Admin → Processing Logs
- Verify the CSV structure matches the processing config
- Ensure all required columns are present in the data
- Check for malformed data rows that might cause parsing failures
- Note: a periodic cleanup task marks entries stuck in `processing` for more than 30 minutes as `failed`

**No data after upload:**

- Verify graphs have correct `dimensions` and `metrics` configured
- Check that processing completed with `"completed"` status
- Ensure at least one graph exists on the dashboard
- Review processing config settings (separator, encoding, column_types) for mismatches

**Filter not working:**

- Verify filter is bound to the dashboard
- Check `config.field` matches a dimension name in your data
- For `source: "data"` filters, re-upload to populate filter values
- Ensure filter values exist in the aggregated data
- Check the panel for a warning alert — a declared type with no evaluable control sends no value, and the request may be refused with a `422`

**Chart shows a gap instead of a value:**

- The measure column resolved for that chart is not among the served metric names
- Compare `config.metrics[0]` with the response's top-level `metrics`; the served names are post-alias, the configured one is pre-alias
- A re-upload under a different `metric_agg` changes the alias

**Access grant not working:**

- Confirm you have the Admin role
- Verify the target user exists in the system
- Check that `dashboard_id` in request body matches the URL parameter

## Appendix

**Simple processing config example:**

```json
{
  "settings": {
    "loader": "basic_loader",
    "encoding": "utf-8",
    "separator": ","
  }
}
```

A minimal configuration for standard CSV files with comma separator and UTF-8 encoding.

**Medium processing config example (with date parsing):**

```json
{
  "settings": {
    "loader": "sales_loader",
    "date_column": "sale_date",
    "date_format": "%Y-%m-%d",
    "timezone": "Europe/Moscow",
    "encoding": "utf-8",
    "separator": ","
  }
}
```

Includes date column specification for YoY calculations and timezone for date operations.

**Complex processing config example (custom separators, type casting, computed fields):**

```json
{
  "settings": {
    "loader": "financial_loader",
    "date_column": "period",
    "date_format": "%d.%m.%Y",
    "timezone": "UTC",
    "separator": ";",
    "encoding": "utf-8",
    "decimal_separator": ",",
    "column_types": {
      "region": "str",
      "revenue": "float",
      "units": "int"
    },
    "renames": {
      "old_name": "new_name"
    },
    "computed_fields": [
      {
        "name": "profit_margin",
        "expression": "(revenue - cost) / revenue * 100"
      }
    ]
  }
}
```

Uses semicolon separator (common in European CSV files), explicit column type casting, column renaming, and computed fields.

Every setting above lives **inside** `settings`. There is no `dimension_columns` or
`metric_columns` key: which columns are dimensions and which are metrics is declared on
the **graph** (`dimensions` / `metrics`), not in the processing config.

## DB/API Reference

| Table | Purpose | Key Columns | Docs |
| ----- | ------- | ----------- | ---- |
| `dashboards` | Dashboard definitions | `id`, `name`, `description`, `config` (JSONB), `layout_id` | [schema-core.md](../09-database/schema-core.md) |
| `graphs` | Graph configurations | `id`, `dashboard_id`, `name`, `type`, `dimensions`, `metrics`, `config` (JSONB) | [schema-core.md](../09-database/schema-core.md) |
| `filters` | Global filter definitions | `id`, `name`, `type`, `config` (JSONB) | [schema-core.md](../09-database/schema-core.md) |
| `dashboard_filters` | Dashboard-filter bindings | `dashboard_id`, `filter_id` | [schema-access.md](../09-database/schema-access.md) |
| `dashboard_filter_values` | Cached filter options | `dashboard_id`, `filter_name`, `filter_value` | [schema-processing.md](../09-database/schema-processing.md) |
| `processing_configs` | CSV parsing settings | `dashboard_id`, `settings` (JSONB) | [schema-processing.md](../09-database/schema-processing.md) |
| `processing_logs` | Task status tracking | `id`, `dashboard_id`, `status`, `message`, `started_at`, `finished_at` | [schema-processing.md](../09-database/schema-processing.md) |
| `aggregated_data` | Stored chart data points | `dashboard_id`, `graph_id`, `dims` (JSONB), `metrics` (JSONB) | [schema-processing.md](../09-database/schema-processing.md) |
| `dashboard_access` | User permissions | `user_id`, `dashboard_id`, `permission` | [schema-access.md](../09-database/schema-access.md) |

## Cross-Links

- [Dashboards API](../02-dashboards/dashboards-api.md) — CRUD for dashboards, graphs, filters, access management
- [Processing API](../03-processing/processing-api.md) — Upload, processing, and data endpoints
- [Core Schema](../09-database/schema-core.md) — Table definitions for users, dashboards, layouts, graphs, filters
- [Processing Schema](../09-database/schema-processing.md) — Table definitions for aggregated data, processing configs, processing logs
- [Access Schema](../09-database/schema-access.md) — Table definitions for dashboard_access, dashboard_filters
- [Database Enums](../09-database/enums.md#4-filtertype) — `FilterType` and the retired `range` label
- [Data Flow](../00-overview/data-flow.md) — End-to-end upload-to-display pipeline
- [UI Pages](../07-frontend/pages.md#4-dashboard-view-page-dashboardid) — The dashboard's render states
- [Extend Graphs](./extend-graphs.md) — How to add new graph types
- [Extend Filters](./extend-filters.md) — How to add new filter types