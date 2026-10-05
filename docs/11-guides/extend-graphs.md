---
id: extend-graphs
domain: guides
tags:
  - guide
  - graphs
  - extensibility
  - charts
  - howto
related:
  - dashboards-api
  - processing-api
  - schema-core
  - data-flow
  - extend-filters
  - create-dashboard
---

## Purpose

This guide walks developers through the process of adding new graph types in the mkobi BI Dashboard System. It covers the full extension workflow — from backend StrEnum changes to frontend `ChartRenderer` wiring — for graph types such as scatter, heatmap, or any custom Plotly trace. It also states which `config` keys are actually **consumed** and which are **reserved**, because that distinction decides whether a stored key does anything. It assumes you have read the [Dashboards API](../02-dashboards/dashboards-api.md) and [SPEC.md](../SPEC.md) overview.

For the wire contract the renderer reads — the served measure and dimension names — see [Processing API → Served measure and dimension names](../03-processing/processing-api.md#served-measure-and-dimension-names). For filter extension, see the companion guide: [Extend Filters](./extend-filters.md).

## Prerequisites

To follow this guide, you should:

- Be familiar with the codebase structure (FastAPI backend, React + TypeScript frontend, Polars data processing)
- Understand the Clean Architecture layers (API → Service → Repository) and Feature-Sliced Design on the frontend
- Have read the [Dashboards API](../02-dashboards/dashboards-api.md) reference for field-level detail on graph config structures
- Have read the [Core Schema](../09-database/schema-core.md) documentation for the `graphs` table structure

## Quick Reference

The following table maps the current graph types to their backend enum values, frontend components, and Plotly trace types:

| Graph Type | Backend (`GraphType`) | Frontend Component | Plotly Trace Type | Data Shape |
| ---------- | --------------------- | ------------------ | ----------------- | ---------- |
| Bar        | `bar`                 | `PlotlyChart`      | `bar`             | GROUP BY   |
| Line       | `line`                | `LineChart.tsx`    | `scatter` (mode: lines) | GROUP BY |
| Pie        | `pie`                 | `PlotlyChart`      | `pie`             | GROUP BY   |
| Table      | `table`               | `TableChart.tsx`   | *(none, HTML table)* | Flat rows |

> There is **no `BarChart.tsx`** and no `PieChart.tsx`. Both types render through
> `PlotlyChart`; `ChartRenderer` builds their traces. A fourth entry here would point
> a reader at a component that does not exist.

## No graph-editing UI exists

**Every graph reference in `frontend/src/` is a read.** There is no create, update or
delete call against `/api/v1/graphs/` or `/api/v1/dashboards/{id}/graphs` anywhere in the
frontend, and the admin panel's only dashboard surface (`DashboardManagement.tsx`)
contains no graph or filter editor at all.

The graph `config` vocabulary below is therefore a **server-side contract**, not a form:

- a `config` reaches the database through `POST /api/v1/graphs/`,
  `PUT /api/v1/graphs/{id}` or `POST /api/v1/dashboards/{id}/graphs` — an HTTP client,
  the seeders, or a direct write. **Not** the product's UI.
- this document's steps that assume a settings screen (a graph-type selector form, an
  admin field) describe work that has **no surface to happen on**. They are written as
  code steps for that reason.

This is the honest consequence of the rule that adjudicated the vocabulary: which keys
are honoured is decided by what reads them, and with no writer in the product a
reserved key has no producer as well as no consumer.

## Conceptual Overview

The graph extension system follows this end-to-end pipeline:

```
Backend StrEnum (Python)
    │
    ▼
PostgreSQL ENUM type (DB-level validation)
    │
    ▼
JSONB config stored in `graphs` table
    │
    ▼
API response serialized to frontend
    │
    ▼
Frontend TypeScript const object (mirrors backend enum)
    │
    ▼
ChartRenderer converts flat merged records → Plotly traces
```

