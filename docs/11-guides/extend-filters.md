---
id: extend-filters
domain: guides
tags:
  - guide
  - filters
  - extensibility
  - howto
related:
  - dashboards-api
  - processing-api
  - schema-core
  - data-flow
  - extend-graphs
  - create-dashboard
---

## Purpose

This guide walks developers through the process of extending filter capabilities in the mkobi BI Dashboard System. It covers the full extension workflow — from backend StrEnum changes to frontend `FilterField` wiring — for filter types such as search, toggle, or any custom MUI control. It assumes you have read the [Dashboards API](../02-dashboards/dashboards-api.md) and [SPEC.md](../SPEC.md) overview.

For graph extension, see the companion guide: [Extend Graphs](./extend-graphs.md).

> **This file is the single source of truth for filter extension.** A former
> `extend-graphs-filters.md` covered the same two subjects as a partial copy of this
> file and `extend-graphs.md`; it was removed so that one subject has one home.

## Prerequisites

To follow this guide, you should:

- Be familiar with the codebase structure (FastAPI backend, React + TypeScript frontend, Polars data processing)
- Understand the Clean Architecture layers (API → Service → Repository) and Feature-Sliced Design on the frontend
- Have read the [Dashboards API](../02-dashboards/dashboards-api.md) reference for field-level detail on filter config structures
- Have read the [Core Schema](../09-database/schema-core.md) documentation for the `filters` table structure

## Quick Reference

The following table maps the current filter types to their backend enum values, MUI controls, and value sources:

| Filter Type | Backend (`FilterType`) | Evaluable (`EvaluableFilterType`) | MUI Control | Value Source |
| ----------- | ---------------------- | --------------------------------- | ----------- | ------------ |
| Select      | `select`               | yes                              | `Select` dropdown | `config.options` (static) or `source: "data"` (dynamic from `dashboard_filter_values` table) |
| Multiselect | `multiselect`         | yes                              | `Select multiple` + `Chip` | Same as select |
| Date        | `date`                 | yes                              | `TextField` type=date | Single date string |
| ~~Range~~   | `range` (**retired**)  | **no**                           | **none — no control is rendered** | — |

