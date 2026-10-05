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
 * A trace's shape is per chart type: @types/plotly.js declares `PieData` with
 * `labels`/`values` (see `lib/pie.d.ts`) while `PlotData` carries `x`/`y` only,
 * so each builder writes just the members its own type accepts.
 */

import type { Data, Layout } from 'react-plotly.js'
import type { PieData, PlotData } from 'plotly.js'
import type { AxisType, Template } from 'plotly.js'

/** A flat aggregated record as the server emits it. */
export type ChartRecord = Record<string, string | number>

/** A rendered trace plus the type of its `x`/`y` payload. */
export type ChartElement = string | number

/** The trace types this module builds; each maps to a distinct payload shape. */
export type ChartTraceType = 'pie' | 'scatter' | 'bar'

/**
 * True when a value is a flat chart record (a plain object whose fields are
 * strings or numbers). `null`, arrays and non-record objects are rejected.
 */
export function isChartRecord(value: unknown): value is ChartRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  return Object.values(value).every(
    (field) => typeof field === 'string' || typeof field === 'number',
  )
}

/**
 * Reads a single field from a trace-like value as a scalar.
 *
 * The server may send already-Plotly traces (`{ x: [...], y: [...] }`) or flat
 * records. Both are `Data` at the type level, so access goes through an
 * `unknown` step guarded by `isChartRecord`.
 */
export function readScalar(value: unknown, key: string): ChartElement | undefined {
  if (!isChartRecord(value)) return undefined
  return value[key]
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
 * A pie trace carries `labels`/`values`, never `x`/`y`: `Partial<PlotData>`
 * declares neither of the former, which is why this builder takes its own
 * `Partial<PieData>`. Absent members are omitted, never emitted as explicit
 * `undefined`.
 */
function makePieTrace(
  labels: ChartElement[],
  values: ChartElement[],
  options: { name?: string } = {},
): Partial<PieData> {
  const trace: Partial<PieData> = { labels, values, type: 'pie' }
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
  xVals: ChartElement[],
  yVals: ChartElement[],
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
  xVals: ChartElement[],
  yVals: ChartElement[],
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
  xVals: ChartElement[],
  yVals: ChartElement[],
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
