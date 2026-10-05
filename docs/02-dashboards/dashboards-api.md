---
id: dashboards-api
domain: dashboards
tags:
  - dashboards
  - layouts
  - graphs
  - filters
  - crud
  - access-control
  - data-access
related:
  - schema-core
  - processing-api
  - auth-api
  - admin-api
  - ui-pages
---

# Dashboards API

## Overview

The dashboards API provides CRUD operations for dashboards, layouts, graphs, and filters. It also serves aggregated data for visualization. All endpoints are part of the `/api/v1` route group.

**Access control:** Dashboard access is validated on every request. Users see only dashboards they have been granted access to via the `dashboard_access` table. See [Access Control](../08-security/access-control.md) for the enforcement model.

**Base path:** `/api/v1`

---

## Dashboard Endpoints

### 1. List My Dashboards

Retrieve all dashboards the current user has access to.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/dashboards/my`        |
| **Auth level** | Any authenticated user         |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `skip`    | int  | `0`     | `>= 0` | Records to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum records returned. |

**Request:** Requires `Authorization: Bearer <token>` header.

**Response** (`200 OK`):

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Sales Dashboard",
    "description": "Quarterly sales metrics",
    "permission": "view",
    "created_at": "2026-04-24T16:02:46+03:00"
  }
]
```

---

### 2. Get Dashboard Detail

Retrieve a single dashboard by ID. Requires access to the dashboard.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/dashboards/:id`       |
| **Auth level** | Any authenticated user (with access) |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | Dashboard ID       |

**Response** (`200 OK`):

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Sales Dashboard",
  "description": "Quarterly sales metrics",
  "config": {
    "graph_types": ["bar", "line"],
    "filters": [
      {"field": "year", "type": "select"},
      {"field": "category", "type": "multiselect"}
    ]
  },
  "permission": "view",
  "layout_id": "660e8400-e29b-41d4-a716-446655440001",
  "created_at": "2026-04-24T16:02:46+03:00",
  "updated_at": "2026-04-24T16:02:46+03:00"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | User lacks dashboard access  | `Access denied`              |
| `404`  | Dashboard not found          | `Dashboard not found`        |

> The system distinguishes between "dashboard exists but no access" (403) and "dashboard does not exist" (404). Admin users bypass the access check entirely. See [Access Control](../08-security/access-control.md) for details.

---

### 3. Create Dashboard

Create a new dashboard. Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/dashboards/`          |
| **Auth level** | Admin                          |

**Request body:**

```json
{
  "name": "Marketing Dashboard",
  "description": "Marketing campaign metrics",
  "layout_id": "660e8400-e29b-41d4-a716-446655440001"
}
```

| Field         | Type            | Description                                              |
| ------------- | --------------- | -------------------------------------------------------- |
| `name`        | `string`        | Dashboard name (required, unique).                       |
| `description` | `string`        | Optional dashboard description.                          |
| `layout_id`   | `UUID`          | Optional associated layout.                              |

The created row also carries a `created_by` column (`UUID REFERENCES users(id) ON DELETE SET NULL`, nullable — see [Database Schema](../09-database/schema-core.md)). It is **server-set**: the service records the authenticated caller's id as `created_by`; it is **not** a client-supplied request field. **`created_by` records authorship and confers no access.** A user with no `dashboard_access` grant row for the dashboard cannot read it even if they created it, and a later administrator may revoke the creator's grant. The creator's readable access at creation time comes from the explicit `dashboard_access` row the service grants, not from `created_by`.

**Response** (`201 Created`): Dashboard detail object.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `422`  | Duplicate name               | Validation error             |

---

### 4. Update Dashboard

Update an existing dashboard. Requires edit permission on the dashboard.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `PUT`                          |
| **Path**       | `/api/v1/dashboards/:id`       |
| **Auth level** | Editor (or admin on dashboard)  |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | Dashboard ID       |

**Request body:**

```json
{
  "name": "Updated Dashboard Name",
  "description": "Updated description",
  "layout_id": "660e8400-e29b-41d4-a716-446655440001"
}
```

**Response** (`200 OK`): Updated dashboard detail object.

**Error responses:**

| Status | Condition                              | Detail                       |
| ------ | -------------------------------------- | ---------------------------- |
| `403`  | User lacks edit permission on dashboard  | `You don't have access to this dashboard` |
| `404`  | Dashboard not found                    | `Dashboard not found`        |
| `422`  | Validation error                       | Error message                |

---

### 5. Delete Dashboard

Delete a dashboard and all associated data (graphs, aggregated data, access entries). Requires admin permission on the dashboard.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/dashboards/:id`       |
| **Auth level** | Editor (admin permission on dashboard)    |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | Dashboard ID       |

**Response** (`204 No Content`)

**Error responses:**

| Status | Condition                              | Detail                       |
| ------ | -------------------------------------- | ---------------------------- |
| `403`  | User lacks admin permission on dashboard | `You don't have access to this dashboard` |
| `404`  | Dashboard not found                    | `Dashboard not found`        |