**Key design principle:** `GraphType` uses Python `StrEnum`, where the enum value is a plain string (e.g., `"bar"`). These strings are stored in PostgreSQL `ENUM` types, which means adding a new type requires both a code change (the StrEnum) and a database migration (`ALTER TYPE ... ADD VALUE`). On the frontend, a `const` object with `as const` assertion mirrors the backend enum to maintain type safety without runtime overhead.

**Chart data sorting:** The `AggregationService` applies automatic sorting after GROUP BY: (1) X-axis sorted chronologically using `year`/`month` columns when available, otherwise by the X dimension directly; (2) Color dimension (brands/categories) sorted by total metric volume (descending) so larger values appear first in stacked bar charts. This ensures consistent visualization without manual trace ordering in the frontend. For Plotly stacked bars, the first trace appears at the bottom of the stack, so descending color totals places larger aggregations at the bottom where they are more visible.

**How ChartRenderer works:** The backend does NOT construct Plotly trace data. `AggregationService` produces flat records with `{dims: {...}, metrics: {...}}` and stores them in the `aggregated_data` table. On read, `DataService` merges each record into **one flat dict** (`{**dims, **metrics}`) and the response serves it in `GraphDataResponse.data` **together with the column names actually present on those rows**, in `metrics` and `dimensions`. `ChartRenderer` reads those served names — never the graph's `config` — to decide which column is the measure, the axis and the colour. If data already arrives in Plotly format (has `x` and `y` fields on the first record) and no colour column resolves, it passes through as-is.

Each trace is built by a **per-type builder** (`makeBarTrace`, `makeLineTrace`,
`makePieTrace`), because each Plotly trace type declares a different member set: a
`PieData` declares no top-level `x`/`y`, so a pie built from `x`/`y` renders with no
slices.

## The config vocabulary

`config` is a **closed declared set of fifteen keys**. The refusal set is computed once
from the `GraphConfigDict` TypedDict's own annotations, so it cannot drift from the
declared vocabulary. **An undeclared key is refused by name** at the request boundary
(`422`, naming the key) on `POST /graphs/`, `PUT /graphs/{id}` and
`POST /dashboards/{id}/graphs`.

### Consumed keys

| Key | Read by | Effect |
| --- | ------- | ------ |
| `x` | `ChartRenderer` | The axis column, **if it is among the served `dimensions`** |
| `color` | `ChartRenderer` | The grouping column, **if it is among the served `dimensions`** |
| `metrics` | `ChartRenderer` / `chartStates` | `metrics[0]` is the measure column, **if it is among the served `metrics`** |
| `orientation` | `ChartRenderer` | Bar trace orientation, `"v"` (default) or `"h"` |
| `barmode` | `ChartRenderer` | Bar grouping mode; defaults to `group` |
| `y` | — | Names the column the renderer's `config.metrics?.[0] ?? 'y'` fallback falls back to. Not read directly |
| `layout` | `api/routes/data.py` → `GraphDataResponse.layout` | Served to the client as stored and read by `ChartRenderer::convertChartLayoutToPlotly` |

### Config-level twins, not lifted

`title` and `showlegend` are the config-level twins of `ChartLayoutConfig.title` and
`ChartLayoutConfig.showlegend`. The renderer reads the **layout** field off the
response, not these keys, and they are **not** lifted into `layout` either. Writing
`config.title` therefore has no effect on the rendered chart; write
`config.layout.title`.

### Reserved keys

Six keys are **RESERVED**: validated at the request boundary, stored and returned on
read, and read by **nothing** in `src/` or `frontend/src/`:

| Key | Why it is kept |
| --- | -------------- |
| `yoy` | Year-over-year comparison. No consumer |
| `secondary_y` | Secondary measure axis. No consumer |
| `xaxis` | Axis config at the config level. **Deliberately unwired** |
| `yaxis` | Axis config at the config level. **Deliberately unwired** |
| `sort_x` | X-axis sorting. No consumer |
| `sort_color` | Colour-value sorting. No consumer |

They are deliberately neither deleted nor silently ignored. A **declared** key means the
boundary accepts it, not that anything reads it.

