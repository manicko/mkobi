# Phase 16 — FRONTEND drift report

**Audit target:** frontend surfaces of `.ai/plans/16-chart-presentation-contract-remediation-execution.md`
**Baseline commit:** `907e052` · **Audited HEAD:** `d6505b1` (**215 commits** ahead at first check; `d6505b1 chore(plans) clean before audit` landed mid-audit)
**Scope:** frontend only + docs + gate facts. Backend findings belong to the sibling audit.
**Constraints honoured:** no code/doc/test/config edits, no git mutations, no `fe-test` / `vitest --coverage` / `npm run build`.

> **Note on the brief:** the sibling file `.ai/plans/_code-context/16-chart-presentation-contract-code-context.md`
> **does** exist on disk (59 261 bytes, tracked, last written by `4692bfd`, `source_head 907e052`). It was not
> consulted — everything below was re-derived from the tree. It is stale by 215 commits.

---

## 1. The decisive answer — did `f500d1f` delete `convertChartLayoutToPlotly`?

**NO. It still exists.** The plan's `C16-2` deletion hazard **did not fire**.

```
frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:103
export function convertChartLayoutToPlotly(layout?: GraphDataWithConfig['layout']): Partial<Layout> | undefined {
```

Present verbatim at `ChartRenderer.tsx:103-133`, unchanged by `f500d1f`. Phase 13 took `CT-7`
**option (b) — narrow the types** — not option (a) — delete the function. Two consequences for phase 16:

- `CHT-002`'s xaxis override is still live and still latently destructive (see §1.3).
- `C16-2` is **void as written**: its premise ("if `CT-7` deletes the function") never materialised.

### 1.1 What `f500d1f` actually did to `ChartRenderer.tsx`

| Removed by `f500d1f` | Replacement |
| --- | --- |
| `as unknown as Record<string, unknown>[]` (the two shape casts, former `:71`, `:73`) | `readScalar` + `isChartRecord` runtime guard → `isChartRecord(record)` / `isPlotlyShaped(record)` |
| `const trace: Record<string, unknown> = { x: xVals, y: yVals, type }` | `chartConversion.ts:127` → `const trace: Partial<Data> = { x: xVals, y: yVals, type }` |
| the three `as Partial<Layout>['title' \| 'xaxis' \| 'yaxis']` assertions | **one** `as unknown as Template` at `chartConversion.ts:107` (a *different* type gap, in a *new* file) |

Also: added an early `if (graph.data.length === 0) return []` guard; **changed behaviour** by ANDing
`!colorCol` into the Plotly-shaping test (a server trace set + `colorCol` now falls through to the
flat-record path instead of passing through); deleted the four explanatory comments. Net `ChartRenderer.tsx`
is 175 lines lighter; `chartConversion.ts` (132 lines) and `ChartRenderer.test.tsx` (153 lines) are new.

### 1.2 `convertToPlotlyData` — verbatim, `ChartRenderer.tsx:68-133`

```tsx
export function convertToPlotlyData(graph: GraphDataWithConfig): Data[] {
  const data = graph.data
  if (data.length === 0) return []

  const config = graph.config ?? {}
  const xCol = config.x ?? 'x'
  const metricCol = config.metrics?.[0] ?? 'y'
  const orientation = config.orientation ?? 'v'

  if (data.every(isPlotlyShaped)) {
    return data as Data[]
  }

  if (config.color) {
    return groupByColor(data as Record<string, unknown>[], {
      type: traceTypeFor(graph.type),
      xCol,
      metricCol,
      orientation,
    })
  }

  const { xVals, yVals } = collectSeries(data as Record<string, unknown>[], xCol, metricCol)

  return [
    makeTrace(xVals, yVals, {
      type: traceTypeFor(graph.type),
      name: metricCol,
      orientation: graph.type === 'bar' ? toOrientation(orientation) : undefined,
    }),
  ]
}
```

