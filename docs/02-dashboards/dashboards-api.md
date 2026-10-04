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
| `409`  | Duplicate name               | `Conflict: layout creation failed`  |
| `422`  | Invalid request body         | Validation error                    |

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
| `409`  | Duplicate name               | `Conflict: layout update failed`  |
| `422`  | Invalid request body         | Validation error                  |

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

Returns every graph on every dashboard the user can access. **This endpoint accepts no query parameters** — the dashboard scope is resolved from the caller's own access, not supplied by the client, and a caller holding the `admin` role is unrestricted. To list the graphs of one specific dashboard use [31. List Graphs for Dashboard](#31-list-graphs-for-dashboard) (`GET /api/v1/dashboards/{dashboard_id}/graphs`).

| Attribute      | Value                          |
| -------------- | ------------------------------ |
| **Method**     | `GET`                          |
| **Path**       | `/api/v1/graphs/`              |
| **Auth level** | Any authenticated user         |

**Query parameters:** None. A `dashboard_id` filter is not accepted here; the parameter is ignored rather than rejected, so a client that sends one silently receives the unfiltered collection.

**Response** (`200 OK`):

```json
[
  {
    "id": "880e8400-e29b-41d4-a716-446655440003",
    "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Revenue by Month",
    "type": "bar",
    "config": {
      "x_axis": "month",
      "y_axis": "revenue",
      "orientation": "v",
      "barmode": "group",
      "colors": ["#1f77b4", "#ff7f0e"]
    },
    "dimensions": ["month", "year"],
    "metrics": ["revenue", "cost"],
    "created_at": "2026-04-24T16:02:46+03:00"
  }
]
```

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
    "x_axis": "date",
    "y_axis": "profit",
    "yoy_mode": "percent"
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

| Feature        | Description                                                                 |
| -------------- | --------------------------------------------------------------------------- |
| `multi-axis`   | Dual Y-axes for comparing metrics with different scales                     |
| `combined`     | Mixed chart types (e.g., bar + line) in a single graph                      |
| `YoY`          | Year-over-year comparison; modes: `absolute` (value diff) or `percent` (% change) |

Feature configuration is stored in the `config` JSONB field of the `graphs` table.

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

Filters support the following types, defined by the `FilterType` StrEnum:

| Type          | Description                                      | UI Control          |
| ------------- | ------------------------------------------------ | ------------------- |
| `select`      | Single value selection                           | Dropdown            |
| `multiselect` | Multiple value selection                         | Multi-select        |
| `range`       | Numeric range (min/max)                          | Range slider        |
| `date`        | Date or date range selection                     | Date picker         |

### Filter Value Source

Filters can receive their option values from two different sources, controlled by the `config.source` field:

| Source       | Description |
| ------------ | ----------- |
| `dims` (default) | Static options defined in `config.options` |
| `data`       | Dynamic values extracted from aggregated data and stored in `dashboard_filter_values` table |

When `source === "data"`, the frontend fetches values from `GET /api/v1/dashboards/{dashboard_id}/filter-values?filter_name={name}` instead of using static options. Values are automatically extracted and persisted to the `dashboard_filter_values` table during each CSV upload processing run. See [Processing Schema](../09-database/schema-processing.md) for the table definition.

### Backend Implementation

Filters are applied on the backend through parameterized SQL queries against the `aggregated_data` table. The `dims` JSONB column is filtered using PostgreSQL JSONB operators. Filter values are never interpolated into SQL strings — all queries use SQLAlchemy parameterized queries.

Example filter application flow:

1. Frontend sends selected filter values as query parameters
2. Backend constructs a query filtering `aggregated_data.dims` using JSONB containment operators (`@>`)
3. Filtered results are returned as graph data

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

**Response** (`200 OK`):

```json
{
  "filter_name": "category",
  "values": ["Electronics", "Food", "Services"]
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
| `422`  | Admitted caller (owner or administrator) and the dashboard does not exist | `Dashboard with id=<dashboard_id> not found` |
| `422`  | `permission` outside `view` / `edit` / `admin` | `Request validation failed` |
| `422`  | dashboard_id mismatch        | `dashboard_id in body doesn't match URL` |