**Cascading effects:** Deleting a dashboard removes all associated graphs, aggregated data, dashboard access entries, dashboard-filter links, and processing configs (via `ON DELETE CASCADE`).

---

## Layout Endpoints

Layouts define the UI composition (grid, graph positions, filter bindings) without data bindings. They are reusable across dashboards.

### 6. List Layouts

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/layouts`              |
| **Auth level** | Any authenticated user         |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `skip`    | int  | `0`     | `>= 0` | Records to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum records returned. |

**Response** (`200 OK`):

```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Two Column Grid",
    "definition": {
      "grid": [{"x": 0, "y": 0, "w": 6, "h": 4}],
      "graphs": ["g1", "g2"],
      "filters": ["year"],
      "bindings": [
        {"filter": "year", "graphs": ["g1", "g2"]}
      ]
    },
    "created_at": "2026-04-24T16:02:46+03:00"
  }
]
```

---

### 7. Get Layout Detail

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/layouts/:id`          |
| **Auth level** | Any authenticated user         |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | Layout ID          |

**Response** (`200 OK`): Single layout object.

---

### 8. Create Layout

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/layouts`              |
| **Auth level** | Admin                          |

**Request body:**

```json
{
  "name": "Three Column Grid",
  "definition": {
    "grid": [
      {"x": 0, "y": 0, "w": 4, "h": 4},
      {"x": 4, "y": 0, "w": 4, "h": 4},
      {"x": 8, "y": 0, "w": 4, "h": 4}
    ],
    "graphs": ["g1", "g2", "g3"],
    "filters": ["year", "category"],
    "bindings": [
      {"filter": "year", "graphs": ["g1", "g2", "g3"]},
      {"filter": "category", "graphs": ["g1"]}
    ]
  }
}
```

**Response** (`201 Created`): Layout object.

**Error responses:**

| Status | Condition                    | Detail                              |
| ------ | ---------------------------- | ----------------------------------- |
| `403`  | Caller is not admin          | `Only admins can create layouts`    |
| `409`  | Duplicate name               | `A layout with the name '<name>' already exists` |
| `422`  | Invalid request body         | `Request validation failed`         |

---

### 9. Update Layout

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `PUT`                          |
| **Path**       | `/api/v1/layouts/:id`          |
| **Auth level** | Admin                          |

**Request body:** Same structure as Create Layout.

**Response** (`200 OK`): Updated layout object.

**Error responses:**

| Status | Condition                    | Detail                            |
| ------ | ---------------------------- | --------------------------------- |
| `403`  | Caller is not admin          | `Only admins can update layouts`  |
| `404`  | Layout not found             | `Layout not found`                |
| `409`  | Duplicate name               | `A layout with the name '<name>' already exists` |
| `422`  | Invalid request body         | `Request validation failed`       |

---

### 10. Delete Layout

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/layouts/:id`          |
| **Auth level** | Admin                          |

**Response** (`204 No Content`)

---

## Graph Endpoints

Graphs define chart configurations within a dashboard. Each graph belongs to exactly one dashboard.

### 11. List Graphs

Returns every graph on every dashboard the user can access. A `dashboard_id` filter is **not** accepted here — the dashboard scope is resolved from the caller's own access, not supplied by the client, and a caller holding the `admin` role is unrestricted. To list the graphs of one specific dashboard use [31. List Graphs for Dashboard](#31-list-graphs-for-dashboard) (`GET /api/v1/dashboards/{dashboard_id}/graphs`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/graphs/`              |
| **Auth level** | Any authenticated user         |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `skip`    | int  | `0`     | `>= 0` | Records to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum records returned. |

A `dashboard_id` parameter is ignored rather than rejected, so a client that sends one silently receives the unfiltered, bounded collection.

**Response** (`200 OK`):

```json
[
  {
    "id": "880e8400-e29b-41d4-a716-446655440003",
    "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Revenue by Month",
    "type": "bar",
    "config": {
      "x": "month",
      "color": "year",
      "metrics": ["revenue"],
      "orientation": "v",
      "barmode": "group"
    },
    "dimensions": ["month", "year"],
    "metrics": ["revenue", "cost"],
    "created_at": "2026-04-24T16:02:46+03:00"
  }
]
```