`xaxis` and `yaxis` are a distinct sub-case: they are reserved **and deliberately not
wired**, because the renderer reads axis configuration from the **served `layout` field
only** and nothing in this repository can write a config-level axis. Lifting them into
`layout` would create a second naming path for the same value with no producer.

### The axis and measure rules, stated correctly

The axis is **not** "the first dimension column" and the measure is **not** "the first
metric column" unconditionally. Both resolve through one rule: a configured name wins
if it is among the served names; an absent or empty served list is no authority; then
each role falls back.

| Role | Resolution order | Fallback when unresolved |
| ---- | ---------------- | ------------------------ |
| Axis (`x`) | `config.x` if served | first served dimension, then the literal `'x'` |
| Measure (`y`) | `config.metrics[0]` if served | first served metric |
| Colour (`color`) | `config.color` if among served dimensions | **no grouping** — never a guessed dimension |

A **bar chart's axis type is `'category'`** unless a stored layout supplies one. The
renderer writes that default first and spreads the converted layout axis after it, so a
layout that omits `type` leaves `'category'` in place.

### How served names came about

An operator writes the **pre-alias** name — `"revenue"` — while the stored rows are keyed
**post-alias**, `revenue_mean`, because the aggregation aliases every aggregate as
`{column}_{function}`. The configured name is also mutable without a re-upload: changing
`metric_agg` rewrites the alias on the next upload without touching the stored rows in
between. Reading served names off the rows removes both the guess and the duplication;
deriving them from `config` would have re-introduced the suffix rule the client must not
apply.

`config.metrics` therefore remains the operator's **input**, and the response's top-level
`metrics` is the **served key set**. They routinely differ, and that difference is the
point.

## Extending Graph Types

### Step 1: Add the Value to `GraphType` StrEnum

Edit `src/mkobi/models/enums.py` and add the new value to the `GraphType` class:

```python
class GraphType(StrEnum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    TABLE = "table"
    SCATTER = "scatter"   # <-- new value
```

The string value (`"scatter"`) must exactly match the value used in the frontend TypeScript enum and the PostgreSQL ENUM type. Use lowercase kebab-case consistently.

### Step 2: Add a Database Migration

Since graph types are enforced at the database level via a PostgreSQL `ENUM` type named `graph_type`, you must add the new value with an `ALTER TYPE` statement in an Alembic migration:

```python
# alembic/versions/XXXX_add_scatter_graph_type.py
def upgrade():
    op.execute("ALTER TYPE graph_type ADD VALUE 'scatter'")

def downgrade():
    # PostgreSQL does not support removing ENUM values directly.
    # A downgrade requires recreating the type or leaving the value in place.
    pass
```

**Critical:** Without this migration, the backend will accept the new enum value but every database `INSERT` or `UPDATE` using it will fail with an invalid enum literal error.

### Step 3: Add the Frontend Enum Value

Edit `frontend/src/shared/types/enums.ts` and add the new value to the `GraphType` const object:

```typescript
export const GraphType = {
  BAR: 'bar',
  LINE: 'line',
  PIE: 'pie',
  TABLE: 'table',
  SCATTER: 'scatter',
} as const

export type GraphType = (typeof GraphType)[keyof typeof GraphType]
```

Ensure the string value matches the backend exactly. A casing mismatch makes the request fail validation at the boundary.

### Step 4: Update ChartRenderer for the New Type

The `ChartRenderer` component (`frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx`) converts flat merged records into Plotly `Data[]`. Its `traceTypeFor()` maps a graph type to one of `pie`, `scatter` or `bar`, and `makeTrace()` dispatches to the per-type builder whose Plotly type declares that payload. A new type therefore needs both a mapping in `traceTypeFor()` and — if the shape differs — a builder, because a trace built from the wrong member set renders blank.

```typescript
// traceTypeFor: add the mapping
if (graphType === 'scatter') return 'scatter'

// chartConversion.ts: a builder that writes through the Partial whose
// Plotly type declares every member it sets
function makeScatterTrace(xVals: ChartLabel[], yVals: ChartMeasure[]): Partial<PlotData> {
  return { x: xVals, y: yVals, type: 'scatter', mode: 'markers' }
}
```