**Every presentation default is untouched.** `xCol`/`metricCol`/`orientation` still default to the literals
`'x'` / `'y'` / `'v'`. The `data as Data[]` / `data as Record<string, unknown>[]` casts that remain here are
**not** the two shape casts `f500d1f` removed — they are still casts, just on the already-narrowed element type.

### 1.3 The pie branch — `labels`/`values` are **NOT** assigned. Verbatim, `chartConversion.ts:127-147`

```ts
export function makeTrace(
  xVals: unknown[],
  yVals: unknown[],
  options: { type?: Data['type']; name?: string; orientation?: 'h' | 'v' } = {},
): Data {
  const type = options.type ?? 'scatter'
  // One narrow path builds the base trace. x/y are assigned unconditionally
  // because the server's flat records always carry both.
  const trace: Partial<Data> = { x: xVals, y: yVals, type }
  if (options.name !== undefined) trace.name = options.name
  if (options.orientation !== undefined) trace.orientation = options.orientation
  return trace as Data
}

export function traceTypeFor(type: GraphDataWithConfig['type']): Data['type'] {
  switch (type) {
    case 'bar':
      return 'bar'
    case 'line':
      return 'scatter'
    case 'pie':
      return 'pie'
    default:
      return 'scatter'
  }
}
```

`makeTrace` has **no `traceType` branch of any kind** — no pie arm, no `labels`, no `values`. The comment's
premise ("the server's flat records always carry both") is **false for the pie shape**. A `type: 'pie'` graph
therefore emits `{ x: [...], y: [...], type: 'pie', name: metricCol }`, which Plotly renders as a pie with no
slices. **`CHT-007` is untouched.** `CHTB-4` is open.

### 1.4 The grouped-colour branch — `groupByColor`, verbatim, `ChartRenderer.tsx:50-68`

```tsx
function groupByColor(
  records: Record<string, unknown>[],
  { type, xCol, metricCol, orientation }: { type: Data['type']; xCol: string; metricCol: string; orientation: string },
): Data[] {
  const groups = new Map<string, { xVals: unknown[]; yVals: unknown[] }>()
  for (const record of records) {
    const groupValue = String(record[colorColKey] ?? '')
    ...
    const metric = readScalar(record, metricCol)
    yVals.push(typeof metric === 'number' ? metric : Number(metric ?? 0))
```

The `groups` accumulator is **still built by Map insertion order over the rows**, with no sort and no
deterministic key order. Trace order therefore still varies between otherwise-identical responses.

### 1.5 The line branch's `[0]` — verbatim, `ChartRenderer.tsx:149-156`

```tsx
if (graph.type === 'line') {
  return (
    <LineChart
      data={convertToPlotlyData(graph)[0]}
      layout={convertChartLayoutToPlotly(graph.layout)}
    />
  )
}
```

Unchanged. `convertToPlotlyData(graph)[0]` still throws `TypeError: Cannot read properties of undefined`
whenever a line graph has an empty `data` array (the new `length === 0` guard returns `[]`). The early-return
added by `f500d1f` **widens** this crash surface from "empty server response" to "any empty `data`".

### 1.6 The two `Number(row[metricCol] ?? 0)` coercions — still present, one alias

`ChartRenderer.tsx:45` in `collectSeries`, and `ChartRenderer.tsx:63` in `groupByColor`:

```tsx
const metric = readScalar(record, metricCol)
yVals.push(typeof metric === 'number' ? metric : Number(metric ?? 0))
```

The subscript form became a `readScalar` call; **the `?? 0` collapse is byte-for-byte intact in both places**.
A config naming an unstoreable measure still yields a full-length `y` array of zeros, and `C16-4` therefore
still reports to the UI that "all metrics are present" while every one of them is zero. **`CHT-001` open.**

---

## 2. Commit → surface → block

