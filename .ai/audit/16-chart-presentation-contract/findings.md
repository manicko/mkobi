---
phase: 16-chart-presentation-contract
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 10
by-severity:
  CRITICAL: 1
  HIGH: 6
  MEDIUM: 3
  LOW: 0
baseline: d008f555f5a2e1b3adb397c4bc67d95ed9c964c5
baseline-dirty: 68
---

# Phase 16 — Findings

## Summary

The presentation contract was traced from its declaration outward: from the `GraphConfigDict` TypedDict that decides which configuration keys exist, through the `GraphDataResponse` model that decides what a served figure carries, to `ChartRenderer.tsx` where the figure becomes a frame. Runtime confirmation came from the dev stack on `:8010` — a graph created through `POST /api/v1/graphs/` with a fully populated config — and from the repository's own interpreter. The single most consequential thing found is that a measure name has no path from configuration to frame: the renderer reads it only from `config.metrics` or the hard-coded literal `'y'`, `config.metrics` is not a member of the declaring TypedDict and is therefore stripped at request validation, and the serving tier names every stored measure `f"{metric}_{agg}"`, so `row['y']` is undefined on every row and `Number(undefined ?? 0)` yields 0. Every bar, line and pie figure in the product is drawn as a flat zero series while the same response carries the correct non-zero values — a complete-looking frame, a confident wrong number, and nothing on screen or in the payload to distinguish the two. The same strip also removes `orientation` and `barmode`, the two keys that would make a horizontal or stacked bar work, and the mechanism is a `total=False` TypedDict used as a Pydantic field type, which drops undeclared keys silently rather than reporting them.

## Findings

### CHT-001 — Every bar, line and pie figure is drawn from a measure column nothing can name, and renders as a flat zero series

**Severity** — CRITICAL

**Zone** — "Declared measures and dimensions: which are honoured, which are silently discarded, and which depend on a name the two tiers must agree on"

**Observation** — `convertToPlotlyData` (`frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:11-75`) resolves the measure column in exactly two ways: `config.metrics[0]` if `config.metrics` is present (line 17, then line 26), otherwise the hard-coded literal `'y'` (line 17). It then reads `row[metricCol]` and coerces with `Number(row[metricCol] ?? 0)` (lines 57 and 72). Both routes are dead ends.

`config.metrics` cannot be persisted. `GraphConfigDict` (`src/mkobi/models/types.py:138-152`) declares exactly `x, y, color, xaxis, yaxis, title, layout, yoy, secondary_y, sort_x, sort_color`. It is a `total=False` TypedDict used as the type of `GraphCreate.config` / `GraphUpdate.config` (`src/mkobi/models/graph.py:15,45`), so Pydantic silently drops any key it does not name. `metrics` is not among them.

The fallback literal `'y'` is a column name the serving tier never produces. `AggregationService.aggregate_graphs` (`src/mkobi/services/aggregation_service.py:92-94`) names every stored measure `f"{m}_{metric_agg}"` — `revenue_sum` — discarding any alias the processing config declared. The live path in `src/mkobi/data/processing/aggregate_transforms.py:131,135` uses `f"{column}_{func_str}"` for the same reason. Served rows are `{**record.dims, **record.metrics}` (`src/mkobi/services/data_service.py:216`), so the keys are dimension names plus `{metric}_{agg}`. `row['y']` is therefore `undefined` for every row, and `Number(undefined ?? 0)` is `0`.

The declarable spelling that would work — `config.y` — is read by nothing in the renderer. `convertToPlotlyData` consults `config.x`, `config.color`, `config.metrics`, `config.orientation` and (at line 149) `config.barmode`. `config.y` is not among them.

**Evidence** — Runtime, over HTTP against the dev stack on `:8010`. `POST /api/v1/graphs/` with

```json
"config": {"x":"region","y":"revenue","color":"category","metrics":["revenue","cost"],
           "orientation":"h","barmode":"stack", "...": "..."}
```

returned HTTP 201 with `"config"` reading back as
`{"x":"region","y":"revenue","color":"category","xaxis":{...},"yaxis":{...},"title":...,"layout":{...},"secondary_y":[...],"sort_x":{...}}` — `metrics`, `orientation` and `barmode` absent, with no error and no warning. The 201 response body is the same object the client will later receive from `/data/aggregated`, which copies `config` verbatim (`src/mkobi/api/routes/data.py:157,193`). Isolated confirmation of the strip: `GraphCreate(config={"metrics":["revenue"],"x":"region"}, …).config` evaluates to `{'x': 'region'}`.

**Consequence** — For every bar, line and pie graph in the product, `metricCol` resolves to `'y'`, `row['y']` is `undefined`, and each trace is built as a flat array of zeroes. The x-axis carries the real dimension values, so the frame is not blank and nothing on screen signals a fault: the reader sees correctly-labelled categories over a row of bars, a line or pie segments pinned at zero, while `/data/aggregated` is returning the correct non-zero measures in the same payload. A reader taking the height of any bar, the slope of any line or the proportion of any pie slice is acting on a confident wrong number. `graph.type === 'table'` is unaffected — `ChartRenderer.tsx:123-125` bypasses `convertToPlotlyData` and passes `graph.data` straight to `TableChart`, which is why the table view shows the real values on the same dashboard.

**Recommendation** — Give the measure name one declarable home and make the renderer read it. The smallest change that removes the effect without a storage migration: add `metrics: list[str] | None`, `orientation: str | None` and `barmode: str | None` to `GraphConfigDict` so the keys stop being stripped, and change `ChartRenderer.tsx:17,26` to read `config.y` (the key the tier already declares and stores) as the single-measure fallback, with `config.metrics[0]` honoured for multi-measure. Separately, stop discarding the aggregation alias at `src/mkobi/services/aggregation_service.py:93` so the stored name is one the configuration chose rather than a `_{agg}` suffix neither tier can predict; that is the name-derivation question phase 05 b4 owns, and this finding's remedy does not need it closed first, only the two tiers agreeing on one spelling. Direction of travel: have the serving tier state the stored measure names on `GraphDataResponse` (see CHT-003) rather than have the renderer guess them.

### CHT-002 — The bar branch overwrites the x-axis it just converted, dropping every configured x-axis setting

**Severity** — HIGH

**Zone** — "Per chart type: what the rendered figure is derived from, and what the declared type permits the renderer to discard"

**Observation** — `convertChartLayoutToPlotly` (`ChartRenderer.tsx:80-119`) converts a declared `ChartLayoutConfig` into a Plotly `Layout`, mapping `xaxis.title`, `xaxis.type` and `xaxis.range` (lines 89-95). The bar branch then builds its layout as