Do **not** read columns off `graph.data` by a hard-coded name. Read them off the served
`graph.metrics` / `graph.dimensions` lists, or reuse `resolveColumnName` /
`resolveMeasureColumn` — a hard-coded name is exactly the guess that served names
replaced.

If your new type can reuse the existing conversion logic (e.g. a horizontal bar chart
using `orientation: 'h'`), you may only need to store that orientation in the graph's
`config` JSON — no `ChartRenderer` change required.

### Step 5: Create a Standalone Chart Component (Optional)

If the new graph type needs its own reusable component (for direct use elsewhere in the
app), create one under `frontend/src/features/dashboards/ui/charts/`:

```typescript
// frontend/src/features/dashboards/ui/charts/ScatterChart.tsx
import { PlotlyChart } from './PlotlyChart'
import type { ChartLayoutConfig } from '../../../../shared/types/api.types'
import type { Data, Layout } from 'react-plotly.js'

interface ScatterChartProps {
  data: Data[]
  layout?: ChartLayoutConfig
}

export function ScatterChart({ data, layout }: ScatterChartProps) {
  const plotLayout: Partial<Layout> = {}
  if (layout?.title !== undefined) plotLayout.title = { text: layout.title }
  return <PlotlyChart data={data} layout={plotLayout} />
}
```

`PlotlyData` / `PlotlyLayout` are **not** exported from `api.types.ts`; the Plotly
types come from `react-plotly.js`, and the server's `ChartLayoutConfig` is the shared
layout vocabulary. `convertChartLayoutToPlotly` in `ChartRenderer.tsx` is the canonical
`ChartLayoutConfig` → `Layout` conversion — reuse it rather than re-deriving it.

Note that a type mapping alone is enough for `bar`, `line`, `pie` and `table`. A
standalone component is for a type whose **default trace properties** differ, not for
merely naming the type.

### Step 6: There is no admin form to update

**No graph-editing UI exists anywhere in the product.** There is no graph-type selector
in the admin panel, and no admin screen writes a graph `config`. Nothing in this step
can be done, and nothing here should be written as though it could.

A new graph type therefore becomes selectable only by a **client** of the API — an HTTP
call to `POST /api/v1/graphs/` or `POST /api/v1/dashboards/{id}/graphs`, the seeders, or
a direct database write. If the product later grows a graph editor, the frontend
`GraphType` const object from Step 3 is what that form must reference.

## Data Pipeline Implications

The aggregation pipeline in `AggregationService` produces flat records with `{dims: {dimension_name: value}, metrics: {metric_name: value}}` for each graph. The GROUP BY columns are `graph.dimensions + dashboard.filter.names` (filter names from bound dashboard filters). All dimension values are converted to strings.

**Graph types that work with existing conversion:**
Bar, line, and pie all share one conversion path: `convertToPlotlyData()` resolves the
axis from `config.x` against the served `dimensions` (else the first served dimension)
and the measure from `config.metrics[0]` against the served `metrics` (else the first
served metric), then dispatches to the per-type builder. **Neither role is
unconditionally "the first column"** — the configured name wins whenever it resolves. If
your new type uses the same data shape with different Plotly trace properties, add a
`traceTypeFor()` mapping and a builder.

**Graph types that need raw row access:**
Table charts display flat records directly, without any Plotly conversion, and they draw
no gap for an absent cell — they print an em dash. If your new graph type needs
row-level data (e.g. a scatter whose x and y come from different **served metric**
columns), resolve both names from `graph.metrics` rather than from `config`, and draw an
explicit `null` for an absent value rather than coercing it to `0` — a coerced zero is
indistinguishable from a real zero.

**Summary:** The aggregation pipeline's output (flat `{dims, metrics}` records) is the single source of truth, and the **served column names** shipped beside them are the client's index into it. New graph types add *conversion functions* in `ChartRenderer` that transform this output into different Plotly trace shapes. You rarely need to modify the aggregation itself.

