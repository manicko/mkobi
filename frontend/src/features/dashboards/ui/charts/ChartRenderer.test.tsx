import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import type { Data, Layout } from 'react-plotly.js'

// Spy components capture the props the renderer hands to Plotly, so the
// conversion can be asserted without mounting real Plotly. The spies are
// declared here and returned from the mock factories (hoisted by vitest).
const plotlySpy = vi.hoisted(() => vi.fn())
const lineSpy = vi.hoisted(() => vi.fn())

interface PlotProps {
  data?: Data | Data[]
  layout?: Partial<Layout>
}

vi.mock('./PlotlyChart', () => ({
  PlotlyChart: (props: PlotProps) => {
    plotlySpy(props)
    return <div data-testid="plotly" />
  },
}))
vi.mock('./LineChart', () => ({
  LineChart: (props: PlotProps) => {
    lineSpy(props)
    return <div data-testid="line" />
  },
}))
vi.mock('./TableChart', () => ({ TableChart: () => <div data-testid="table" /> }))

import { ChartRenderer } from './ChartRenderer'
import type { GraphDataWithConfig } from '../../../../shared/types/api.types'

function makeGraph(overrides: Partial<GraphDataWithConfig>): GraphDataWithConfig {
  return {
    graph_id: 'g1',
    type: 'bar',
    name: 'Test',
    data: [],
    returned_rows: 0,
    total_rows: 0,
    rows_truncated: false,
    ...overrides,
  }
}

function lastPlotlyProps(): PlotProps {
  const call = plotlySpy.mock.calls.at(-1)
  return (call?.[0] as PlotProps | undefined) ?? {}
}

function lastLineProps(): PlotProps {
  const call = lineSpy.mock.calls.at(-1)
  return (call?.[0] as PlotProps | undefined) ?? {}
}

describe('ChartRenderer', () => {
  beforeEach(() => {
    plotlySpy.mockClear()
    lineSpy.mockClear()
  })

  it('renders a flat-record single series as one trace', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          data: [{ category: 'A', revenue: 10 }, { category: 'B', revenue: 20 }],
          config: { x: 'category', metrics: ['revenue'] },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    expect(lastPlotlyProps().data).toEqual([
      { x: ['A', 'B'], y: [10, 20], type: 'bar', orientation: 'v' },
    ])
  })

  it('renders a multi-trace grouped series when a color column is declared', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          data: [
            { category: 'A', year: '2023', revenue: 10 },
            { category: 'A', year: '2024', revenue: 15 },
          ],
          config: { x: 'category', color: 'year', metrics: ['revenue'] },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    expect(lastPlotlyProps().data).toEqual([
      { x: ['A'], y: [10], type: 'bar', name: '2023' },
      { x: ['A'], y: [15], type: 'bar', name: '2024' },
    ])
  })

  it('passes already-Plotly-shaped data through unchanged', async () => {
    const trace: Data = { x: ['A'], y: [1], type: 'bar' }
    render(
      <ChartRenderer graph={makeGraph({ data: [trace], config: { x: 'x', metrics: ['y'] } })} />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    expect(lastPlotlyProps().data).toEqual([trace])
  })

  it('honours the declared axis vocabulary without asserting the type', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'line',
          data: [{ x: 'A', y: 1 }],
          config: { x: 'x', metrics: ['y'] },
          layout: {
            title: 'Trend',
            xaxis: { title: 'Period', type: 'category', range: [0, 10] },
          },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('line')).toBeInTheDocument())
    const layout = lastLineProps().layout
    expect(layout?.title).toEqual({ text: 'Trend' })
    expect(layout?.xaxis?.type).toBe('category')
    expect(layout?.xaxis?.range).toEqual([0, 10])
  })

  it('drops an unknown axis type rather than forcing it through', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'line',
          data: [{ x: 'A', y: 1 }],
          config: { x: 'x', metrics: ['y'] },
          layout: { xaxis: { type: 'not-a-plotly-axis' } },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('line')).toBeInTheDocument())
    expect(lastLineProps().layout?.xaxis?.type).toBeUndefined()
  })
})