```tsx
const barLayout: Partial<Layout> = {
  ...convertedLayout,          // line 148
  barmode: (graph.config?.barmode || 'group'),   // line 149
  xaxis: { type: 'category' as const },          // line 150
}
```

`xaxis: { type: 'category' }` is written after the spread, so it replaces the whole converted `xaxis` object. The converted `title` and `range` are dropped and the converted `type` is overwritten with the constant. The `yaxis` written by the converter survives, because nothing writes `yaxis` after it. The `pie` branch (line 155) has no such write and keeps the converted `xaxis` intact — so the two Plotly-backed types disagree about the same declared field.

**Evidence** — Static proof over the two construction sites in the same function: `ChartRenderer.tsx:148-151` spreads `convertedLayout` at 148 and assigns a fresh `xaxis` literal at 150. The discarded values are computed at `ChartRenderer.tsx:90-94` and read by nothing after line 150. Reproduced on the same declaration the API accepts: `config.layout = {"xaxis":{"title":"Region","type":"category","range":[0,100]}}` is stored and served intact (CHT-001 readback shows `"layout":{"title":"Configured Layout Title","xaxis":{"title":"Region","range":[0.0,100.0],"type":"category"},...}`), so the value is present in the response and discarded in the frame.

**Consequence** — Every bar chart on every dashboard loses its configured x-axis title, its configured x-axis range and its configured x-axis scale type, while `plotly.min.js` draws a `category` axis with no title. The figure is complete-looking and wrong in exactly the one respect the configuration asked for, and the y-axis title the operator set beside it renders normally — so the chart reads as deliberately unlabelled on one axis rather than as a chart whose label was discarded. Pie charts configured the same way keep the title, which makes the loss look like a per-type difference in what the product supports.

**Recommendation** — In the bar branch, merge rather than replace: `xaxis: { type: 'category', ...convertedLayout?.xaxis }`, so the declared type still wins when the configuration sets one and the constant applies only when it does not. A second, cheaper option is to drop the forced `category` and let the declared `type` stand — that costs the default categorical axis for a bar chart configured with no `xaxis`, so prefer the merge. If the forced `category` is load-bearing for the bar renderer, say so in a comment on the same line, because the ordering is what makes the discard invisible on review.

### CHT-003 — The graph's own measure and dimension lists are never served, so the client has no declarable source for either

**Severity** — HIGH

**Zone** — "The declared presentation contract: which declared fields the served response never populates"

**Observation** — `Graph` carries `dimensions: list[str]` and `metrics: list[str]` (`src/mkobi/db/models/graphs.py:70-80`); both are required on create and update (`src/mkobi/models/graph.py:16-17,46-47`) and both are the arrays `AggregationService.aggregate_graphs` consumes to build the very rows the chart is drawn from (`src/mkobi/services/aggregation_service.py:69,74`). The response model for a served figure, `GraphDataResponse` (`src/mkobi/models/data.py:425-436`), declares `graph_id`, `type`, `name`, `data`, `layout` and `config` — and neither `metrics` nor `dimensions`. The route's two construction sites (`src/mkobi/api/routes/data.py:152-158` and `188-194`) populate only `graph_id`, `type`, `name`, `data` and `config`.

The client's mirror of the contract agrees: `GraphDataWithConfig` (`frontend/src/shared/types/api.types.ts:203-216`) has no `metrics` or `dimensions` member, so nothing in the browser tier looks for them either. The measure list the configuration declares is thus consumed entirely on the write side and never crosses the read boundary.

**Evidence** — Static: `GraphDataResponse` field set at `src/mkobi/models/data.py:431-436` against the two `GraphDataResponse(...)` call sites at `src/mkobi/api/routes/data.py:152-158` and `188-194`; neither passes `metrics` or `dimensions`, and the model has no default for them because it declares none. The response readback captured for CHT-001 contains keys `graph_id`, `type`, `name`, `data`, `config`, `layout` and no measure list.

**Consequence** — The renderer must rediscover a measure name that the server already knows, and its only candidates are the undeclared `config.metrics` and the literal `'y'` (CHT-001). The fix for CHT-001 can be made to work by adding `metrics` to `GraphConfigDict`, but the contract stays one-directional: the server states which measures it aggregated and the browser is told nothing, so a rename in the processing config, a `metric_agg` change from `sum` to `mean`, or a metric dropped for lack of a matching source column (`aggregation_service.py:77-81` skips the graph entirely in that case) is invisible to the frame until it produces zeros. This is the structural cause under CHT-001 and the reason that defect has no declarable repair.

**Recommendation** — Add `metrics: list[str]` and `dimensions: list[str]` to `GraphDataResponse`, populate both from `graph.metrics` / `graph.dimensions` at the two route call sites, and add the matching members to `GraphDataWithConfig`. Then have `convertToPlotlyData` derive its measure column from the served list instead of from `config.metrics` or `'y'`. This is a response-shape change, so it is the same commit as the CHT-001 fix rather than a follow-on — doing CHT-001 alone leaves the client still guessing.

### CHT-005 — `orientation` and `barmode` are read by the renderer and cannot be stored, so a stacked or horizontal bar renders as a grouped vertical one

**Severity** — HIGH

**Zone** — "Declared measures and dimensions: which are honoured, which are silently discarded, and which depend on a name the two tiers must agree on"

**Observation** — `ChartRenderer.tsx:18` reads `config.orientation` with default `'v'` and writes it to `trace.orientation` for bar traces (line 36-38); line 149 reads `config.barmode` with default `'group'`. Neither key is a member of `GraphConfigDict`, so Pydantic strips both at request validation exactly as it strips `config.metrics`. The defaults are therefore not fallbacks for an unset value — they are the only values that can ever arrive. A bar chart configured `"barmode": "stack"` over two `color` values renders as side-by-side bars; one configured `"orientation": "h"` renders upright.

**Evidence** — Same runtime readback as CHT-001: `metrics`, `orientation` and `barmode` were all absent from the 201 response, all three having been sent in the request body. `config.x` and `config.color`, which *are* declared, survived the same request. That isolates the strip to the undeclared keys rather than to the request or the endpoint.

**Consequence** — This is the one place in the presentation contract where the two tiers do agree on a key name and the configuration still has no effect, which makes it harder to spot than CHT-001: a developer reading `ChartRenderer.tsx` sees `config.barmode` wired end to end and concludes stacked bars work. They do not. Where a dashboard groups by a `color` dimension the reader sees a grouped chart and cannot tell it is not the stacked chart that was configured. Grouped-versus-stacked is exactly the comparison a stacked bar is chosen to make, so the figure is complete-looking and wrong in the one respect the configuration asked for.