> The `config` keys in this example — and every other key it may carry — are drawn
> from a **closed declared vocabulary of fifteen keys**. `x_axis`, `y_axis` and
> `colors` are **not** keys: an undeclared key is refused by name at the request
> boundary. See [The config vocabulary](../11-guides/extend-graphs.md#the-config-vocabulary).

---

### 12. Get Graph Detail

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/graphs/:id`           |
| **Auth level** | Any authenticated user (with dashboard access) |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | Graph ID           |

**Response** (`200 OK`): Single graph object.

---

### 13. Create Graph

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/graphs/`              |
| **Auth level** | Admin                          |

**Request body:**

```json
{
  "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Profit Trend",
  "type": "line",
  "config": {
    "x": "date",
    "metrics": ["profit"],
    "layout": {
      "title": "Profit Trend",
      "yaxis": {"title": "Profit", "type": "linear"}
    }
  },
  "dimensions": ["date"],
  "metrics": ["profit"]
}
```

**Response** (`201 Created`): Graph object.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller is not admin          | Forbidden                    |
| `409`  | Duplicate name in dashboard  | `Conflict: graph creation failed` |
| `422`  | Invalid graph type           | Validation error             |

---

### 14. Update Graph

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `PUT`                          |
| **Path**       | `/api/v1/graphs/:id`           |
| **Auth level** | Admin                          |

**Request body:** Same structure as Create Graph (excluding `dashboard_id`).

**Response** (`200 OK`): Updated graph object.

---

### 15. Delete Graph

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/graphs/:id`           |
| **Auth level** | Admin                          |

**Response** (`204 No Content`)

---

## Graph Types

Graphs support the following types, defined by the `GraphType` StrEnum:

| Type     | Description                          | Plotly equivalent          |
| -------- | ------------------------------------ | -------------------------- |
| `bar`    | Vertical or horizontal bar chart     | `plotly.graph_objects.Bar` |
| `line`   | Line chart with optional markers     | `plotly.graph_objects.Scatter` (mode=lines) |
| `pie`    | Pie/donut chart                      | `plotly.graph_objects.Pie` |
| `table`  | Tabular data display                 | HTML `<table>`             |

### Graph Features

Feature configuration is stored in the `config` JSONB field of the `graphs` table,
but **a declared key is not a working feature**. The keys below are *reserved*: they
are validated at the request boundary, stored and returned on read, and read by
nothing in `src/` or `frontend/src/`. They are kept deliberately rather than silently
ignored, and lifting them needs a consumer as well as a producer — nothing in this
repository can write them, because no graph-editing UI exists.

| Key          | Intended feature                                                              | Status |
| ------------ | ----------------------------------------------------------------------------- | ------ |
| `secondary_y` | Dual Y-axes for comparing metrics with different scales                       | **RESERVED** — no consumer |
| `combined`   | Mixed chart types (e.g. bar + line) in a single graph                        | **Not a config key** — refused by name |
| `yoy`        | Year-over-year comparison; modes: `absolute` (value diff) or `percent` (% change) | **RESERVED** — no consumer |
| `xaxis`, `yaxis` | Axis title, type and range, at the config level                         | **RESERVED** — deliberately unwired; the renderer reads axis configuration from the response's `layout` field only |

See [The config vocabulary](../11-guides/extend-graphs.md#the-config-vocabulary) for
the complete classification of all fifteen declared keys.

---

## Filter Endpoints

Filters are reusable across dashboards via the `dashboard_filters` many-to-many join table. They are applied globally to all graphs on a dashboard.

> **The global filter CRUD routes are removed.** Endpoints 16–20 below
> (`GET/POST/PUT/DELETE /api/v1/filters`) no longer exist: they were orphaned
> (no frontend caller) and `src/mkobi/api/routes/filters.py` is now a
> placeholder module that registers **no route**. Filter rows are seeded
> directly into the `filters` table. The live filter surfaces are the
> dashboard-scoped binding endpoints (27–29) and
> `GET /api/v1/dashboards/{dashboard_id}/filter-values` (see *Filter Values*).
> The entries below are retained only as a historical record of the removed
> API.

### 16. List Filters

Returns filters for dashboards the user has access to. Editor and above.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/filters`              |
| **Auth level** | Editor+                        |

**Query parameters:**

| Parameter      | Type   | Required | Description                    |
| -------------- | ------ | -------- | ------------------------------ |
| `dashboard_id` | UUID   | No       | Filter by specific dashboard   |
| `skip`         | int    | No       | Records to skip (offset), `>= 0`. Default `0`. |
| `limit`        | int    | No       | Maximum records returned, `1..1000`. Default `100`. |

**Response** (`200 OK`):

```json
[
  {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "name": "year",
    "type": "select",
    "config": {
      "field": "year",
      "source": "dims",
      "multi": false
    },
    "created_at": "2026-04-24T16:02:46+03:00"
  }
]
```

---

### 17. Get Filter Detail

Editor and above.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/filters/:id`          |
| **Auth level** | Editor+                        |

**Path parameters:**

| Parameter | Type   | Description        |
| --------- | ------ | ------------------ |
| `id`      | UUID   | Filter ID          |

**Response** (`200 OK`): Single filter object.

---

### 18. Create Filter

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `POST`                         |
| **Path**       | `/api/v1/filters`              |
| **Auth level** | Admin                          |

**Request body:**

```json
{
  "name": "category",
  "type": "multiselect",
  "config": {
    "field": "category",
    "source": "dims",
    "multi": true
  }
}
```

**Response** (`201 Created`): Filter object.

---

### 19. Update Filter

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `PUT`                          |
| **Path**       | `/api/v1/filters/:id`          |
| **Auth level** | Admin                          |

**Request body:** Same structure as Create Filter.

**Response** (`200 OK`): Updated filter object.

---

### 20. Delete Filter

Admin only.

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `DELETE`                       |
| **Path**       | `/api/v1/filters/:id`          |
| **Auth level** | Admin                          |

**Response** (`204 No Content`)

---

## Filter Types

Filters support the following types. The controlling vocabulary for what a filter
value may be is **not** `FilterType` — it is `EvaluableFilterType`
(`src/mkobi/models/dashboard.py`), which is the closed set a submitted value can
actually be evaluated against:

| Type          | Description                              | UI Control          | Value shape on `GET /data/aggregated` |
| ------------- | ---------------------------------------- | ------------------- | ------------------------------------- |
| `select`      | Single value selection                   | Dropdown            | Scalar (`->>` equality) |
| `multiselect` | Multiple value selection                 | Multi-select        | **`list[str]`** (membership union); an empty list constrains nothing |
| `date`        | Single date selection                    | Date picker         | Scalar (`->>` equality) |

There is **no** evaluable `range`. The `range` filter type is **retired**: it has no
control in the filters panel, and a stored `range` filter is refused **by name** —
`422` on a dashboard save naming the field and the supported set, and `422` on the
aggregate read naming the filter and its reason. A dashboard that already stores one
renders a **non-blocking warning inside the filters panel** and sends no value; it is
**not** blanked and it is **not** an empty state.

The `FilterType.RANGE` enum member and the `filter_type` PostgreSQL label **still
exist** and are inert; their removal is deferred to phase 14 (`C14-17`). The
`filters.type` column therefore still accepts the label — the retirement is in the
*evaluation*, not in the schema. See [Database Enums](../09-database/enums.md#4-filtertype).

### Filter Value Source

Filters can receive their option values from two different sources, controlled by the `config.source` field:

| Source       | Description |
| ------------ | ----------- |
| `dims` (default) | Static options defined in `config.options` |
| `data`       | Dynamic values extracted from aggregated data and stored in `dashboard_filter_values` table |

When `source === "data"`, the frontend fetches values from `GET /api/v1/dashboards/{dashboard_id}/filter-values?filter_name={name}` instead of using static options. Values are automatically extracted and persisted to the `dashboard_filter_values` table during each CSV upload processing run. See [Processing Schema](../09-database/schema-processing.md) for the table definition.

### Backend Implementation

Filters are applied on the backend through parameterized SQL queries against the `aggregated_data` table. Filter values are never interpolated into SQL strings — all queries use SQLAlchemy parameterized queries.

Example filter application flow:

1. Frontend sends selected filter values as a JSON-encoded `filters` query parameter
2. Backend validates the payload's shape and bounds, then checks each submitted key's **admissibility** against the dashboard's declared filter types
3. Each key becomes one predicate on `aggregated_data.dims`: a scalar uses `->>` `=`, a list uses `->>` `IN (…)`
4. Filtered results are returned as graph data

The `->>` extraction operator is what the predicates use, and `->>` does **not** reach
the `idx_aggregated_data_dims_gin` index; the read is served by
`idx_aggregated_data_dashboard_graph`. See [Indexes](../09-database/indexes.md#4-idx_aggregated_data_dims_gin)
for what does and does not reach that GIN index.

A submitted value is additionally checked for **admissibility** before any branch is
taken: a `range`-declared key is refused by name whatever the value's shape, and a
`list` is refused by name on any key not declared `multiselect`. Both refusals are
`422` RFC 7807 responses carrying `{filter, declared_type, reason}` in `details`. The
full rule, and the **bound** that a two-string value on an undeclared filter is
indistinguishable from a two-value multiselect, are documented once in
[Processing API → Filter values and admissibility](../03-processing/processing-api.md#filter-values-and-admissibility).

---

## Filter Values Endpoint

### 32. Get Filter Values

Returns distinct values for a specific filter/dimension of a dashboard. Values are extracted from aggregated data and cached in the `dashboard_filter_values` table. Used to dynamically populate filter UI controls when `config.source === "data"`.

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/filter-values`  |
| **Auth level** | Any authenticated user (with dashboard access)     |
| **Query param**| `filter_name` — Name of the filter/dimension       |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `filter_name` | str | — | — | Name of the filter/dimension. |
| `skip`    | int  | `0`     | `>= 0` | Values to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum values returned. |

`total_values` is the **true, untruncated** distinct-value count, reported from a `COUNT(*)` query rather than the length of the possibly bounded `values` list.

**Response** (`200 OK`):

```json
{
  "filter_name": "category",
  "values": ["Electronics", "Food", "Services"],
  "total_values": 3
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | User lacks dashboard access  | `Access denied`              |
| `500`  | Database error               | `Error getting filter values` |

---

## Processing Config Endpoints

Processing configs define how CSV data is parsed and aggregated for a specific dashboard.

### 21. Get Processing Config

Viewer and above.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `GET`                                      |
| **Path**       | `/api/v1/processing-configs/:dashboard_id` |
| **Auth level** | Viewer+                                    |

**Path parameters:**

| Parameter      | Type   | Description        |
| -------------- | ------ | ------------------ |
| `dashboard_id` | UUID   | Dashboard ID       |

**Response** (`200 OK`):

```json
{
  "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
  "settings": {
    "loader": "sales_loader",
    "date_column": "event_date",
    "timezone": "UTC"
  },
  "updated_at": "2026-04-24T16:02:46+03:00"
}
```

---

### 22. Update Processing Config

Editor and above.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `PUT`                                      |
| **Path**       | `/api/v1/processing-configs/:dashboard_id` |
| **Auth level** | Editor+                                    |

**Request body:**

```json
{
  "settings": {
    "loader": "sales_loader",
    "date_column": "event_date",
    "timezone": "Europe/Moscow"
  }
}
```

**Response** (`200 OK`): Updated processing config object.

---

### 23. Delete Processing Config

Editor and above.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `DELETE`                                   |
| **Path**       | `/api/v1/processing-configs/:dashboard_id` |
| **Auth level** | Editor+                                    |

**Response** (`204 No Content`)

---

## Dashboard Access Management

Managing access to a dashboard requires an `admin` permission on that dashboard or the `admin` role, which bypasses the per-dashboard check; an administrator who is neither owner nor grantee may manage access.

### 24. Grant Dashboard Access

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/access`         |
| **Auth level** | Owner or administrator                             |

**Request body:**

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "dashboard_id": "660e8400-e29b-41d4-a716-446655440001",
  "permission": "view"
}
```

**Response** (`200 OK`):

```json
{
  "message": "Access granted",
  "dashboard_id": "660e8400-e29b-41d4-a716-446655440001",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "permission": "admin"
}
```

**Valid permission levels:** `view`, `edit`, `admin` (defined by `DashboardPermission` StrEnum). The value is bound and stored under its lowercase enum label.

A grant for a `(user_id, dashboard_id)` pair that already exists **applies the requested permission**: the stored permission becomes the requested one and the response body carries it, so a re-grant of `admin` over an existing `view` returns `"permission": "admin"` and updates the stored row. This is a write, not a no-op.

The response echoes the **requested** permission, and that equals the stored value because the boundary rejects any other: the request model admits only `view`/`edit`/`admin`, so the echoed value is necessarily what the upsert wrote. This is a boundary guarantee, not a structural one — the handler cannot read the stored row back and does not claim to.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller holds neither an `admin` grant on this dashboard nor the `admin` role | `You do not have admin access to this dashboard` |
| `404`  | Admitted caller (owner or administrator) and the dashboard does not exist | `Dashboard not found` |
| `422`  | `permission` outside `view` / `edit` / `admin` | `Request validation failed` |
| `422`  | dashboard_id mismatch        | `dashboard_id in body doesn't match URL` |

