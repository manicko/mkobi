/**
 * The dashboard chart state vocabulary and the served-column resolution.
 *
 * The server serves a graph list whose rows may be non-empty while the measure
 * column the chart reads is *not* on those rows. Such a chart used to draw a
 * flat zero, indistinguishable from a genuine zero. This module names that
 * state, the state it is not, and the single resolution rule the predicate and
 * the trace must agree on — so a chart cannot claim one column and draw another.
 *
 * The definitions live here, in the dashboards feature, because only this
 * feature consumes them; `model/` cannot own them (the predicate needs the
 * chart-record reader that lives in `ui/charts/`), and `shared/` would be a
 * speculative widening for a feature-local vocabulary.
 *
 * State families use the project's `as const` object idiom, matching
 * `shared/types/enums.ts`: TypeScript `enum` is banned by `erasableSyntaxOnly`.
 */

import type {
  AggregatedDataResponse,
  GraphDataWithConfig,
} from '../../../../shared/types/api.types'
import { isChartRecord, readScalar } from './chartConversion'

/** The chart states a single graph can be in. */
export const GraphRenderState = {
  /** The server served a graph but no rows for it. */
  NO_ROWS: 'NO_ROWS',
  /** Rows exist, but the resolved measure column is absent from all of them. */
  MEASURE_ABSENT: 'MEASURE_ABSENT',
  /** Rows exist and at least one carries a value in the measure column. */
  RENDERED: 'RENDERED',
} as const

export type GraphRenderState = (typeof GraphRenderState)[keyof typeof GraphRenderState]

/** The dashboard-level states over the whole served graph list. */
export const DashboardDataState = {
  /** The server served an empty graph list. */
  NO_CHARTS: 'NO_CHARTS',
  /** The server served at least one graph. */
  RENDERED: 'RENDERED',
} as const

export type DashboardDataState = (typeof DashboardDataState)[keyof typeof DashboardDataState]

/** Shown when the dashboard has no graphs at all. */
export const NO_CHARTS_MESSAGE = 'This dashboard has no charts to display.'

/** Shown when a graph exists but the server served no rows for it. */
export const NO_ROWS_MESSAGE = 'No data available for this chart'

/** Shown per graph when rows exist but the resolved measure is not among them. */
export const MEASURE_ABSENT_MESSAGE =
  'The measure "{column}" is not in the served data, so this chart shows a gap instead of a value.'

/** Shown once at dashboard scope when any graph's measure is absent. */
export const DASHBOARD_MEASURE_ABSENT_MESSAGE =
  'One or more charts have a measure that is not in the served data. Those charts are drawn as gaps, not zeros.'

/** Shown at dashboard scope when retained data could not be refreshed. */
export const STALE_DATA_MESSAGE = 'Data may be out of date — last updated {time}'

/** The table's counterpart of a chart gap. */
export const ABSENT_CELL_MARKER = '—'

/**
 * Resolves an operator-configured column name against the served column names.
 *
 * Precedence: the served names are keys on served rows by construction, while
 * the configured names are the operator's pre-alias guess — a guess that misses
 * zeroes the measure. So a configured name that is also served wins (operator
 * intent survives on a multi-measure graph), an absent/empty served list is no
 * authority at all and the configured name stands, and anything else is
 * unresolved.
 */
export function resolveColumnName(
  configured: string | undefined,
  served: string[] | undefined,
): string | undefined {
  if (served === undefined || served.length === 0) return configured
  if (configured !== undefined && served.includes(configured)) return configured
  return undefined
}

/** The measure column the chart reads for one graph; `undefined` when none resolves. */
export function resolveMeasureColumn(graph: GraphDataWithConfig): string | undefined {
  return resolveColumnName(graph.config?.metrics?.[0], graph.metrics) ?? graph.metrics?.[0]
}

/** True when a value read off a row is absent (never a real `0` or `''`). */
export function isAbsentValue(value: unknown): boolean {
  return value === null || value === undefined
}

/** Classifies the dashboard-level state over the served graph list. */
export function classifyDashboard(response: AggregatedDataResponse): DashboardDataState {
  return response.graphs.length === 0 ? DashboardDataState.NO_CHARTS : DashboardDataState.RENDERED
}

/**
 * Classifies one graph by its served rows and resolved measure column.
 *
 * A present-but-`0` measure is `RENDERED`, never `MEASURE_ABSENT`: the whole
 * point of the state is that a value is present, whatever it is.
 */
export function classifyGraph(graph: GraphDataWithConfig): GraphRenderState {
  if (graph.data.length === 0) return GraphRenderState.NO_ROWS
  const measureColumn = resolveMeasureColumn(graph)
  if (measureColumn === undefined) return GraphRenderState.NO_ROWS
  const hasValue = graph.data.some(
    (row) => isChartRecord(row) && readScalar(row, measureColumn) !== undefined,
  )
  return hasValue ? GraphRenderState.RENDERED : GraphRenderState.MEASURE_ABSENT
}

/** True when a graph has rows but its resolved measure is absent from all of them. */
export function hasAbsentMeasure(graph: GraphDataWithConfig): boolean {
  return classifyGraph(graph) === GraphRenderState.MEASURE_ABSENT
}