The absent-dashboard case is role-dependent: an admitted caller (owner or administrator) reaches the handler and receives `422` when the dashboard does not exist, while a caller outside the audience receives `403` whether or not the dashboard exists, because the admin-access gate runs before the handler body.

---

### 25. List Dashboard Access

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/access`         |
| **Auth level** | Owner or administrator                             |

**Response** (`200 OK`): List of access records with user_id, permission level. An admitted caller (owner or administrator) receives `200` with an empty list when the dashboard has no access records; a caller outside the audience receives `403` whether or not the dashboard exists.

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
| **Auth level** | Admin                                              |
| **Query param**| `filter_id` — UUID of the filter to bind           |

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
| `404`  | Filter not found             | `Filter not found`           |
| `409`  | Already bound / integrity    | `Conflict: filter binding failed` |

---

### 28. Unbind Filter from Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `DELETE`                                           |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/filters/{filter_id}` |
| **Auth level** | Admin                                              |

**Response** (`200 OK`):

```json
{
  "message": "Filter unbound from dashboard"
}
```

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `404`  | Filter not bound             | `Filter not bound to this dashboard` |

---

### 29. List Dashboard Filters

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/filters`        |
| **Auth level** | Any authenticated user (with dashboard access)     |

**Response** (`200 OK`): List of filter IDs bound to the dashboard.

---

## Dashboard Graph Endpoints

In addition to the global graph endpoints, graphs can be created and listed via dashboard-scoped endpoints.

### 30. Create Graph for Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `POST`                                             |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/graphs`         |
| **Auth level** | Admin                                              |

**Request body:** Same structure as global Create Graph.

**Response** (`201 Created`): Graph object.

**Error responses:**

| Status | Condition                    | Detail                       |
| ------ | ---------------------------- | ---------------------------- |
| `409`  | Duplicate name in dashboard  | `Conflict: graph creation failed` |

---

### 31. List Graphs for Dashboard

| Attribute      | Value                                              |
| -------------- | -------------------------------------------------- |
| **Method**     | `GET`                                              |
| **Path**       | `/api/v1/dashboards/{dashboard_id}/graphs`         |
| **Auth level** | Any authenticated user (with dashboard access)     |

**Response** (`200 OK`): List of graph objects for the dashboard.

---

## Data Access Pattern

Aggregated data is served through the data endpoints (see [Data API](../03-processing/processing-api.md) and [Data Flow](../00-overview/data-flow.md)). The typical flow:

```
Browser                          FastAPI                     PostgreSQL
  │                                │                           │
  │  GET /data/aggregated          │                           │
  │  ?dashboard_id=:id             │                           │
  │  &graph_id=:id                 │                           │
  │  &filters=...                  │                           │
  │ ──────────────────────────────►│                           │
  │                                │  Check dashboard access   │
  │                                │  Apply filters (JSONB)    │
  │                                │  SELECT dims, metrics     │
  │                                │  FROM aggregated_data     │
  │                                │  WHERE graph_id = :id     │
  │                                │──────────────────────────►│
  │                                │                           │
  │                                │  { dims: {...},           │
  │                                │    metrics: {...} }[]     │
  │                                │◄──────────────────────────│
  │  200 OK                        │                           │
  │  [{dims, metrics}, ...]        │                           │
  │ ◄──────────────────────────────│                           │
  │                                │                           │
  │  Plotly.js renders chart       │                           │
```

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
      "data": [ {"category": "A", "revenue": 1000} ],
      "returned_rows": 1,
      "total_rows": 5000,
      "rows_truncated": true
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
`->>` equality in the aggregate query, and nothing previously bounded its
width, so any caller could make the planner build an arbitrarily large
predicate set. The application now validates the payload against four bounds
(`src/mkobi/models/data.py`, `AggregatedFiltersRequest`):

| Bound | Value | Constant |
| --- | --- | --- |
| Filter keys | 20 | `MAX_FILTER_KEYS` |
| Key-name length | 64 characters | `MAX_FILTER_KEY_LENGTH` |
| Value length | 256 characters | `MAX_FILTER_VALUE_LENGTH` |
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
`AppException`. The repository query is unchanged: `->>` equality per key, with
no interpolation.

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