The absent-dashboard case is role-dependent: an admitted caller (owner or administrator) reaches the handler and receives `404` when the dashboard does not exist, while a caller outside the audience receives `403` whether or not the dashboard exists, because the admin-access gate runs before the handler body.

---

### 25. List Dashboard Access

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/access`         |
| **Auth level** | Owner or administrator                             |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `skip`    | int  | `0`     | `>= 0` | Records to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum records returned. |

**Response** (`200 OK`): List of access records with user_id, permission level. An admitted caller (owner or administrator) receives `200` with an empty list when the dashboard has no access records; a caller outside the audience receives `403` whether or not the dashboard exists.

**The empty-list-versus-forbidden distinction:** the audience check is the *only* thing that produces `403` here. Once a caller is inside the audience, the ACL read is always `200`, and an empty list means "this dashboard has no access rows", not "you may not see them". A `200 []` is therefore never an admission failure, and a caller that cannot see the records never receives an empty body in place of a refusal — it receives `403`. The status codes do not move with the row count.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller holds neither an `admin` grant on this dashboard nor the `admin` role | `You do not have admin access to this dashboard` |

---

### 26. Revoke Dashboard Access

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `DELETE`                                           |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/access/{user_id}` |
| **Auth level** | Owner or administrator                             |

**Response** (`200 OK`):