**Recommendation** — Add `orientation: str | None` and `barmode: str | None` to `GraphConfigDict` so the two keys stop being stripped, and constrain their values in the same TypedDict (`Literal["v","h"]` and `Literal["group","overlay","relative","stack"]`) so an unsupported value is rejected rather than cast through the `as` at `ChartRenderer.tsx:149`. This is the same TypedDict edit as CHT-001's first step and belongs in the same commit.

### CHT-006 — `GraphDataResponse.layout` is declared and no construction site supplies it, so no chart layout setting reaches any frame

**Severity** — HIGH

**Zone** — "The declared presentation contract: which declared fields the served response never populates"

**Observation** — `GraphDataResponse` declares `layout: ChartLayoutConfig | None = None` (`src/mkobi/models/data.py:435`), with a `json_schema_extra` example advertising `"layout": {"title": "Sales Chart"}` (line 449) and a docstring at line 428 promising "graph metadata (id, type, name) and Plotly.js data". The route that produces every served figure has exactly two construction sites — `src/mkobi/api/routes/data.py:152-158` (single-graph branch) and `188-194` (all-graphs branch) — and neither passes `layout`. Both are the only `GraphDataResponse(...)` constructions in the codebase. The field therefore resolves to its `None` default on every response.

The consequence is total for the layout surface. `convertChartLayoutToPlotly` (`ChartRenderer.tsx:80`) opens with `if (!layout) return undefined`, so on every chart the converted layout is `undefined`. The `bar` branch spreads `undefined` (harmless) and still supplies `barmode` and `xaxis`; the `pie` branch passes `undefined` as the whole layout; the `line` branch passes `undefined` into `LineChart`, whose own `{title, xaxis, yaxis}` defaults (`LineChart.tsx:19-24`) are then overridden by the spread — so the line chart gets `{title:{text:''}, xaxis:{title:{text:''}}, yaxis:{title:{text:''}}}` and a title-less, axis-title-less frame. Every field `convertChartLayoutToPlotly` knows how to map — `title`, `xaxis.title`, `xaxis.type`, `xaxis.range`, `yaxis.title`, `yaxis.type`, `yaxis.range`, `showlegend`, `height`, `width`, `template` — is unreachable.

`AxisConfig.label` (`src/mkobi/models/types.py:105`, mirrored at `frontend/src/shared/types/api.types.ts:188`) is a twelfth dead field: even if `layout` were populated, the converter reads `title` and `label` is never consulted.

**Evidence** — Runtime. `GET /api/v1/data/aggregated?dashboard_id=a5214e7a-…` returned both graphs with `layout` absent from each object and the same result with and without a filter, confirming the field is never emitted rather than emitted-as-empty. Static: the two construction sites at `data.py:152-158` and `188-194` against the model at `data.py:431-436`. The converter's early return is `ChartRenderer.tsx:81`.

**Consequence** — A chart title, an x-axis title, a y-axis title, an axis range, an axis scale type, a legend toggle, a figure height, a figure width and a Plotly template are all storable on a graph (`config.title`, `config.xaxis`, `config.yaxis`, `config.layout` are all declared and survive the round trip — see CHT-004) and all absent from every figure. What a reader sees instead is the graph's `name` rendered as the heading by `DashboardView.tsx:191-193` and empty axis titles drawn by Plotly. The figures are not wrong; they are unlabelled in the one place a dashboard author would expect their own wording.

**Recommendation** — Either populate the field or delete it. Populating is one line at each of the two construction sites (`layout=ChartLayoutConfig(**graph.config["layout"])` when `graph.config` carries one) and makes CHT-004's `config.layout` key real. Deleting it removes the false affordance in the OpenAPI example at `data.py:449` and the converter's eleven unreachable branches. Recommend populating: the `config.layout` key already round-trips today, so the value is in the database and only the read path is missing.

### CHT-007 — A `pie` graph is handed a scatter-shaped trace, so the pie renders with no slices

**Severity** — HIGH

**Zone** — "Per chart type: what the rendered figure is derived from, and what the declared type permits the renderer to discard"

**Observation** — `makeTrace` (`ChartRenderer.tsx:28-43`) unconditionally sets `x: xVals` and `y: yVals`, then sets `type` to `'pie'` when `graph.type === 'pie'` (line 32). A Plotly `pie` trace is populated by the attributes `labels` and `values`; `x` and `y` are not among the attributes it reads, and the function never emits `labels` or `values` for any type. So the `pie` branch at `ChartRenderer.tsx:155` hands `PlotlyChart` a single trace of `{x: [...], y: [...], type: 'pie'}` and Plotly has nothing to draw. The `bar` branch is the mirror image and works: `bar` does read `x` and `y`.

The same function is the only producer of trace shapes in the client — `LineChart.tsx` receives its trace from `ChartRenderer.tsx:138` and `PlotlyChart` receives the rest — so there is no other place a pie trace could be given the attributes it needs.

**Evidence** — Static: `ChartRenderer.tsx:30-33` is the sole assignment of `x` and `y` on a trace, and `ChartRenderer.tsx:28-43` contains no `labels` or `values` assignment. `GraphType` in `src/mkobi/models/enums.py` includes `pie`, and the dashboard config accepts `graph_types: ["bar","line","pie","table"]` — the create call for this audit's probe dashboard returned HTTP 201 with exactly that list, so the type is declarable. `/data/aggregated` returns `"type":"bar"` for the seeded graphs, so the branch is reachable for any pie graph a user creates.

**Consequence** — Every pie chart on every dashboard renders as an empty pie frame regardless of how much data it is given. The gate at `ChartRenderer.tsx:128` passes, because `graph.data.length > 0` — the response really does carry rows — so the reader gets a figure rather than the "No data available for this chart" message that would at least have been honest. The dashboard heading and a correctly-populated `TableChart` for the same graph sit next to it, so the emptiness reads as a rendering quirk rather than a contract failure.

**Recommendation** — Give the pie branch its own trace builder that emits `{type: 'pie', labels: xVals, values: yVals, ...}` instead of routing it through `makeTrace`. It depends on the measure lookup being fixed first (CHT-001), because `values` built from `Number(row['y'] ?? 0)` would be an all-zero pie rather than an empty one — so sequence this after the CHT-001 step in the roadmap rather than with it. Note the direction of travel: if CHT-003 is taken, the `labels`/`values` split has a natural home in the same place the measure name is resolved, and both changes land in one function.

