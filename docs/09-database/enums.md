---
id: enums
domain: database
tags:
  - strenum
  - postgresql-enum
  - user-role
  - graph-type
  - filter-type
  - processing-status
  - upload-mode
related:
  - schema-core
  - schema-processing
  - schema-access
  - indexes
---

# Database Enums (StrEnum)

## Overview

All fixed values in the system are defined as `StrEnum` classes in `src/mkobi/models/enums.py`. StrEnum members are string-valued, making them directly serializable and compatible with PostgreSQL ENUM types.

**Total StrEnum classes:** 19

---

## Reference Table

| #  | Class Name               | Values                                          | PostgreSQL ENUM       | Used In Table(s)         |
| -- | ------------------------ | ----------------------------------------------- | --------------------- | ------------------------ |
| 1  | `UserRole`               | `admin`, `editor`, `viewer`                     | `user_role`           | `users`                  |
| 2  | `DashboardPermission`    | `view`, `edit`, `admin`                         | `dashboard_permission_level` | `dashboard_access` |
| 3  | `GraphType`              | `bar`, `line`, `pie`, `table`                   | `graph_type`          | `graphs`                 |
| 4  | `FilterType`             | `select`, `multiselect`, `range`, `date`        | `filter_type`         | `filters`                |
| 5  | `RegistrationStatus`     | `pending`, `approved`, `rejected`               | `registration_status` | `registration_requests`  |
| 6  | `UploadMode`             | `overwrite`, `append`                           | —                     | API parameter            |
| 7  | `ProcessingStatus`       | `started`, `uploaded`, `processing`, `success`, `failed`, `completed` | `processing_status` | `processing_logs` |
| 8  | `EnvironmentEnum`        | `production`, `staging`, `development`, `test`  | —                     | Configuration            |
| 9  | `MimeTypeEnum`           | `text/csv`, `application/gzip`, `application/x-gzip` | —              | Upload validation        |
| 10 | `FileExtensionEnum`      | `csv`, `csv.gz`                                 | —                     | Upload validation        |
| 11 | `AggregationFunctionEnum`| `sum`, `mean`, `count`, `min`, `max`, `median`, `std`, `var`, `first`, `last` | — | Processing config |
| 12 | `FilterOperatorEnum`     | `==`, `!=`, `>`, `<`, `>=`, `<=`               | —                     | Filter logic             |
| 13 | `OrientationEnum`        | `v`, `h`                                        | —                     | Graph config (JSONB)     |
| 14 | `BarmodeEnum`            | `group`, `stack`                                | —                     | Graph config (JSONB)     |
| 15 | `YoyModeEnum`            | `absolute`, `percent`                           | —                     | Graph config (JSONB)     |
| 16 | `ButtonVariant`          | `primary`, `secondary`, `success`, `danger`, `warning`, `info`, `light`, `dark` | — | `Layout vocabulary only (not enforced)` |
| 17 | `ComponentSize`          | `sm`, `md`, `lg`                                | —                     | `Layout vocabulary only (not enforced)` |

---

## Detailed Definitions

### 1. `UserRole`

Defines system user roles for role-based access control.

```python
class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
```

| Value     | Description                                      |
| --------- | ------------------------------------------------ |
| `admin`   | Full system access: CRUD dashboards, manage users, grant access |
| `editor`  | Can upload CSV and trigger data processing       |
| `viewer`  | Read-only access to assigned dashboards          |

**PostgreSQL ENUM:** `user_role`
**Table:** `users.role`

---

### 2. `DashboardPermission`

Defines access levels for the `dashboard_access` join table.

```python
class DashboardPermission(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    ADMIN = "admin"
```

| Value   | Description                                      |
| ------- | ------------------------------------------------ |
| `view`  | Read-only access to dashboard data               |
| `edit`  | Can upload data and modify processing configs    |
| `admin` | Full dashboard management                        |

**PostgreSQL ENUM:** `dashboard_permission_level`
**Table:** `dashboard_access.permission`

`read` and `write` are **rejected at the boundary, not normalised**: the API
body model declares ``permission`` as ``DashboardPermission``, so a value
outside ``view``/``edit``/``admin`` fails validation (422) before any handler
runs, and the service never rewrites one spelling into another. The stored
labels are exactly the three above.