```json
{
  "message": "Access revoked successfully"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller holds neither an `admin` grant on this dashboard nor the `admin` role | `You do not have admin access to this dashboard` |
| `404`  | No access record exists for this `(user_id, dashboard_id)` | `Access record not found`    |

---

## Dashboard-Filter Binding

Filters are linked to dashboards via the `dashboard_filters` many-to-many join table. Bound filters appear on the dashboard's filter panel.

### 27. Bind Filter to Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/filters`        |
| **Auth level** | Dashboard admin (an `admin` grant on this dashboard, or the `admin` role) |
| **Query param**| `filter_id` — UUID of the filter to bind           |

A caller outside that audience receives `403` whether or not the dashboard and filter exist, because the dashboard admin gate runs before the handler body.

**Response** (`200 OK`):

```json
{
  "message": "Filter bound to dashboard",
  "bound": true
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller holds neither an `admin` grant on this dashboard nor the `admin` role | `You do not have admin access to this dashboard` |
| `404`  | Dashboard not found          | `Dashboard not found`        |
| `404`  | Filter not found             | `Filter not found`           |

---

### 28. Unbind Filter from Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `DELETE`                                           |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/filters/{filter_id}` |
| **Auth level** | Dashboard admin (an `admin` grant on this dashboard, or the `admin` role) |