### CHT-008 — The line branch passes `convertToPlotlyData(graph)[0]`, dropping every series but the first

**Severity** — HIGH

**Zone** — "Per chart type: what the rendered figure is derived from, and what the declared type permits the renderer to discard"

**Observation** — `convertToPlotlyData` returns a `Data[]`. When `config.color` is set it returns one trace per distinct colour value (`ChartRenderer.tsx:45-65`, `Object.entries(groups).map(...)` at line 64); otherwise it returns exactly one trace (line 74). The line branch takes the leading element only:

```tsx
if (graph.type === 'line') {
  return <LineChart data={convertToPlotlyData(graph)[0]} layout={…} />   // line 138
}
```

`LineChart` then wraps it as a single-element array (`LineChart.tsx:26`, `data={[data]}`), so the remaining traces are not carried forward unread — they are discarded. The surviving trace is whichever colour group happened to be inserted first into the `groups` object, which is insertion order over `graph.data` and is not related to any sort.

The `bar` branch at line 142 does not have this defect; it passes the whole array.

**Evidence** — Static: `ChartRenderer.tsx:138` indexes `[0]` on the result of a function typed `Data[]` and returning `Object.entries(groups).map(...)` at line 64; `LineChartProps.data` is typed `Data`, not `Data[]` (`LineChart.tsx:5`); `LineChart.tsx:26` re-wraps it as `[data]`. That a line graph is configured with a `color` dimension is declarable — the seeded graph `546e04d8-bbc7-4a0c-98b6-0d585acb662d` in this dev instance stores `"config":{"x":"month_label","color":"brand"}`, and `GraphConfigDict.color` is a declared key.

**Consequence** — A line chart configured with a `color` dimension — the standard way to draw one series per segment — renders a single line. With N colour values the reader sees 1 of N series and the legend shows 1 entry, so nothing on screen says N-1 are missing. Because `mode` is hard-coded to `'lines'` (line 40) with no markers, the single surviving series is also the only visual cue that the axis carries more than one category. The figure is otherwise correct, which is what makes this worse than an error: a reader comparing two segments draws a conclusion from one of them.

**Recommendation** — Widen `LineChartProps.data` to `Data[]` and pass the full array: `<LineChart data={convertToPlotlyData(graph)} …/>` with `data={data}` at the Plotly call. This is the same change the `bar` branch already models, so it introduces no new concept. It lands in the same file and function as CHT-001 and CHT-007; sequence it after CHT-001 so the surviving traces carry real values rather than zeros, but the diff itself is independent and safe to review on its own.

### CHT-004 — Eight declared config keys are accepted, stored, served and read by nothing

**Severity** — MEDIUM

**Zone** — "Declared measures and dimensions: which are honoured, which are silently discarded, and which depend on a name the two tiers must agree on"

**Observation** — Of the eleven keys `GraphConfigDict` declares, the renderer reads two: `config.x` (`ChartRenderer.tsx:15`) and `config.color` (line 16, consumed at 45-65). `config.orientation` and `config.barmode` are read but cannot be stored (CHT-001, CHT-005). Of the nine remaining, eight are stored and served and read by nothing anywhere in the client:

`y`, `xaxis`, `yaxis`, `title`, `layout`, `secondary_y`, `sort_x`, `sort_color` — with `xaxis`, `yaxis`, `title` and `layout` all having a `GraphDataResponse.layout` counterpart that the server never populates (CHT-006). The ninth, `yoy`, is deferred: the `yoy` configuration is structurally unusable upstream (phase 05, DP-009), so no claim is made about it here beyond its being in the same accepted-and-ignored set.

`config.title` is the sharpest instance. A graph created with `config: {"title": "Revenue by region"}` is stored with that title, is returned by `GET /api/v1/graphs/`, is returned again by `/data/aggregated`, and is read by no component: `DashboardView.tsx:191-193` renders `graph.name` as the heading above every chart and never reads `config.title`.

**Evidence** — The CHT-001 readback shows `y`, `xaxis`, `yaxis`, `title`, `layout`, `secondary_y` and `sort_x` surviving the round trip intact, so the acceptance is real and not a validation artefact. A read of `frontend/src/features/dashboards/ui/charts/` and `frontend/src/features/dashboards/ui/DashboardView.tsx` finds no occurrence of `config.title`, `config.xaxis`, `config.yaxis`, `config.layout`, `config.secondary_y`, `config.sort_x` or `config.sort_color`.

**Consequence** — Eight settings a dashboard author can set through the API are accepted without complaint, returned by the API, and have no effect on any figure. The rendered consequence is bounded today — the graph's `name` and the axis defaults still label the frame — so this is not a wrong number, it is a set of declared controls that do nothing. The sharp edge is `title`: it is the field an author reaches for first, it round-trips successfully so the API looks like it took, and the chart is captioned by `graph.name` instead.

**Recommendation** — Do not add renderer support for all eight. Pick one: either narrow `GraphConfigDict` to the keys the renderer honours (`x`, `y`, `color`) so the API rejects the rest instead of silently accepting them, or promote the two that carry real reader-visible weight — `title` and `y` — to a contract the renderer honours and delete the rest. Narrowing is the smaller change and removes the false affordance immediately. The choice of which keys to keep is a product decision; the audit position is that an accepted-and-ignored key is worse than a rejected one.

### CHT-009 — A `multiselect` or `range` filter selection is sent as an array and compared with `str()`, so it can never narrow a frame

**Severity** — MEDIUM

**Zone** — "Filter binding: whether the configured selection reaches the query the figure is drawn from, and what the user sees when it does not"

**Observation** — The binding path is intact up to the comparison. `DashboardFilters.handleFilterChange` stores the selection in component state and calls `onChange` after a 300 ms debounce (`DashboardFilters.tsx:48-63`); `DashboardView` holds it in `filters` state (`DashboardView.tsx:35-37`); `useAggregatedData` puts it in the TanStack query key as `['aggregatedData', dashboardId, filters]` (`dashboardApi.ts:69`) and serialises it into the `filters` query parameter (line 74); the route parses it (`data.py:107-115`) and hands it to the repository; the repository turns each entry into `AggregatedData.dims[key].astext == str(value)` (`aggregated_data_repo.py:158-162`). The selection does reach the request.

