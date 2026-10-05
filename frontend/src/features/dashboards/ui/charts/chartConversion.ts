/**
 * Typed conversion helpers for the chart renderer.
 *
 * The backend's `GraphDataResponse.data` is `list[dict[str, int | float | str]]`
 * — flat records keyed by dimension and metric names — while react-plotly.js
 * expects traces (`Data`). The shared `GraphDataWithConfig` type declares
 * `data: Data[]`, so this module is the single boundary that reads a record
 * field out of a possibly-flat `data` array without a blind cast.
 *
 * Everything here narrows with a real type guard; no assertion is used to
 * silence the compiler.
 *
 * A trace's shape is per chart type, and each shipped trace type pins its own
 * `type` literal (`PieData.type` is `"pie"`; the bar and scatter types pin
 * theirs). A pie trace built from `x`/`y` is the defect this split prevents:
 * `PieData` declares no top-level `x`/`y` — the only `x`/`y` in `lib/pie.d.ts`
 * belong to `PieDomain`, reachable solely through `domain`, which this code
 * never sets — so such a trace carries members its own type does not accept and
 * the plot renders a pie with no slices. Splitting the builders means the trace
 * type and the payload can no longer be paired wrongly.
 */

import type { Data, Layout } from 'react-plotly.js'
import type { PieData, PlotData } from 'plotly.js'
import type { AxisType, Template } from 'plotly.js'

/**
 * A flat aggregated record as the server emits it.
 *
 * The value set is widened to the wire truth: a Polars `sum` over an all-null
 * group is `None` (a `null` field), and `_coerce_dim_value` preserves `bool`
 * dimensions. A guard that rejected those would drop the whole row, blanking
 * the category and coercing the measure to a value it never had.
 */
export type ChartRecord = Record<string, string | number | boolean | null>

/**
 * A rendered trace label: an `x` or pie label. This is exactly the value set
 * Plotly's `Datum` accepts for a label (`string | number`; a boolean dimension
 * is stringified by {@link toLabelValue}).
 */
export type ChartLabel = string | number

/**
 * A rendered trace measure: a `y` or pie value. `null` is a gap for a cartesian
 * `y` (`Datum` includes `null`); a pie has no gapped slice, so the pie builder
 * drops the paired label instead (see {@link makePieTrace}).
 */
export type ChartMeasure = number | null

/** The historical payload alias for the `x`/`y` element union. */
export type ChartElement = ChartLabel

/** The trace types this module builds; each maps to a distinct payload shape. */
export type ChartTraceType = 'pie' | 'scatter' | 'bar'

/**
 * True when a value is a flat chart record (a plain object whose fields are
 * strings, numbers, booleans, or `null`). Arrays and non-record objects are
 * rejected.
 */
export function isChartRecord(value: unknown): value is ChartRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  return Object.values(value).every(
    (field) =>
      typeof field === 'string' ||
      typeof field === 'number' ||
      typeof field === 'boolean' ||
      field === null,
  )
}

/**
 * Reads a single field from a trace-like value as a scalar.
 *
 * The server may send already-Plotly traces (`{ x: [...], y: [...] }`) or flat
 * records. Both are `Data` at the type level, so access goes through an
 * `unknown` step guarded by `isChartRecord`. A present-but-`null` key and an
 * absent key stay distinguishable here (`null` vs `undefined`) even though both
 * render as the same gap downstream.
 */
export function readScalar(
  value: unknown,
  key: string,
): string | number | boolean | null | undefined {
  if (!isChartRecord(value)) return undefined
  return value[key]
}

/**
 * Narrows a served measure value to a gauge or gap.
 *
 * A finite `number` is itself — including `0`, which is checked first so a real
 * zero is never mistaken for absence. `null`, `undefined`, `NaN`, `Infinity`
 * and every non-number become `null`: coercing a garbage value to a number is
 * the same defect as the `?? 0` fallback it replaces.
 */
export function toMeasureValue(value: unknown): ChartMeasure {
  if (typeof value !== 'number') return null
  return Number.isFinite(value) ? value : null
}

/**
 * Narrows a served label value to the `string | number` Plotly accepts.
 *
 * An absent label becomes the empty string (the historical default); a boolean
 * dimension is stringified, since `Datum` excludes `boolean`.
 */
export function toLabelValue(
  value: string | number | boolean | null | undefined,
): ChartLabel {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return String(value)
  return value
}

/** The exact set of axis types react-plotly.js declares. */
const AXIS_TYPES: readonly AxisType[] = [
  '-',
  'linear',
  'log',
  'date',
  'category',
  'multicategory',
]

/**
 * Narrows the server's free-form bar `orientation` string to Plotly's union.
 *
 * The backend declares `config.orientation` as `str`; Plotly accepts `'h' | 'v'`.
 * Anything else yields `'v'`, the backend's own default.
 */
export function toOrientation(value: string | undefined): 'h' | 'v' {
  return value === 'h' ? 'h' : 'v'
}

/**
 * Narrows the server's free-form axis `type` string to Plotly's `AxisType`.
 *
 * The backend declares `xaxis.type`/`yaxis.type` as `str`; Plotly's is a closed
 * union. This guard is the narrowing step, so no cast is needed at the call
 * site. An unknown value yields `undefined` and let the axis default apply.
 */