A caller outside that audience receives `403` whether or not the dashboard exists, because the dashboard admin gate runs before the handler body.

**Response** (`200 OK`):

```json
{
  "message": "Filter unbound from dashboard"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller holds neither an `admin` grant on this dashboard nor the `admin` role | `You do not have admin access to this dashboard` |
| `404`  | Dashboard not found          | `Dashboard not found`        |
| `404`  | Filter not bound to the dashboard | `Filter not bound to this dashboard` |

---

### 29. List Dashboard Filters

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/filters`        |
| **Auth level** | Any authenticated user (with dashboard access)     |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `skip`    | int  | `0`     | `>= 0` | Records to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum records returned. |

**Response** (`200 OK`): List of filter IDs bound to the dashboard.

---

## Dashboard Graph Endpoints

In addition to the global graph endpoints, graphs can be created and listed via dashboard-scoped endpoints.

### 30. Create Graph for Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/graphs`         |
| **Auth level** | Dashboard admin (an `admin` grant on this dashboard, or the `admin` role) |

A caller outside that audience receives `403` whether or not the dashboard exists, because the dashboard admin gate runs before the handler body.

**Request body:** Same structure as global Create Graph.

**Response** (`201 Created`): Graph object.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `403`  | Caller holds neither an `admin` grant on this dashboard nor the `admin` role | `You do not have admin access to this dashboard` |
| `409`  | Duplicate name in dashboard  | `Conflict: graph creation failed` |

---

### 31. List Graphs for Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/graphs`         |
| **Auth level** | Any authenticated user (with dashboard access)     |

**Query parameters:**

| Parameter | Type | Default | Bounds | Description |
| --------- | ---- | ------- | ------ | ----------- |
| `skip`    | int  | `0`     | `>= 0` | Records to skip (offset). |
| `limit`   | int  | `100`   | `1..1000` | Maximum records returned. |

**Response** (`200 OK`): List of graph objects for the dashboard.

---

## Data Access Pattern

Aggregated data is served through the data endpoints (see [Data API](../03-processing/processing-api.md) and [Data Flow](../00-overview/data-flow.md)). The typical flow:

```
Browser                          FastAPI                     PostgreSQL
  │                                │                           │
  │  GET /data/aggregated          │                           │
  │  ?dashboard_id=:id             │                           │
  │  &filters=...                  │                           │
  │  (graph_id omitted)            │                           │
  │ ──────────────────────────────►│                           │
  │                                │  Check dashboard access   │
  │                                │  Apply filters (JSONB)    │
  │                                │  SELECT dims, metrics     │
  │                                │  FROM aggregated_data     │
  │                                │  WHERE dashboard_id = :id │
  │                                │  ORDER BY id LIMIT ...    │
  │                                │──────────────────────────►│
  │                                │                           │
  │                                │  { dims: {...},           │
  │                                │    metrics: {...} }[]     │
  │                                │◄──────────────────────────│
  │  200 OK                        │                           │
  │  {graphs:[...], total_rows,    │                           │
  │   truncated}                   │                           │
  │ ◄──────────────────────────────│                           │
  │                                │                           │
  │  Plotly.js renders chart       │                           │
```