The comparison cannot succeed for two of the four filter types the client offers. A MUI `multiple` Select reports an array (`DashboardFilters.tsx:162`, `onChange(e.target.value)`), and the `range` branch reports `[number, number]` from the Slider (line 191). `str(['North'])` is the literal `"['North']"`; `str([0, 100])` is `"[0, 100]"`. Neither equals a `dims` value's `astext`. A `range` filter could not be honoured even if it arrived as a scalar, because equality is not a range test. A `select` filter sends a scalar and is the one type that binds correctly.

**Evidence** — Static: `DashboardFilters.tsx:162` and `:191` produce arrays; `aggregated_data_repo.py:161` applies `str(value)`. Reproduced against the running interpreter with the stored side fixed at a JSONB string `region = "North"`: `str('North') == 'North'` → `True`; `str(['North']) == 'North'` → `False`; `str(['North','South']) == 'North'` → `False`; `str([0, 100]) == 'North'` → `False`. The client offers exactly these four types in its `switch` (`DashboardFilters.tsx:132-213`).

**Consequence** — Selecting more than one value in a multiselect filter, or any value in a range filter, sends a request that returns zero rows. `ChartRenderer.tsx:128` then renders "No data available for this chart" for every graph the filter touched. The control still shows the selection applied — chips for the multiselect (line 164), the slider thumb for the range — so the screen says the filter is on and the chart says there is no data, and nothing distinguishes a genuinely empty result from a filter that cannot be evaluated. This is graded MEDIUM rather than CRITICAL because the figure is visibly empty rather than confidently wrong: a reader is not misled about a value, they are left unable to read one and are given no reason why.

**Recommendation** — Make the repository branch on the shape of the value rather than stringifying it: a scalar keeps `dims[key].astext == str(value)`; a list becomes `AggregatedData.dims[key].astext.in_([str(v) for v in value])`; a two-element numeric list on a numeric dimension becomes a `BETWEEN`. Reject anything else with a 422 rather than a silently empty result, so an unevaluable filter is an error the user can see instead of a chart that vanishes. The `range` case needs a decision the code does not currently record anywhere — whether `range` filters a dimension or a measure, since the repository only ever reads `dims` — so treat that as a product decision to make before the fix, not a detail.

### CHT-010 — The option list behind every `source: 'data'` filter is never invalidated, so a filter keeps offering values the data no longer has

**Severity** — MEDIUM

**Zone** — "Filter binding: whether the configured selection reaches the query the figure is drawn from, and what the user sees when it does not"

**Observation** — `FilterField` calls `useFilterValues(dashboardId, filter.name)` unconditionally (`DashboardFilters.tsx:126`) and, for a filter declared `source: 'data'`, uses that response as the *entire* option list of the control (`DashboardFilters.tsx:127-130`). The backing query key is `['filterValues', dashboardId, filterName]` (`dashboardApi.ts:93`).

The complete `invalidateQueries` inventory in `frontend/src` is nine call sites, and none names that key: `['admin','users']` ×3 (`UserManagement.tsx:99,112,123`), `['admin','registration-requests']` ×2 (`RegistrationRequests.tsx:93,108`), `['admin','dashboards']` ×3 (`DashboardManagement.tsx:72,92,111`), `['dashboards', id]` (`dashboardApi.ts:84`) and `['aggregatedData', dashboardId]` (`dashboardApi.ts:86`).

This adjudicates **VAL-13-003**, which the phase-13 executor filed as an empty band and whose validator refuted, naming `DashboardFilters.tsx:126-127` as the consumer. The validator is correct on both halves and this finding confirms it at runtime-independent cost: the key is load-bearing for every `source:'data'` filter's option list, and no invalidation path reaches it. The question is a presentation-contract staleness question, so it is filed here rather than left with phase 13.

**Evidence** — Static: `DashboardFilters.tsx:126-130` against the nine `invalidateQueries` call sites listed above. The upload path that changes the data — `UploadModal.onUploadComplete` → `invalidateAggregatedData(id)` (`DashboardView.tsx:215-220` → `dashboardApi.ts:86`) — invalidates the frames and not the options. The backend endpoint is `GET /dashboards/{id}/filter-values?filter_name=…` (`dashboardApi.ts:36-39`), which reads the same `aggregated_data` rows the frames are drawn from, so its result genuinely does change when those rows do.

**Consequence** — On a dashboard that is open when a new file is uploaded, the charts redraw with the new data and the filter dropdowns keep the option list captured when the page mounted. A category introduced by the new upload cannot be selected at all, because it is not in the stale list; a category the new upload removed can still be selected, and selecting it drives the frame to empty via the same path as CHT-009. The reader has no way to tell the list is stale, and the visible symptom — a chart that empties on a selection that looks legitimate — points at the data rather than at the control. On a fresh page load the effect is absent, which is what makes it a session-scoped defect rather than a permanent one.

**Recommendation** — Invalidate the option list wherever the frames are invalidated. The smallest change is in `useInvalidateDashboard` (`dashboardApi.ts:80-88`): add `invalidateFilterValues: (dashboardId) => queryClient.invalidateQueries({ queryKey: ['filterValues', dashboardId] })` and call it from `UploadModal.onUploadComplete` alongside `invalidateAggregatedData`. The prefix match is sufficient — `['filterValues', dashboardId]` covers every `filterName` under that dashboard without enumerating them. If any other mutation is added that writes `aggregated_data` later, the same key must be invalidated there too; a comment on the hook naming that dependency is cheaper than rediscovering it.

## Distribution

- `frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx` — CHT-001, CHT-002, CHT-004, CHT-005, CHT-007, CHT-008. The single function that converts a served figure into a frame carries six of the ten findings; it is where the presentation contract is either honoured or lost.
- `src/mkobi/models/types.py` (`GraphConfigDict`) — CHT-001, CHT-004, CHT-005, CHT-006. The TypedDict that defines which configuration keys exist is the gate that strips the three keys the renderer reads.
- `src/mkobi/models/data.py` (`GraphDataResponse`) and `src/mkobi/api/routes/data.py` — CHT-003, CHT-006. The serving tier's response model omits the graph's own measure list and never populates its declared `layout`.
- `src/mkobi/db/repositories/aggregated_data_repo.py` and `frontend/src/features/dashboards/ui/DashboardFilters.tsx` — CHT-009, CHT-010. The two ends of the filter binding, which is intact in transit and broken in both comparison and refresh.

`ChartRenderer.tsx` carries the most, and it is the right place to look first: it is 156 lines, it is the sole producer of every trace in the client, and it reads a `config` object whose keys are decided three tiers away in a `TypedDict` it cannot see.

## Cross-Finding Analysis