---

### 3. `GraphType`

Defines supported chart types.

```python
class GraphType(StrEnum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    TABLE = "table"
```

| Value    | Plotly Equivalent                                |
| -------- | ------------------------------------------------ |
| `bar`    | `plotly.graph_objects.Bar`                       |
| `line`   | `plotly.graph_objects.Scatter` (mode=lines)      |
| `pie`    | `plotly.graph_objects.Pie`                       |
| `table`  | HTML `<table>`                                   |

**PostgreSQL ENUM:** `graph_type`
**Table:** `graphs.type`

---

### 4. `FilterType`

Defines filter UI control types.

```python
class FilterType(StrEnum):
    SELECT = "select"
    MULTISELECT = "multiselect"
    RANGE = "range"
    DATE = "date"
```

| Value         | UI Control       |
| ------------- | ---------------- |
| `select`      | Dropdown         |
| `multiselect` | Multi-select     |
| `range`       | Range slider     |
| `date`        | Date picker      |

**PostgreSQL ENUM:** `filter_type`
**Table:** `filters.type`

---

### 5. `RegistrationStatus`

Defines the lifecycle of registration requests.

```python
class RegistrationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
```

| Value      | Description                                  |
| ---------- | -------------------------------------------- |
| `pending`  | Awaiting admin review                        |
| `approved` | User account created with temp password      |
| `rejected` | Request denied                               |

**PostgreSQL ENUM:** `registration_status`
**Table:** `registration_requests.status`

---

### 6. `UploadMode`

Defines data upload behavior.

```python
class UploadMode(StrEnum):
    OVERWRITE = "overwrite"
    APPEND = "append"
```

| Value       | Description                                  |
| ----------- | -------------------------------------------- |
| `overwrite` | Replace all existing data for the dashboard  |
| `append`    | Add new data to existing records             |

**Not a PostgreSQL ENUM** — used as an API query parameter.

---

### 7. `ProcessingStatus`

Defines the lifecycle of data processing tasks.

```python
class ProcessingStatus(StrEnum):
    STARTED = "started"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    COMPLETED = "completed"
```

| Value        | Description                              |
| ------------ | ---------------------------------------- |
| `started`    | Processing task created                  |
| `uploaded`   | File uploaded to temporary storage       |
| `processing` | Data being parsed and aggregated         |
| `success`    | Processing completed successfully        |
| `failed`     | Processing encountered an error          |
| `completed`  | Final state after success (post-processing) |

**PostgreSQL ENUM:** `processing_status`
**Table:** `processing_logs.status`

---

### 8. `EnvironmentEnum`

Defines application deployment environments.

```python
class EnvironmentEnum(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TEST = "test"
```

**Not a PostgreSQL ENUM** — used for configuration and feature flags.

---

### 9. `MimeTypeEnum`

Defines allowed MIME types for file uploads.

```python
class MimeTypeEnum(StrEnum):
    TEXT_CSV = "text/csv"
    APPLICATION_GZIP = "application/gzip"
    APPLICATION_X_GZIP = "application/x-gzip"
```

**Not a PostgreSQL ENUM** — used for upload validation.

---

### 10. `FileExtensionEnum`

Defines allowed file extensions for upload.

```python
class FileExtensionEnum(StrEnum):
    CSV = "csv"
    CSV_GZ = "csv.gz"
```

**Not a PostgreSQL ENUM** — used for upload validation.

---

### 11. `AggregationFunctionEnum`

Defines data aggregation functions for processing.

```python
class AggregationFunctionEnum(StrEnum):
    SUM = "sum"
    MEAN = "mean"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    STD = "std"
    VAR = "var"
    FIRST = "first"
    LAST = "last"
```

**Not a PostgreSQL ENUM** — used in processing configuration (JSONB).

---

### 12. `FilterOperatorEnum`

Defines filter comparison operators.

```python
class FilterOperatorEnum(StrEnum):
    EQ = "=="
    NE = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
```

**Not a PostgreSQL ENUM** — used in filter logic.