The dashboard view issues **one** request for the whole dashboard with
`graph_id` **absent** — there is no per-graph fan-out (`DP-13-A`). The
`graph_id` parameter remains accepted by the endpoint but the client never sends
it; each chart reads its own graph out of the single bounded response.

---

### Aggregate read bounds and the truncation contract

The aggregate read is **bounded**. Before this change it had no row bound; the
read path allocates roughly **3,402 B/row** (linear; the 1,277 B/row floor
after removing the eager ORM cascade is the raw JSONB payload), and the linear
memory curve crosses the application's 1 GiB cgroup limit between **250,000 and
300,000 rows**. An uncapped read was the defect.

Two settings bound it (`src/mkobi/config.py`, `DataSettings`):

| Setting | Default | Meaning |
| --- | --- | --- |
| `DATA__MAX_ROWS_PER_GRAPH` | `2000` | Rows returned for one graph in one response. |
| `DATA__MAX_ROWS_TOTAL` | `20000` | Rows returned across the whole dashboard response. |

**Derivation.** 20,000 rows × 3,402 B/row is roughly **68 MB** for one dashboard
response, which leaves comfortable headroom inside the 1 GiB application limit
while `--workers 4` serve concurrently. The per-graph cap keeps any single
chart's payload small; the total cap bounds the whole response.

**Truncation is visible, never silent.** The response reports the true,
untruncated counts alongside the bounded rows:

```json
{
  "graphs": [
    {
      "graph_id": "…",
      "type": "bar",
      "name": "Sales by Category",
      "data": [ {"category": "A", "revenue_sum": 1000} ],
      "metrics": ["revenue_sum"],
      "dimensions": ["category"],
      "returned_rows": 1,
      "total_rows": 5000,
      "rows_truncated": true,
      "layout": null,
      "config": {"x": "category", "metrics": ["revenue"]}
    }
  ],
  "total_rows": 5000,
  "truncated": true
}
```

- `GraphDataResponse.returned_rows` — the number of rows the server placed in
  `data`. The lower bound of "Showing N of M" renders from this field
  (`DP-13-C`): a client-side `data.length` would stop describing what the
  server sent once the client transforms the array. **Mandatory**.
- `GraphDataResponse.total_rows` — the graph's true row count, from a
  `COUNT(*)` query, never the length of the bounded page. **Mandatory**
  (`DP-11-B`).
- `GraphDataResponse.rows_truncated` — true exactly when `data` holds fewer
  rows than `total_rows`.
- `GraphDataResponse.metrics` / `.dimensions` — the **served, post-alias** column
  names actually present on the served rows, in first-seen order. Optional with an
  empty default, so neither is in the OpenAPI `required` list. These are **not**
  `config["metrics"]` / `config["x"]`, which are the operator's pre-alias input; a
  client reading the served names applies no `_{metric_agg}` suffix rule to them.
- `GraphDataResponse.layout` — the graph's stored `config["layout"]`, served as
  stored, or `null` when none was stored. **Not** a merge of the config-level
  `title` / `showlegend` / `xaxis` / `yaxis` twins.
- `GraphDataResponse.config` — the graph's stored `config` object, unchanged.
- `AggregatedDataResponse.total_rows` — the dashboard-wide true row count.
- `AggregatedDataResponse.truncated` — true when any graph was bounded.

When the dashboard-wide budget is exhausted, the remaining graphs still appear
in the response with their counts and an empty `data` list. Which rows come
back is **deterministic**: the `ORDER BY aggregated_data.id` order is
preserved, so identical requests return the identical slice. The server does
**not** aggregate to fit the cap — the row content and its shape are unchanged;
only the number of rows is bounded. The client renders "Showing N of M" from
the server's `returned_rows`/`total_rows`/`rows_truncated` fields (`DP-13-C`),
not from any client-side count.

---

### Filter payload bounds (`PRF-5`)

The `filters` query parameter is a JSON-encoded object. Each key becomes one
predicate on `aggregated_data.dims` in the aggregate query, and nothing previously
bounded its width, so any caller could make the planner build an arbitrarily large
predicate set. The application now validates the payload against four bounds
(`src/mkobi/models/data.py`, `AggregatedFiltersRequest`):

| Bound | Value | Constant |
| --- | --- | --- |
| Filter keys | 20 | `MAX_FILTER_KEYS` |
| Key-name length | 64 characters | `MAX_FILTER_KEY_LENGTH` |
| Value length | 256 characters **per element** | `MAX_FILTER_VALUE_LENGTH` |
| Serialised payload | 4 KB | `MAX_FILTER_PAYLOAD_BYTES` |