Two causes account for all ten findings.

**The configuration vocabulary is defined in one place and consumed in another, with nothing reconciling them.** `GraphConfigDict` (`src/mkobi/models/types.py:138-152`) is the declaration; `ChartRenderer.tsx:15-18` and `frontend/src/shared/types/api.types.ts:209-215` are the consumers. Neither is derived from the other, and the gap runs in both directions. Keys the renderer reads but the declaration omits are stripped at write time and can never arrive — `metrics` (CHT-001), `orientation` and `barmode` (CHT-005). Keys the declaration carries but nothing reads are accepted, stored, returned and ignored — eight of them: `y`, `xaxis`, `yaxis`, `title`, `layout`, `secondary_y`, `sort_x`, `sort_color` (CHT-004), with the same four again through the never-populated `GraphDataResponse.layout` (CHT-006); the ninth, `yoy`, is deferred to phase 05 DP-009. The measurement that would have caught this is one line: the renderer names five config keys, the declaration names eleven, and the two sets intersect in two.

**The response model does not state what the client needs to draw the figure.** `GraphDataResponse` (`src/mkobi/models/data.py:425-436`) omits the graph's own `metrics` and `dimensions` (CHT-003) and never populates its `layout` (CHT-006). The renderer's response to that omission is to guess — `config.metrics` or the literal `'y'` (CHT-001) — and the guess is wrong in a way that produces zeroes rather than an error. CHT-003 is the structural cause under CHT-001: with the served measure list present, the renderer would have a name that is correct by construction, and the `_{agg}` suffix that makes `'y'` unmatchable would stop mattering to the presentation tier.

Three findings are independent of both causes and of each other. CHT-002 (the bar branch writing `xaxis` after the spread), CHT-007 (`makeTrace` emitting `x`/`y` on a `pie` trace) and CHT-008 (the line branch indexing `[0]`) are three separate mistakes inside `convertToPlotlyData` and its caller. They share a file, not a cause, and each can be fixed and reviewed on its own.

CHT-009 and CHT-010 share no code — one is a comparison in the repository, the other a query key in the client — but they compose: a stale option list hands the user a value the current data does not have, and selecting it produces exactly the empty frame CHT-009 describes. That composition is the reason CHT-010's consequence mentions CHT-009, and it is why fixing either alone leaves the other reachable.

### Deferrals and cross-references

- **FE-007 / FE-008 (phase 13, ruled).** The same defect — a chart payload declared as Plotly traces but served as row dicts — is visible from this phase's side in `ChartRenderer.tsx:21-23`, where the early return `'x' in graph.data[0] && 'y' in graph.data[0]` is the renderer's accommodation for it. **Merge, not adjacency:** this is one defect with one remedy, in one function, and the phase-13 ruling already assigned it. Nothing in CHT-001 to CHT-008 re-files it, and the fix for the shape gap would not by itself close CHT-001 — `GraphDataWithConfig.data` is still typed `Data[]` while the payload is `list[dict]`, and typing it correctly still leaves the renderer needing a measure name the response does not carry (CHT-003). Recorded here so the merge is explicit and not duplicated in implementation.
- **DP-002 / DP-018 (phase 05).** The claim filed here is distinct and does not overlap: DP-018 is that the *stored value* is a `sum` regardless of the configured `metric_agg`, while this phase's claim is that the *served column name* is `f"{m}_{metric_agg}"` (`src/mkobi/services/aggregation_service.py:93`) and that no declarable field lets the renderer name it. A correct DP-018 fix changes the values and leaves CHT-001 exactly as it is; a correct CHT-001 fix leaves DP-018 as it is. They must both be fixed for a reader to see the right number.
- **DP-009 (phase 05).** `yoy_config`, `share_config` and `custom_metrics` are structurally unusable upstream. The presentation consequence of a `yoy` column reaching the frame would be CHT-001's zero-trace, but the `yoy` config never gets that far, so this phase files nothing on it. The `config.yoy` and `config.secondary_y` keys are counted in CHT-004's inventory only as accepted-and-ignored keys, not as a claim about the transformation path.
- **05 b4 / b6 — how a measure name is derived.** The `f"{m}_{metric_agg}"` aliasing at `aggregation_service.py:93` and the discarding of the configured `alias` are name *derivation*, which phase 05 owns. CHT-001 relies on the current behaviour as evidence but its remedy does not require changing it, and it says so in the recommendation.
- **08 b1 / b2 — one named home for a fixed value or vocabulary.** The `GraphConfigDict` / client-type divergence is a vocabulary with two homes and nothing keeping them equal. This phase does not re-file it: the rendered consequence is named in CHT-001 and CHT-005, and the two-homes property itself is 08's question.
- **13 b7 — absent data rendering distinguishably.** CHT-009 and CHT-010 both end in an empty frame. That the empty frame is indistinguishable from other empties is 13 b7's; that the frame is empty at all is this phase's. Recorded so the two are not conflated.
- **11 b4 / b9 — payload and per-process ceilings.** Not reached. PERF-001's 30.9 MB body and 375,000 rows mean the renderer's leading-part truncation (CHT-008) is not the binding constraint on that instance; no measurement in this report is affected by it.
- **Client bundle composition.** Assigned by deferral in phase 10 and enumerated by no active phase's scope paragraph. Not claimed here, consistent with the phase-16 scope note.

## Roadmap

Three groups, ordered by cause rather than severity.

**Step 1 — Make the declared vocabulary and the consumed vocabulary the same set. Closes CHT-001, CHT-005, and the enabling half of CHT-004.**

Add `metrics: list[str] | None`, `orientation: Literal["v","h"] | None` and `barmode: Literal["group","overlay","relative","stack"] | None` to `GraphConfigDict`, so the three keys the renderer already reads stop being stripped at `GraphCreate`/`GraphUpdate` validation. Then change `ChartRenderer.tsx:17` to prefer `config.y` — the key the tier already declares and stores — as the single-measure fallback, so a graph configured the documented way draws the measure the operator named.

*Must be true before step 2:* the CHT-001 probe readback returns a config that contains `metrics`, `orientation` and `barmode`. Until it does, step 2 has no measure name to read and every trace it builds is zero.

**Step 2 — Have the serving tier state the measure and dimension names. Closes CHT-003, and makes CHT-001's fix structural rather than conventional.**

Add `metrics` and `dimensions` to `GraphDataResponse`, populate both at `data.py:152-158` and `188-194`, mirror them in `GraphDataWithConfig`, and have `convertToPlotlyData` read the served list instead of `config.metrics` or `'y'`.

