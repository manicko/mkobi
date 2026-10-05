import { PlotlyChart } from './PlotlyChart'
import type { Data, Layout } from 'react-plotly.js'

interface LineChartProps {
  data: Data[]
  layout?: Partial<Layout>
}

export function LineChart({ data, layout }: LineChartProps) {
  return <PlotlyChart data={data} layout={layout} />
}