**Derivation.** Phase-1 measurement found that query *execution* time stays in
a 16.4–33.1 ms band regardless of key count, with the plan node staying
`Index Scan` at every key count; it is *planning* time that grows — 0.889 ms at
zero keys to 37.971 ms at one thousand keys (43×). Bounding the payload is
therefore about the plan, not the scan: 20 keys with realistic key/value
lengths holds planning time to roughly 1.6 ms instead of the 38 ms a thousand
keys produce. The edge applies nginx's default 8 KB request-line limit (no
`large_client_header_buffers` directive exists repository-wide), so a payload
that reaches the application is already under ~8 KB; 20 keys sit comfortably
inside that ceiling. The bound is enforced in the application layer, not at the
proxy.

A payload that violates any bound is rejected with the same RFC 7807
`VALIDATION_ERROR` (HTTP `422`) as malformed JSON, raised through
`AppException`. The length bound is measured **element-wise** for a list value
rather than through the scalar `len(str(value))` branch: it *attributes* the
violation, naming the offending key and the offending element's length, and it
*widens* acceptance for multi-element lists the scalar branch used to refuse.
No per-key element-count bound is applied — a list compiles to **one** membership
predicate regardless of length, so the plan-time rationale does not apply, and
the payload-size bound already caps the total element count.

### Filter values: membership and admissibility

A value may be a **scalar** or a **`list[str]`**, and the two are decided in two
different layers:

- **Shape**, in `AggregatedFiltersRequest`: the union above. A payload that violates
  the union is a `422`.
- **Admissibility**, in `DataService.validate_filter_values`: whether the *declared
  type* of the submitted key can evaluate the value at all. A `range`-declared key is
  refused **by name** whatever the shape; a `list` is refused **by name** on any key
  not declared `multiselect`.

A **list** means *membership*: the returned rows are the union over the listed values.
An **empty list** imposes **no** constraint and returns everything. A **scalar**
filter's behaviour is unchanged. A value is bounded per element; the whole payload
remains bounded.

The complete admissibility table, the RFC 7807 refusal shape, and the **bound** — a
two-string value on a dashboard that declares no filters is permitted and matched as a
membership test, because it is indistinguishable on the wire from a legitimate
two-value multiselect and is unreachable from anything the application produces — are
stated once in [Processing API → Filter values and admissibility](../03-processing/processing-api.md#filter-values-and-admissibility). That bound is **not** a claim that the retired `range` hole is closed.

---

## UI Page References

The following frontend pages consume the dashboards API:

| UI Page                        | Path                    | Key Endpoints Used                                      |
| ------------------------------ | ----------------------- | ------------------------------------------------------- |
| Dashboard List                 | `/dashboards`           | `GET /api/v1/dashboards/my`                             |
| Dashboard View                 | `/dashboard/:id`        | `GET /api/v1/dashboards/:id`, `GET /api/v1/data/aggregated`, `POST /api/v1/upload/:dashboard_id` |
| Admin Dashboard Management     | `/admin`                | CRUD endpoints for dashboards, layouts, graphs, filters |

### Dashboard List Page (`/dashboards`)

- Opens after successful login
- Displays dashboards in a sortable DataGrid table (ID, Name, Created columns)
- Clicking a row navigates to `/dashboard/:id`
- Shows empty state when user has no dashboard access
- Redirects to `/login` if the session is expired

### Dashboard View Page (`/dashboard/:id`)

- Displays the dashboard title, description, and filter panel
- Renders charts in a grid layout using Plotly.js React
- Upload button visible for `admin` and `editor` roles; opens UploadModal dialog (no page navigation)
- Filters panel dynamically renders controls based on filter configuration
- Filter changes trigger new data requests with updated filter parameters
- After upload completion, dashboard data refreshes automatically

---

## Access Control

All dashboard-related endpoints enforce access control:

- **Dashboard endpoints:** Users must have an entry in `dashboard_access` for the requested dashboard
- **Graph endpoints:** Graph definitions are filtered by dashboard access
- **Filter endpoints:** Filters are only returned if the user has access to the associated dashboard

The `check_dashboard_access` function verifies the user's permission against the `dashboard_access` table for the specific dashboard resource being accessed.

---

## Cross-References

- [Database Schema](../09-database/schema-core.md) — Table definitions for `dashboards`, `layouts`, `graphs`, `filters`, `dashboard_access`, `dashboard_filters`, `processing_configs`, `aggregated_data`
- [Access Control](../08-security/access-control.md) — Dashboard-level permission enforcement
- [Processing API](../03-processing/processing-api.md) — Upload, processing triggers, and aggregated data retrieval
- [Security Overview](../08-security/) — CORS, rate limiting, credential enforcement
- [Frontend Pages](../07-frontend/pages.md) — UI pages consuming the dashboards API
- [Database Enums](../09-database/enums.md) — `GraphType`, `FilterType` StrEnum definitions