*Must be true before step 3:* a `/data/aggregated` response carries a non-empty `metrics` list for every graph, and the renderer reads it. Until then, step 3's fixes produce figures that are correctly shaped but still flat.

**Step 3 — Fix the three per-type defects in the renderer. Closes CHT-002, CHT-007, CHT-008.**

Merge rather than replace `xaxis` in the bar branch (`ChartRenderer.tsx:150`); give the `pie` branch a trace that emits `labels` and `values`; pass the full array to `LineChart` and widen `LineChartProps.data` to `Data[]`.

*Sequencing note:* these are independent of each other and safe to land separately. They should land **after** step 1, because each changes what a trace carries and landing them first produces figures that are correctly shaped and still all-zero — which reads as a failed fix. Do not need to wait for step 2.

**Step 4 — Populate or delete `layout`; narrow the accepted-but-ignored keys. Closes CHT-006, CHT-004.**

Populate `GraphDataResponse.layout` at both construction sites from `graph.config["layout"]` — the value already round-trips today — and drop `AxisConfig.label` from both tiers, since nothing reads it. Then decide the fate of `y`, `xaxis`, `yaxis`, `title`, `secondary_y`, `sort_x` and `sort_color`: narrow `GraphConfigDict` to the keys the renderer honours, or promote the two that carry reader-visible weight. Narrowing is the smaller change.

*Must be true before step 4 ships:* step 2 has landed, because narrowing the vocabulary while the renderer is still guessing would turn a silently-ignored key into a rejected one at the same moment the client loses its only workaround.

**Step 5 — Fix the two filter-binding defects. Closes CHT-009, CHT-010.**

Branch on value shape in `aggregated_data_repo.py:158-162` (scalar / `in_` list / range), rejecting unevaluable filters with a 422. In parallel, add `invalidateFilterValues(dashboardId)` to `useInvalidateDashboard` and call it wherever `invalidateAggregatedData` is called.

*Must be true before step 5 ships:* a product decision on whether a `range` filter targets a dimension or a measure. The repository only ever reads `dims`, and the code records that decision nowhere. Fixing the list case alone is still worth doing; the range case is not, until that decision is written down.

## Rollout Safety

Step 1 changes what the API accepts and stores. Three risks. First, graphs already in a database have no `metrics`, `orientation` or `barmode` in their stored config — nothing is backfilled and nothing needs to be, because the renderer's defaults (`'y'`, `'v'`, `'group'`) are what those graphs are already being drawn with today, so their rendering is unchanged by the edit. Second, once `metrics` stops being stripped, existing requests that were sending it will start having it persisted; nothing downstream writes `config.metrics` today, so there is no second writer to conflict with. Third, the `Literal` constraints will start rejecting values that were previously stripped-and-ignored — `orientation: "horizontal"` was silently dropped before and will now 422. That is the intended direction, but it is a behaviour change for any caller that was relying on the silence, so check the admin UI's graph editor for whether it ever sends these keys before shipping. Revert is a single revert of the `GraphConfigDict` edit; no stored data depends on it because nothing can currently read what it would gain.

Step 2 changes the response shape. `GraphDataResponse` is a `response_model` on `/data/aggregated`, so adding two required list fields is additive in JSON terms — existing clients reading `graphs[].data` are unaffected — but the OpenAPI schema changes, and the generated client types will change with it, so any TypeScript that constructs a `GraphDataWithConfig` literally (tests, fixtures) needs the two new members. Verify by re-running the CHT-001 probe: the response must carry a non-empty `metrics`, and a bar chart must draw non-zero bars. Revert is a single revert; the extra keys are ignored by any consumer that has not been updated to read them.

Steps 3 and 5 are renderer and repository changes with no persisted or served shape change, so their risk is confined to what the user sees — which is the point. The one to watch is step 5's 422: a filter that previously returned an empty chart will now return an error, and `DashboardView.tsx:181-185` renders that as "Failed to load chart data" for the whole dashboard, not for the one filtered graph, because `/data/aggregated` serves every graph in one response. If the 422 path is reachable for any legitimate configuration, that couples one bad filter to every chart on the dashboard — which is a worse outcome than the empty chart CHT-009 produces today. Decide deliberately whether the rejection belongs at filter *change* time (a 422 on the control's own request) rather than on the combined data request, and verify that before shipping step 5.

## Appendices

### A1 — Declared-field inventory for a served figure

Derived from `GraphDataResponse` (`src/mkobi/models/data.py:431-436`) and the two construction sites at `data.py:152-158` and `188-194`.

| Field | Declared | Construction site supplies | Populated in response | Read by renderer |
|---|---|---|---|---|
| `graph_id` | yes | both | always | no (React key only, `DashboardView.tsx:190`) |
| `type` | yes | both | always | yes — `ChartRenderer.tsx:32,123,137,145` |
| `name` | yes | both | always | no — rendered as heading at `DashboardView.tsx:191-193` |
| `data` | yes | both | always | yes — `ChartRenderer.tsx:21,48,70` |
| `layout` | yes | **neither** | **never** (`null` default) | `ChartRenderer.tsx:81` — always short-circuited |
| `config` | yes | both (`= graph.config` verbatim) | always | yes — `ChartRenderer.tsx:15-18,149` |
| `metrics` | **not declared** | — | — | — (CHT-003) |
| `dimensions` | **not declared** | — | — | — (CHT-003) |

### A2 — `GraphConfigDict` key inventory

`src/mkobi/models/types.py:138-152` against the renderer's reads.

| Key | Declared | Stored (survives validation) | Read by renderer | Verdict |
|---|---|---|---|---|
| `x` | yes | yes | `ChartRenderer.tsx:15` | honoured |
| `color` | yes | yes | `ChartRenderer.tsx:16,45-49` | honoured |
| `y` | yes | yes | — | accepted, ignored (CHT-004) |
| `xaxis` | yes | yes | — | accepted, ignored (CHT-004, CHT-006) |
| `yaxis` | yes | yes | — | accepted, ignored (CHT-004, CHT-006) |
| `title` | yes | yes | — | accepted, ignored (CHT-004) |
| `layout` | yes | yes | — | accepted, ignored (CHT-004, CHT-006) |
| `yoy` | yes | yes | — | accepted, ignored; deferred to phase 05 DP-009 |
| `secondary_y` | yes | yes | — | accepted, ignored (CHT-004) |
| `sort_x` | yes | yes | — | accepted, ignored (CHT-004) |
| `sort_color` | yes | yes | — | accepted, ignored (CHT-004) |
| `metrics` | **no** | **no — stripped** | `ChartRenderer.tsx:17,26` | unnameable (CHT-001) |
| `orientation` | **no** | **no — stripped** | `ChartRenderer.tsx:18,37` | unstoreable (CHT-005) |
| `barmode` | **no** | **no — stripped** | `ChartRenderer.tsx:149` | unstoreable (CHT-005) |