| Commit | Subject | Phase-16 surface touched (symbol) | Block |
| --- | --- | --- | --- |
| `f500d1f` | fix(frontend): make the Plotly trace types match what the server sends | `ChartRenderer.convertToPlotlyData` (2 shape casts removed), `chartConversion.{isChartRecord,makeTrace,toLayoutTemplate}` (new), `ChartRenderer.test.tsx` (new). **`convertChartLayoutToPlotly` retained.** | `CHTB-1`, `CHTB-3`, `CHTB-4` |
| `77e2d47` | refactor(frontend): one identity source, no cross-layer edges, no dead barrels | deleted `ui/charts/index.ts` barrel + 5 other barrels; `shared/auth/identity.ts`; `shared/__tests__/layering.test.ts` (new FSD guard). **No chart-symbol change.** | `CHTB-4` (caller reachability only) |
| `49028f6` | fix(frontend): clear the remaining lint errors in the dashboard surface | `DashboardView.shouldPreserveFilters` + `loadPersistedFilters` (6 lint errors → 0) | `CHTB-5` (incidental) |
| `70958d6` | docs(frontend): align the client documentation and drop the void coverage procedure | `docs/02-dashboards/dashboards-api.md`, `docs/07-frontend/pages.md`, `docs/09-database/enums.md`. **Did not touch `extend-graphs.md`.** | `CHTB-8` (partial, unrelated) |
| `6f2d37a` | fix(frontend): key the aggregated-data cache by graph | `dashboardApi.useAggregatedData` queryKey `['aggregatedData', id, graphId ?? null, filters]` | `CHTB-7` (adjacent only) |
| `a3db812` | fix(frontend): give the dashboard range filter an accessible name | `DashboardFilters.renderRange` — `labelId` + `aria-labelledby` + `Typography variant="caption"` | `CHTB-6` (accessibility only; control **retained**) |
| `e4bd273` | build(frontend): untrack the coverage report directory | deleted 15 tracked `frontend/coverage/**` files, added `/frontend/coverage/` to `.gitignore` (anchored by `9d39218`) | `CHTB-9` (gate premise) |
| `5ca453f` / `05a06a0` | perf(aggregated): bound the aggregate read / take the displayed row count from the server | `DashboardView` "Showing N of M" from `rows_truncated` | `CHTB-5` (truncation half **landed**) |
| `dac421b` | fix(frontend): show one error surface per context from a typed vocabulary | `shared/api/errorSurfaces.ts` → `DashboardView` uses `CHART_DATA_LOAD_FAILED_MESSAGE` / `DASHBOARD_LOAD_FAILED_MESSAGE` | `CHTB-5` (string set **reorganised**) |
| `3cca6b0` | fix(frontend): report boundary errors through the client-errors route | `ErrorBoundary` | — |
| `3f01601` | fix(graphs): refuse undeclared keys inside the graph config | backend `GraphConfigDict` / `GraphConfigModel` (client-side read keys now accepted) | `CHTB-1` (backend half) |
| `ea1061a` | fix(frontend): narrow the barmode type and add cross-tier enum parity | `BarmodeEnum` mirror; `OrientationEnum` **left in `SERVER_ONLY_FAMILIES`** | `CHTB-1` (half-done) |
| `d94aaff` | build(docker): ship the client bundle inside the image | `docker/Dockerfile` `frontend-nginx` stage | — |

---

## 3. `LineChart.tsx`

**`LineChartProps.data` is still `Data`, not `Data[]`** — `LineChart.tsx:14`:

```tsx
interface LineChartProps {
  data: Data
  layout?: Partial<Layout>
  config?: Partial<Config>
}
```

- **The `[data]` re-wrap still exists** — `LineChart.tsx:26`: `<PlotlyChart data={[data]} …/>`.
- **`title`, `xAxisLabel`, `yAxisLabel` are still declared** — `LineChart.tsx:18-20` — and still never passed
  by any caller.
- **`convertDataToPlotlyFormat` still handles only `bar`** — `LineChart.tsx:53-59` returns
  `[{ type: 'bar', x, y }]` regardless of the trace's own `type`. A `'scatter'` trace round-trips as
  `type: 'bar'`.

**Complete caller census** (whole `frontend/src`, three symbol references plus the barrel deletion):

