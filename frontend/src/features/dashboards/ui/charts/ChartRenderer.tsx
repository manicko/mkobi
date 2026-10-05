import { PlotlyChart } from './PlotlyChart'
import { LineChart } from './LineChart'
import { TableChart } from './TableChart'
import type { GraphDataWithConfig, ChartLayoutConfig } from '../../../../shared/types/api.types'
import { BarmodeEnum } from '../../../../shared/types/enums'
import type { Data, Layout } from 'react-plotly.js'
import {
  makeTrace,
  readScalar,
  toLabelValue,
  toLayoutAxis,
  toLayoutTemplate,
  toMeasureValue,
  toOrientation,
  type ChartMeasure,
  type ChartLabel,
  type ChartTraceType,
} from './chartConversion'
import {
  NO_ROWS_MESSAGE,
  resolveColumnName,
  resolveMeasureColumn,
} from './chartStates'

interface ChartRendererProps {
  graph: GraphDataWithConfig
}

/**
 * True when the server already sent Plotly-shaped traces (`x`/`y` present on
 * the first record) rather than flat aggregated records.
 */
function isPlotlyShaped(data: Data[]): boolean {
  const first: unknown = data[0]
  return 'x' in Object(first) && 'y' in Object(first)
}

function traceTypeFor(graphType: GraphDataWithConfig['type']): ChartTraceType {
  if (graphType === 'pie') return 'pie'
  if (graphType === 'line') return 'scatter'
  return 'bar'
}

function collectSeries(
  records: Data[],
  xCol: string,
  metricCol: string,
): { xVals: ChartLabel[]; yVals: ChartMeasure[] } {
  const xVals: ChartLabel[] = []
  const yVals: ChartMeasure[] = []
  for (const record of records) {
    xVals.push(toLabelValue(readScalar(record, xCol)))
    yVals.push(toMeasureValue(readScalar(record, metricCol)))
  }
  return { xVals, yVals }
}

function groupByColor(
  records: Data[],
  colorCol: string,
  xCol: string,
  metricCol: string,
): Map<string, { x: ChartLabel[]; y: ChartMeasure[] }> {
  const groups = new Map<string, { x: ChartLabel[]; y: ChartMeasure[] }>()
  for (const record of records) {
    const colorValue = readScalar(record, colorCol)
    const color = colorValue === undefined || colorValue === null ? 'unknown' : String(colorValue)
    const group = groups.get(color) ?? { x: [], y: [] }
    group.x.push(toLabelValue(readScalar(record, xCol)))
    group.y.push(toMeasureValue(readScalar(record, metricCol)))
    groups.set(color, group)
  }
  return groups
}

function convertToPlotlyData(graph: GraphDataWithConfig): Data[] {
  const config = graph.config ?? {}
  // Served names win over the operator's pre-alias guess: the served list is a
  // union of every emitted key, so a configured name that resolves is the
  // operator's own pick, and an unresolved one falls back to the first served
  // name rather than a column that is not on the rows.
  const xCol = resolveColumnName(config.x, graph.dimensions) ?? graph.dimensions?.[0] ?? 'x'
  const colorCol = resolveColumnName(config.color, graph.dimensions)
  // The same resolution the state predicate reads, so the trace and the
  // classification can never disagree about which column is the measure.
  const metricCol = resolveMeasureColumn(graph) ?? 'y'
  const orientation = config.orientation ?? 'v'
  const traceType = traceTypeFor(graph.type)

  if (graph.data.length === 0) return []

  // Already Plotly-shaped: the server sent traces, not flat records.
  if (isPlotlyShaped(graph.data) && !colorCol) {
    return graph.data
  }

  if (colorCol) {
    const groups = groupByColor(graph.data, colorCol, xCol, metricCol)
    return [...groups.entries()].map(([name, series]) =>
      makeTrace(traceType, series.x, series.y, { name }),
    )
  }

  const { xVals, yVals } = collectSeries(graph.data, xCol, metricCol)
  return [
    makeTrace(traceType, xVals, yVals, {
      orientation: graph.type === 'bar' ? toOrientation(orientation) : undefined,
      mode: graph.type === 'line' ? 'lines' : undefined,
    }),
  ]
}

/**
 * Converts ChartLayoutConfig to Plotly's Layout format.
 */
function convertChartLayoutToPlotly(
  layout: ChartLayoutConfig | undefined,
): Partial<Layout> | undefined {
  if (!layout) return undefined

  const plotLayout: Partial<Layout> = {}

  if (layout.title !== undefined) {
    plotLayout.title = { text: layout.title }
  }
  if (layout.xaxis) {
    plotLayout.xaxis = toLayoutAxis(layout.xaxis)
  }
  if (layout.yaxis) {
    plotLayout.yaxis = toLayoutAxis(layout.yaxis)
  }
  if (layout.showlegend !== undefined) {
    plotLayout.showlegend = layout.showlegend
  }
  if (layout.height !== undefined) {
    plotLayout.height = layout.height
  }
  if (layout.width !== undefined) {
    plotLayout.width = layout.width
  }
  if (layout.template !== undefined) {
    plotLayout.template = toLayoutTemplate(layout.template)
  }

  return plotLayout
}

export function ChartRenderer({ graph }: ChartRendererProps) {
  // Table charts render as native HTML tables (no Plotly conversion)
  if (graph.type === 'table') {
    return <TableChart data={{ rows: graph.data }} />
  }

  if (graph.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        {NO_ROWS_MESSAGE}
      </div>
    )
  }

  if (graph.type === 'line') {
    return (
      <LineChart
        data={convertToPlotlyData(graph)}
        layout={convertChartLayoutToPlotly(graph.layout)}
      />
    )
  }

  const plotlyData = convertToPlotlyData(graph)

  if (graph.type === 'bar') {
    const convertedLayout = convertChartLayoutToPlotly(graph.layout)
    const barLayout: Partial<Layout> = {
      ...convertedLayout,
      barmode: graph.config?.barmode ?? BarmodeEnum.GROUP,
      xaxis: { type: 'category', ...convertedLayout?.xaxis },
    }
    return <PlotlyChart data={plotlyData} layout={barLayout} />
  }

  return <PlotlyChart data={plotlyData} layout={convertChartLayoutToPlotly(graph.layout)} />
}