**The `range` row is retired, not caveated.** See
[`range` is retired](#range-is-retired) below for the whole statement.

## `range` is retired

There is **no** range filter control, and no range filter evaluation. Concretely:

| Surface | Behaviour |
| ------- | --------- |
| Filters panel | No control. A stored `range` filter renders a **non-blocking warning inside the panel** and **sends no value**. The dashboard is **not** blanked, and this is **not** an empty state |
| `POST /api/v1/dashboards/`, `PUT /api/v1/dashboards/{id}` | `422` naming the offending **field** and the supported set (`select`, `multiselect`, `date`). Enforced by `EvaluableFilterType` in `src/mkobi/models/dashboard.py` |
| `GET /api/v1/data/aggregated` | `422` naming the **filter** and its **reason**, with `{filter, declared_type, reason}` in RFC 7807 `details`. Enforced by `DataService.validate_filter_values`, whatever the value's shape — a scalar on a range-declared filter is meaningless too |
| `FilterType.RANGE` enum member | **Still exists, and is inert.** The label's removal and the migration of stored rows are deferred to phase 14 (`C14-17`) |
| `filter_type` PostgreSQL label | **Still exists.** The column still accepts `'range'` — the retirement is in the evaluation, not in the schema |

The `FilterType` / `EvaluableFilterType` split is the reason a single table cannot answer
this question. `FilterType` is the **storage** vocabulary (what a column may hold, backed
by a live PostgreSQL enum whose labels are inert); `EvaluableFilterType` is the **closed
set of declared types a submitted filter value can be evaluated against**. Aliasing them
would make the storage enum authoritative over evaluability and recreate the defect.

### Adding a type back, or adding a new one, to the evaluable set

A new filter type is only evaluable once **three** declarations agree:

1. `FilterType` — the storage enum, plus an `ALTER TYPE filter_type ADD VALUE` migration.
2. `EvaluableFilterType` — the write-boundary vocabulary. Omitting it makes the type
   storable through a direct write but **un-saveable** through the API.
3. `DataService.validate_filter_values` — the admissibility rule. A `list` is refused by
   name on every key not declared `multiselect`; a `range`-declared key is refused by
   name unconditionally.

Omitting (3) is the dangerous half: a declared type with no evaluation rule falls
through the rule as *permitted*, and the repository then compares the value as text.
That is a silent wrong answer, not an error.

## Conceptual Overview

The filter extension system follows this end-to-end pipeline:

```
Backend StrEnum (Python)
    │
    ▼
PostgreSQL ENUM type (DB-level validation)
    │
    ▼
JSONB config stored in `filters` table
    │
    ▼
API response serialized to frontend
    │
    ▼
Frontend TypeScript const object (mirrors backend enum)
    │
    ▼
FilterField switch dispatches to MUI control
```

**Key design principle:** `FilterType` uses Python `StrEnum`, where the enum value is a plain string (e.g., `"select"`). These strings are stored in PostgreSQL `ENUM` types, which means adding a new type requires both a code change (the StrEnum) and a database migration (`ALTER TYPE ... ADD VALUE`). On the frontend, a `const` object with `as const` assertion mirrors the backend enum to maintain type safety without runtime overhead.

**How DashboardFilters works:** The `DashboardFilters` component uses an explicit `switch (filter.type)` statement in the `FilterField` subcomponent. Each filter type maps to a specific MUI control. **An unhandled type does not render `null` — it renders a warning alert** naming the filter and its declared type, inside the panel. Silence is the same "does nothing" defect as a dead control, so the panel says so instead. Filter values are fetched dynamically from `GET /api/v1/dashboards/{id}/filter-values` when `config.source === "data"`, or from static `config.options` when `config.source === "dims"`.

**Filter-value caching.** The option list is a function of the uploaded file, so it
changes only on upload and nothing else produces change. It is therefore cached with
`staleTime: Infinity` for the process lifetime and **explicitly invalidated when an
upload completes**, together with the aggregated data. The pin is on that query alone —
a global `Infinity` would silently disable background refetching for every query in the
application. Every other query keeps its existing refetch behaviour.

## Extending Filter Types

### Step 1: Add the Value to `FilterType` StrEnum

Edit `src/mkobi/models/enums.py` and add the new value to the `FilterType` class:

```python
class FilterType(StrEnum):
    SELECT = "select"
    MULTISELECT = "multiselect"
    RANGE = "range"        # retired and inert; kept until phase 14 (C14-17)
    DATE = "date"
    SEARCH = "search"      # <-- new value
```

### Step 2: Add a Database Migration

Add an Alembic migration for the `filter_type` PostgreSQL ENUM:

```python
def upgrade():
    op.execute("ALTER TYPE filter_type ADD VALUE 'search'")
```

### Step 3: Add the Frontend Enum Value

Edit `frontend/src/shared/types/enums.ts`:

```typescript
export const FilterType = {
  SELECT: 'select',
  MULTISELECT: 'multiselect',
  RANGE: 'range',
  DATE: 'date',
  SEARCH: 'search',
} as const

export type FilterType = (typeof FilterType)[keyof typeof FilterType]
```

### Step 4: Add the Filter Field Case in `DashboardFilters`

Edit `frontend/src/features/dashboards/ui/DashboardFilters.tsx` and add a new `case` in the `FilterField` switch statement:

```typescript
case 'search':
  return (
    <TextField
      fullWidth
      size="small"
      label={filter.name}
      value={(value as string) || ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={`Search ${filter.name}...`}
    />
  )
```

**A missing case is now visible, not silent.** The `default` branch renders a warning
alert naming the filter and its declared type, so an unhandled type is reported rather
than ignored. It still needs adding — the alert is a diagnostic, not a control.

### Step 5: Declare the type evaluable, and write its evaluation

This is the step the storage enum alone does not cover. Two edits:

1. Add the value to `EvaluableFilterType` in `src/mkobi/models/dashboard.py`. Without
   it, the type is storable through a direct write but **refused on every dashboard
   save** with a `422` naming the field.
2. Add the evaluation in the aggregate query path. The current predicates are
   `AggregatedDataRepository._graph_filter_conditions`: a **scalar** becomes
   `dims ->> :key = :value`, and a **non-empty list** becomes `dims ->> :key IN (…)`
   over the same `->>` operator. An **empty list is skipped entirely** — it imposes no
   constraint, and it is deliberately not `IN ()`, which would blank every chart with no
   visible cause.

Note what the predicates do **not** use: they never emit `@>` (JSONB containment) and
never interpolate. `->>` extraction does not reach the `idx_aggregated_data_dims_gin`
index; the read is served by `idx_aggregated_data_dashboard_graph`. See
[Indexes](../09-database/indexes.md#4-idx_aggregated_data_dims_gin).

A substring search (the common `search` case) has no predicate today: it needs `ILIKE`
against the extracted text, which is a new operator on this path and needs its own
bound.

### Step 6: There is no admin form to update

**No filter-editing UI exists anywhere in the product.** The global filter CRUD routes
were removed as orphaned, and the admin panel's only dashboard surface contains no filter
editor. A filter row reaches the database through a seeder or a direct write — not
through the UI. Nothing in this step can be done; it is written as a code step so the gap
is not mistaken for an oversight.

## Data Pipeline Implications

Filter types do not affect the aggregation pipeline. They affect how users select dimension values to filter by. The key consideration is the `config.source` field:

- **`source: "dims"` (static):** Filter options are defined in the filter's `config.options` JSON array. No data pipeline changes needed.
- **`source: "data"` (dynamic):** Filter options are extracted from the `dashboard_filter_values` table after each upload. No code changes needed for new filter types — as long as the filter's `config.field` matches a dimension name in your data, dynamic values are populated automatically during CSV processing.

A new filter type that introduces **no new evaluation** needs only the frontend
`FilterField` case. The backend handles every evaluable type uniformly through the
repository's per-key predicate and the admissibility rule.

## Appendix

### Example: Adding a Search Filter Type

This example adds a `"search"` filter type that provides a text input for free-text filtering of dimension values.

**1. Backend StrEnum** (`src/mkobi/models/enums.py`):

```python
class FilterType(StrEnum):
    # ... existing values
    SEARCH = "search"
```

**2. Database migration**:

```python
def upgrade():
    op.execute("ALTER TYPE filter_type ADD VALUE 'search'")
```

**3. Frontend enum** (`frontend/src/shared/types/enums.ts`):

```typescript
export const FilterType = {
  // ... existing values
  SEARCH: 'search',
} as const
```

**4. FilterField case** (`frontend/src/features/dashboards/ui/DashboardFilters.tsx`):

Add the search case to the `FilterField` switch statement:

```typescript
case 'search':
  return (
    <TextField
      fullWidth
      size="small"
      label={filter.name}
      value={(value as string) || ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={`Search ${filter.name}...`}
    />
  )
```

**5. Declare it evaluable** (`src/mkobi/models/dashboard.py`):

```python
class EvaluableFilterType(StrEnum):
    SELECT = "select"
    MULTISELECT = "multiselect"
    DATE = "date"
    SEARCH = "search"    # <-- required, or the type is refused on every save
```

**6. Backend handling** — The search filter needs a **new predicate**, not a variation of
the existing one: `ILIKE '%term%'` against the extracted dimension text, in
`_graph_filter_conditions`. It is not expressible as `->>` equality or `IN (…)`, and it
needs its own bound — a leading-wildcard predicate cannot use a B-tree index.

No changes to the aggregation pipeline are needed. The search filter operates on the
already-aggregated data, filtering rows where a dimension value contains the search term.

### The one thing this guide cannot close

A **retired type is not the same as a closed hole**, and this guide is where a reader is
most likely to assume otherwise. A filter value of two strings — `["0", "100"]` — is
**indistinguishable on the wire** from a legitimate two-value multiselect. A dashboard
that declares **no** filters at all, and receives such a value, is **permitted** and
matched as a membership test: an undeclared filter carries no type to discriminate with,
and no value union can, because the wire shape is identical.

That path is **unreachable from any input the application produces** (the range slider is
gone, so nothing emits a `number[]`), and it is **not covered for a non-browser client**.
It is recorded as a **bound**. See
[Processing API → Bound: the retired `range` type is not fully closed](../03-processing/processing-api.md#bound-the-retired-range-type-is-not-fully-closed).

## Cross-Links

- [Dashboards API](../02-dashboards/dashboards-api.md) — CRUD for dashboards, graphs, filters, and access management; field-level detail on filter config JSONB structures
- [Processing API](../03-processing/processing-api.md#filter-values-and-admissibility) — Upload and processing pipeline, plus the filter value and admissibility rule
- [Core Schema](../09-database/schema-core.md) — Table definitions for `filters` table, including PostgreSQL ENUM types and JSONB columns
- [Processing Schema](../09-database/schema-processing.md) — Table definitions for `aggregated_data`, `dashboard_filter_values`, `processing_configs`, and `processing_logs`
- [Database Enums](../09-database/enums.md#4-filtertype) — `FilterType` and the retired `range` label
- [Indexes](../09-database/indexes.md#4-idx_aggregated_data_dims_gin) — What the filter predicates do and do not reach
- [Data Flow](../00-overview/data-flow.md) — End-to-end upload-to-display pipeline
- [Extend Graphs](./extend-graphs.md) — How to add new graph types (companion guide)
- [Create Dashboard](./create-dashboard.md) — Step-by-step guide for creating a new dashboard from scratch