## Appendix

### Example 1: Adding a Scatter Graph Type (Simple)

This example adds a `"scatter"` graph type that renders individual data points. The scatter plot uses two **served** metric columns.

**1. Backend StrEnum** (`src/mkobi/models/enums.py`):

```python
class GraphType(StrEnum):
    # ... existing values
    SCATTER = "scatter"
```

**2. Database migration** (`alembic/versions/XXXX_add_scatter.py`):

```python
"""Add scatter to graph_type enum."""

revision = "XXXX"
down_revision = "YYYY"

def upgrade():
    op.execute("ALTER TYPE graph_type ADD VALUE 'scatter'")

def downgrade():
    pass  # PostgreSQL does not support removing ENUM values
```

**3. Frontend enum** (`frontend/src/shared/types/enums.ts`):

```typescript
export const GraphType = {
  // ... existing values
  SCATTER: 'scatter',
} as const
```

**4. Trace mapping and builder** (`ChartRenderer.tsx` + `chartConversion.ts`):

```typescript
// traceTypeFor
if (graphType === 'scatter') return 'scatter'

// chartConversion.ts — read the columns off the SERVED names
const xCol = graph.metrics?.[0]
const yCol = graph.metrics?.[1]
const xs = collectSeries(graph.data, xCol, 'x')   // ChartLabel[]
const ys = collectSeries(graph.data, yCol, 'y')   // ChartMeasure[], null = gap
return [makeScatterTrace(xs, ys)]
```

**5. Backend data construction** — No changes needed. `AggregationService` already
produces flat `{dims, metrics}` records, and `GET /data/aggregated` already serves the
column names those rows carry in `metrics` / `dimensions`. Two metrics is the case that
requires a **new** step: with one served metric the standard path already works.

### Example 2: Adding a Heatmap Graph Type (Medium Complexity)

Heatmaps require a 2D matrix of values and two dimension axes. The data shape differs from bar/line/pie graphs because it needs cross-tabulated aggregates.

**1–3. StrEnum + migration + frontend enum** — Same pattern as Example 1 (`HEATMAP = "heatmap"`).

**4. Trace builder** — Heatmaps need a pivoted data shape. Add a builder that produces `z` (2D value matrix), `x` (column dimension values), and `y` (row dimension values):

```typescript
function makeHeatmapTrace(xLabels: ChartLabel[], yLabels: ChartLabel[], z: (number | null)[][]): Partial<PlotData> {
  return { x: xLabels, y: yLabels, z, type: 'heatmap' }
}
```

Resolve the two axis dimensions from `graph.dimensions` (the served list) — not from
`config.x`, and not by position without checking the served names.

**5. Backend data construction** — If the heatmap requires a different aggregation shape, add a construction function in `AggregationService` that produces pre-pivoted records. The default GROUP BY produces flat records; heatmaps need an additional pivot step.

## Cross-Links

- [Dashboards API](../02-dashboards/dashboards-api.md) — CRUD for dashboards, graphs, filters, and access management; field-level detail on graph config JSONB structures
- [Processing API](../03-processing/processing-api.md#served-measure-and-dimension-names) — Upload and processing pipeline, plus the served `metrics` / `dimensions` / `layout` contract this guide's renderer consumes
- [Core Schema](../09-database/schema-core.md) — Table definitions for `graphs` table, including PostgreSQL ENUM types and JSONB columns
- [Processing Schema](../09-database/schema-processing.md) — Table definitions for `aggregated_data`, `processing_configs`, and `processing_logs`
- [Data Flow](../00-overview/data-flow.md) — End-to-end upload-to-display pipeline
- [UI Pages](../07-frontend/pages.md) — The four dashboard render states this guide's traces feed
- [Extend Filters](./extend-filters.md) — How to add new filter types (companion guide)
- [Create Dashboard](./create-dashboard.md) — Step-by-step guide for creating a new dashboard from scratch