---

### 13. `OrientationEnum`

Defines chart bar orientation.

```python
class OrientationEnum(StrEnum):
    VERTICAL = "v"
    HORIZONTAL = "h"
```

**Not a PostgreSQL ENUM** — stored in graph `config` JSONB.

---

### 14. `BarmodeEnum`

Defines bar chart display mode.

```python
class BarmodeEnum(StrEnum):
    GROUP = "group"
    STACK = "stack"
```

**Not a PostgreSQL ENUM** — stored in graph `config` JSONB.

---

### 15. `YoyModeEnum`

Defines year-over-year comparison display mode.

```python
class YoyModeEnum(StrEnum):
    ABSOLUTE = "absolute"
    PERCENT = "percent"
```

**Not a PostgreSQL ENUM** — stored in graph `config` JSONB.

---

### 16. `ButtonVariant`

Defines button style variants for UI components.

```python
class ButtonVariant(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    INFO = "info"
    LIGHT = "light"
    DARK = "dark"
```

**Not a PostgreSQL ENUM** — declared in `src/mkobi/models/enums.py` as the shared vocabulary for dashboard layout presentation, and **not enforced by the server**: `layouts.definition` is unconstrained `JSONB` and `LayoutService.create_layout` performs no variant check, so a definition carrying an unknown variant is stored unchanged. Server-side validation of layout definitions is a stated intent, not an implemented capability, and the accepted shape of a valid definition is undecided. The values match the frontend's button-styling vocabulary; the frontend declares its own literals and does not import this enum.

---

### 17. `ComponentSize`

Defines component size variants for UI elements.

```python
class ComponentSize(StrEnum):
    SMALL = "sm"
    MEDIUM = "md"
    LARGE = "lg"
```

**Not a PostgreSQL ENUM** — declared in `src/mkobi/models/enums.py` as the shared vocabulary for dashboard layout presentation, and **not enforced by the server**: `layouts.definition` is unconstrained `JSONB` and `LayoutService.create_layout` performs no size check, so a definition carrying an unknown size is stored unchanged. Server-side validation of layout definitions is a stated intent, not an implemented capability, and the accepted shape of a valid definition is undecided. The values match the frontend's component-sizing vocabulary; the frontend declares its own literals and does not import this enum.

---

## PostgreSQL ENUM Types

The following 5 StrEnum classes have corresponding PostgreSQL ENUM types:

| PostgreSQL ENUM Type          | StrEnum Class        | Values                                          |
| ----------------------------- | -------------------- | ----------------------------------------------- |
| `user_role`                   | `UserRole`           | `admin`, `editor`, `viewer`                     |
| `dashboard_permission_level`  | `DashboardPermission`| `view`, `edit`, `admin`                         |
| `graph_type`                  | `GraphType`          | `bar`, `line`, `pie`, `table`                   |
| `filter_type`                 | `FilterType`         | `select`, `multiselect`, `range`, `date`        |
| `processing_status`           | `ProcessingStatus`   | `started`, `uploaded`, `processing`, `success`, `failed`, `completed` |
| `registration_status`         | `RegistrationStatus` | `pending`, `approved`, `rejected`               |

**Note:** PostgreSQL ENUM types are created in the initial migration using `checkfirst=True` for idempotency:
```python
user_role_enum = ENUM('admin', 'editor', 'viewer', name='user_role')
user_role_enum.create(op.get_bind(), checkfirst=True)
```

---

## Cross-References

- [Core Schema](./schema-core.md) — Tables using ENUM types
- [Processing Schema](./schema-processing.md) — Processing-related ENUM types
- [Access Schema](./schema-access.md) — Access-related ENUM types
- [Indexes](./indexes.md) — Index definitions
- [Source Code](src/mkobi/models/enums.py) — StrEnum implementation
- [Dashboards API](../02-dashboards/dashboards-api.md) — `GraphType`, `FilterType` usage in API
- [Processing API](../03-processing/processing-api.md) — `ProcessingStatus`, `UploadMode` usage in API
- [Access Control](../08-security/access-control.md) — `UserRole`, `DashboardPermission` in access model