### A3 — Per-chart-type derivation record

| `graph.type` | Frame built from | Declared settings that reach it | Discarded |
|---|---|---|---|
| `table` | `graph.data` → `TableChart` (`ChartRenderer.tsx:124`) | none read | every `config` key; `convertToPlotlyData` not called |
| `line` | `convertToPlotlyData(graph)[0]` → `LineChart` → `PlotlyChart` | `x`, `color`, `orientation` (no effect: `makeTrace` sets `mode` not `orientation` for line), `layout` (always `undefined`) | all traces after the first (CHT-008); `xAxisLabel`/`yAxisLabel` props of `LineChart` are never passed |
| `bar` | `convertToPlotlyData(graph)` → `PlotlyChart` | `x`, `color`, `barmode` (default `'group'`), forced `xaxis.type='category'` | `xaxis.title`, `xaxis.type`, `xaxis.range` after conversion (CHT-002); `layout` (CHT-006) |
| `pie` | `convertToPlotlyData(graph)` → `PlotlyChart` | `x`, `color` | `labels`/`values` never emitted (CHT-007) |

### A4 — Method and environment

Static analysis of `frontend/src/features/dashboards/` and the serving path
`src/mkobi/api/routes/data.py` → `src/mkobi/services/data_service.py` →
`src/mkobi/db/repositories/aggregated_data_repo.py`, plus targeted runtime
confirmation against the dev stack on `:8010` and the repository's own Python
interpreter. Runtime artefacts created and removed by this audit: dashboard
`CHT16-probe` (`af737dd8-d3bb-4ec0-9693-f34e238ce08d`) and graph
`cht16-probe-bar` (`08bf96a7-4999-41d4-b94d-0e646f630273`), both deleted after
the probes. No frontend build, test, lint or coverage command was run and no
file outside this report was modified. The dev stack was left as found.

### A5 — Bands left empty, and why

- **Finding identifiers are not in numeric order in the Findings section.** Blocks are ordered by descending severity, as the template requires. `CHT-004` is MEDIUM and therefore sits after `CHT-008` (the last HIGH) rather than in numeric position, because it was identified earlier in the run while a HIGH finding was still being confirmed. Severity and identifiers are both correct; only the presentation order differs from the numeric sequence. Cross-references throughout the report use the identifiers, not the positions, so nothing depends on the ordering.
- **No HIGH finding on a genuinely populated multi-measure `config.metrics` array.** CHT-001 and CHT-005 establish that `config.metrics` cannot be stored at all, so the "later members of a declared measure array are never read" case (`metricCols[0]` at `ChartRenderer.tsx:26` reading only index 0) has no reachable instance today. The leading-part truncation is filed once, where it is reachable: `ChartRenderer.tsx:138` taking `[0]` of a multi-trace result produced by `config.color`, which *is* declarable. Filing a second leading-part finding against `metricCols[0]` would describe a state the product cannot currently be configured into.
- **No finding on the line chart's `xAxisLabel` / `yAxisLabel` props.** `LineChart.tsx:12-18` accepts them and `ChartRenderer.tsx:138` never passes them, so they are always `''`. This is dead-parameter drift with no figure consequence beyond what CHT-006 already records, and it is the same `layout`-is-never-populated cause.
- **No finding on the pie branch's `config.color` grouping.** `makeTrace` sets `name` from the colour group (line 35) and a pie trace reads `labels`, so the grouping is as unreachable as the values. It is part of CHT-007's remedy, not a separate defect.
- **LOW band empty.** Nothing rated LOW. The candidates considered and rejected: `AxisConfig.label` (folded into CHT-006 — its parent is already HIGH and a separate LOW for one unread field inside a never-populated object would be noise), and the `graph.name` versus `config.title` divergence (folded into CHT-004 — the heading is correct today, which is precisely why this is MEDIUM and not a wrong figure).
- **Browser-tier render not observed live.** Charts were driven through the API and the conversion source rather than through a headless browser at `:5173`. The reason is stated in the residual footer below; no finding in this report depends on it.
- **No per-figure screenshot evidence.** Same reason. Every finding rests on a served payload plus the conversion source, which is sufficient for each claim and is labelled as such in its Evidence field.

### A6 — Residual limits on this report

- **The rendered frame itself was not observed.** `convertToPlotlyData` was read, not executed in a browser, and `PlotlyComponent.tsx` was not traced into `plotly.min.js` to confirm how the library treats a `pie` trace carrying `x`/`y` (CHT-007 states the frame is empty because `labels` and `values` are never emitted; whether Plotly additionally warns on the unexpected `x`/`y` attributes is not established here, and the finding does not depend on it). The three independent defects in `convertToPlotlyData` are read from the source at the line numbers cited and each is a plain assignment or index, not an inference about library behaviour.
- **Aggregate rows were not produced for this phase's probe graph.** The probe graph was created and its config round-trip confirmed, but no file was uploaded, so `/data/aggregated` for `CHT16-probe` returned an empty `data` array. The consequence chain in CHT-001 is established from the served row construction (`data_service.py:216`, `{**dims, **metrics}`) and the alias rule (`aggregation_service.py:93`), not from a served payload containing a non-zero measure. A reader wanting a rendered zero-series should treat the one unexercised link as the alias rule.
- **Phase 05's DP-002 re-grade was not reconciled.** The brief records that DP-002 was re-graded CRITICAL to MEDIUM and that DP-018 is the finding that actually mislabels stored measures. This phase makes no claim about the stored *value* of a measure and therefore does not touch either. The relationship is recorded in Cross-Finding Analysis under DP-002/DP-018.
- **`HEAD` moved during this audit.** The baseline recorded in the frontmatter is `d008f555f5a2e1b3adb397c4bc67d95ed9c964c5` with 68 dirty paths, taken at the start of the run. Every path this report cites was re-read at its cited line number during the run; a concurrent remediation programme was landing commits against phase-02 config/secrets findings, which do not touch the chart path. If `ChartRenderer.tsx`, `GraphConfigDict` or `GraphDataResponse` changes after the baseline, the line numbers drift and the claims should be re-checked against the current source — the substance does not depend on the line numbers.