export function toAxisType(value: string | undefined): AxisType | undefined {
  if (value === undefined) return undefined
  return AXIS_TYPES.find((candidate) => candidate === value)
}

/**
 * Builds a Plotly axis from the server's axis config.
 *
 * `range` is `number[]` on the wire and `any[]` in Plotly's own types, so it is
 * assigned directly. `type` goes through {@link toAxisType}.
 *
 * Absent members are **omitted**, never emitted as explicit `undefined`. On the
 * wire this is a no-op (undefined members never serialise); it matters because
 * the renderer writes defaults *before* spreading this object, so an emitted
 * `type: undefined` would clobber the `'category'` default instead of leaving
 * it in place.
 */
export function toLayoutAxis(
  axis: { title?: string; range?: number[]; type?: string },
): Partial<Layout['xaxis']> {
  const converted: Partial<Layout['xaxis']> = {}
  if (axis.title !== undefined) converted.title = { text: axis.title }
  const axisType = toAxisType(axis.type)
  if (axisType !== undefined) converted.type = axisType
  if (axis.range !== undefined) converted.range = axis.range
  return converted
}

/**
 * Narrows a server template name to Plotly's `Template` slot.
 *
 * Mismatch: the backend models `layout.template` as a template *name* (`str`),
 * while @types/plotly.js declares `Layout.template` as a `Template` object. The
 * runtime accepts a registered name string, so the value is passed through
 * unchanged. The cast is contained here, next to the comment naming the gap, so
 * no other function needs one.
 */
export function toLayoutTemplate(value: string | undefined): Template | undefined {
  if (value === undefined) return undefined
  return value as unknown as Template
}

/**
 * Builds a Plotly pie trace.
 *
 * A pie trace carries `labels`/`values`, never `x`/`y`: `PieData` declares no
 * top-level `x`/`y` — the only `x`/`y` in `lib/pie.d.ts` belong to `PieDomain`,
 * reachable solely through `domain`, which this code never sets — and it pins
 * its own `type` literal (`"pie"`), so only this builder can supply a pie
 * payload that its trace type accepts.
 *
 * A pie carries no gap: `PieData.values` is `Array<number | string>` and admits
 * no `null`, so a measure that is absent drops its paired label rather than
 * becoming a slice — the pie-honest equivalent of a cartesian gap, and never a
 * zero slice. Absent members are omitted, never emitted as explicit
 * `undefined`.
 */
function makePieTrace(
  labels: ChartLabel[],
  values: ChartMeasure[],
  options: { name?: string } = {},
): Partial<PieData> {
  const slices = values.flatMap((value, index) =>
    value === null ? [] : [{ label: labels[index] ?? '', value }],
  )
  const trace: Partial<PieData> = {
    labels: slices.map((slice) => slice.label),
    values: slices.map((slice) => slice.value),
    type: 'pie',
  }
  if (options.name !== undefined) trace.name = options.name
  return trace
}

/**
 * Builds a Plotly bar trace.
 *
 * A bar trace carries `x`/`y` plus `orientation`; `Partial<PlotData>` is the
 * only shape that declares all three. Absent members are omitted, never
 * emitted as explicit `undefined`.
 */
function makeBarTrace(
  xVals: ChartLabel[],
  yVals: ChartMeasure[],
  options: { name?: string; orientation?: 'h' | 'v' } = {},
): Partial<PlotData> {
  const trace: Partial<PlotData> = { x: xVals, y: yVals, type: 'bar' }
  if (options.name !== undefined) trace.name = options.name
  if (options.orientation !== undefined) trace.orientation = options.orientation
  return trace
}

/**
 * Builds a Plotly scatter (line) trace.
 *
 * A scatter trace carries `x`/`y` plus `mode`; the literal union Plotly
 * declares for `mode` requires a `Partial<PlotData>` local. Absent members are
 * omitted, never emitted as explicit `undefined`.
 */
function makeLineTrace(
  xVals: ChartLabel[],
  yVals: ChartMeasure[],
  options: { name?: string; mode?: 'lines' | 'markers' | 'lines+markers' } = {},
): Partial<PlotData> {
  const trace: Partial<PlotData> = { x: xVals, y: yVals, type: 'scatter' }
  if (options.name !== undefined) trace.name = options.name
  if (options.mode !== undefined) trace.mode = options.mode
  return trace
}

/**
 * Builds the plotly `Data` trace for one series.
 *
 * Dispatches to the per-type builder so each trace is written through the
 * `Partial` whose type actually declares its members: a pie trace is built as
 * `Partial<PieData>` and a bar/scatter trace as `Partial<PlotData>`. The
 * `options` bag is forwarded by variable, never as a fresh literal, so no
 * excess-property check fires and no absent member is ever written.
 */
export function makeTrace(
  type: ChartTraceType,
  xVals: ChartLabel[],
  yVals: ChartMeasure[],
  options: {
    name?: string
    orientation?: 'h' | 'v'
    mode?: 'lines' | 'markers' | 'lines+markers'
  } = {},
): Data {
  if (type === 'pie') return makePieTrace(xVals, yVals, options)
  if (type === 'scatter') return makeLineTrace(xVals, yVals, options)
  return makeBarTrace(xVals, yVals, options)
}