| Site | Kind |
| --- | --- |
| `ChartRenderer.tsx:151` | **the only production caller** |
| `ChartRenderer.test.tsx:22-27` | test mock (inspects props) |
| `filter-persistence.test.tsx` | test mock (not exercised) |
| `DashboardView.test.tsx` | test mock (not exercised) |

`ui/charts/index.ts` was deleted by `77e2d47`, so `LineChart` is reachable **only** by direct path.
Consequence: `CHT-008`'s prop-shape change is a genuine one-caller change — low risk, no migration.

---

## 4. Four verdicts

- **`CHTB-1` frontend half — PARTIALLY LANDED.** The two shape casts are gone and `barmode` is now typed
  `BarmodeEnum` (`ChartRenderer.tsx:163`; `api.types.ts:235`), but `xCol`/`metricCol`/`orientation` still
  default to `'x'`/`'y'`/`'v'` (`ChartRenderer.tsx:71,73,74`), both `Number(metric ?? 0)` collapses are intact,
  `api.types.ts::GraphDataWithConfig.config` declares 5 keys with `title`/`metrics`-drift still unresolved, and
  `OrientationEnum` is still in `SERVER_ONLY_FAMILIES` (`enums.ts:98`).
- **`CHTB-3` client half — PARTIALLY LANDED.** `convertChartLayoutToPlotly` still exists; the three named
  `fe-lint` assertions are gone; the bar branch still writes `xaxis` **after** the `...convertChartLayoutToPlotly(graph.layout)`
  spread (`ChartRenderer.tsx:161-164`), so `CHT-002` is open.
- **`CHTB-4` — STILL OPEN.** No `labels`/`values` for pie, no per-metric traces, no `y`-nameable substitute,
  insertion-order `groups` accumulator, `[0]` still there, `LineChartProps.data` still `Data`,
  `title`/`xAxisLabel`/`yAxisLabel` still unpassed.
- **`CHTB-5` absent-vs-zero client half — STILL OPEN.** `DashboardView.tsx:209` still gates on
  `aggregatedData.graphs.length > 0`, `:235` still shows the one indistinguishable
  `"No data available for this dashboard. Upload data to see charts."`, and both `?? 0` collapses still
  fabricate zeros. (The *truncation* half of `CHTB-5` did land, via `5ca453f`/`05a06a0`.)

---

## 5. Headline drift the plan does not know about

1. **`C16-2` is void.** `convertChartLayoutToPlotly` was never deleted; `f500d1f` took `CT-7` option (b).
2. **The three `fe-lint` type assertions are gone** — `fe-lint` is now **green (0 errors)**, so `CHTB-3`'s lint
   sub-item and `CT-12`'s "clear the lint errors" both need re-scoping.
3. **The plan's `H-1` coverage premise is obsolete.** `/frontend/coverage/` is now **untracked *and*
   gitignored** (`.gitignore:53`, anchored by `9d39218`). It is a normal build artefact, not a regression to
   restore; phase 13's `CT-15` "no block may restore `frontend/coverage/`" is meaningless now.
4. **`f500d1f` widened the `CHT-001` crash surface**: the new `data.length === 0` early return makes the line
   branch's `[0]` throw on any empty `data`, not only on an empty server response.
5. **The plan's test baseline is stale.** 24 files / **196 tests** now (not 13 / 170); `ChartRenderer.test.tsx`
   (5 tests) **is** chart-surface coverage the plan says does not exist. `LineChart.tsx` and `TableChart.tsx`
   appear in **no** coverage report (mocked everywhere) — zero coverage.
6. **`a3db812` made the `range` control accessible rather than removing it.** `CHTB-6` now has to *delete* a
   control someone just invested in labelling; `a3db812`'s 4 added lines will be reverted.
7. **`.ai/audit/` is effectively gone** — `d6505b1` committed the deletion; only `templates/` and `validated/`
   remain. Every anchor in the plan pointing at `.ai/audit/16-…/findings.md` and `.ai/audit/99-validation/16-…`
   is dangling.
8. **The brief's own premises are stale**: the "~50 pre-existing uncommitted deletions" were committed by
   `d6505b1`, and the 59 KB sibling `_code-context` file does exist.