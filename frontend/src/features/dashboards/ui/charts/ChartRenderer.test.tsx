import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import type { Data, Layout } from 'react-plotly.js'

// Spy components capture the props the renderer hands to Plotly, so the
// conversion can be asserted without mounting real Plotly. The spies are
// declared here and returned from the mock factories (hoisted by vitest).
const plotlySpy = vi.hoisted(() => vi.fn())
const lineSpy = vi.hoisted(() => vi.fn())

interface PlotProps {
  data?: Data[]
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

/**
 * Builds a graph fixture from the **server wire shape** for `data`: a list of
 * flat records, not Plotly traces. `GraphDataWithConfig.data` is declared as
 * `Data[]` in the peer-owned `api.types.ts`, so the wire shape is bridged here
 * with one documented cast at the fixture boundary. The production conversion
 * itself never casts — it narrows with `isChartRecord`.
 */
function makeGraph(overrides: Partial<GraphDataWithConfig> & { data?: unknown[] }): GraphDataWithConfig {
  const { data = [], ...rest } = overrides
  return {
    graph_id: 'g1',
    type: 'bar',
    name: 'Test',
    returned_rows: 0,
    total_rows: 0,
    rows_truncated: false,
    ...rest,
    data,
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

  it('merges the converted axis into a bar chart instead of replacing it', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          data: [{ category: 'A', revenue: 1 }],
          config: { x: 'category', metrics: ['revenue'] },
          layout: { xaxis: { title: 'Category', range: [0, 10] } },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    expect(lastPlotlyProps().layout).toEqual({
      xaxis: { type: 'category', title: { text: 'Category' }, range: [0, 10] },
      barmode: 'group',
    })
  })

  it('lets a converted axis type win and omits absent members', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          data: [{ category: 'A', revenue: 1 }],
          config: { x: 'category', metrics: ['revenue'] },
          layout: { xaxis: { type: 'linear' } },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    const axis = lastPlotlyProps().layout?.xaxis
    expect(axis?.type).toBe('linear')
    // The omission is pinned by the key set: keeping `title: undefined` /
    // `range: undefined` would leave those keys present and fail here.
    expect(Object.keys(axis ?? {})).toEqual(['type'])
  })

  it('hands LineChart exactly the converted layout with no re-stated defaults', async () => {
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
    // The declared title wins the spread; a re-stated `title: { text: '' }`
    // written before the spread would be caught by this whole-object compare.
    expect(layout).toEqual({
      title: { text: 'Trend' },
      xaxis: { title: { text: 'Period' }, type: 'category', range: [0, 10] },
    })
    // LineChart supplies its own defaults; re-declaring them here is the
    // mistake VAL-16-006 warns about, so their absence is the tripwire.
    expect(layout).not.toHaveProperty('xAxisLabel')
    expect(layout).not.toHaveProperty('yAxisLabel')
    expect(layout?.title).not.toHaveProperty('xAxisLabel')
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

  // --- R4: per-type trace shape and served-name consumption ---

  it('emits a pie trace with labels/values and no x/y', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'pie',
          data: [
            { category: 'A', revenue_sum: 3 },
            { category: 'B', revenue_sum: 7 },
          ],
          config: { x: 'category', metrics: ['revenue_sum'] },
          metrics: ['revenue_sum'],
          dimensions: ['category'],
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    const traces = lastPlotlyProps().data ?? []
    // Whole-trace compare pins labels[i]/values[i] pairing, not just presence.
    expect(traces).toEqual([
      { labels: ['A', 'B'], values: [3, 7], type: 'pie' },
    ])
    expect(traces[0]).not.toHaveProperty('x')
    expect(traces[0]).not.toHaveProperty('y')
  })

  it('resolves the served metric for a pie so its values are not all zero', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'pie',
          data: [
            { category: 'A', revenue_sum: 4 },
            { category: 'B', revenue_sum: 6 },
          ],
          config: { x: 'category', metrics: ['revenue'] },
          metrics: ['revenue_sum'],
          dimensions: ['category'],
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    const values = (lastPlotlyProps().data?.[0] as { values?: number[] }).values ?? []
    expect(Math.max(...values)).toBeGreaterThan(0)
  })

  it('resolves the served metric for a bar so y is not all zero', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'bar',
          data: [
            { category: 'A', revenue_sum: 5 },
            { category: 'B', revenue_sum: 8 },
          ],
          config: { x: 'category', metrics: ['revenue'] },
          metrics: ['revenue_sum'],
          dimensions: ['category'],
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    const y = (lastPlotlyProps().data?.[0] as { y?: number[] }).y ?? []
    expect(Math.max(...y)).toBeGreaterThan(0)
  })

  it('prefers a configured name that resolves over the first served name', async () => {
    // Precedence pin, passes before and after: guards a future
    // "served position 0 always wins" from discarding operator intent on a
    // multi-measure graph.
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'bar',
          data: [{ category: 'A', revenue: 11 }],
          config: { x: 'category', metrics: ['revenue'] },
          metrics: ['revenue'],
          dimensions: ['category'],
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    expect(lastPlotlyProps().data).toEqual([
      { x: ['A'], y: [11], type: 'bar', orientation: 'v' },
    ])
  })

  it('does not let an empty served list override a configured name', async () => {
    // Precedence pin, passes before and after: an empty served list carries no
    // authority. This decouples R6's empty/absent states from R4.
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'bar',
          data: [{ category: 'A', revenue: 9 }],
          config: { x: 'category', metrics: ['revenue'] },
          metrics: [],
          dimensions: [],
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('plotly')).toBeInTheDocument())
    expect(lastPlotlyProps().data).toEqual([
      { x: ['A'], y: [9], type: 'bar', orientation: 'v' },
    ])
  })

  it('renders one line per colour group instead of dropping all but the first', async () => {
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'line',
          data: [
            { period: 'P1', region: 'North', revenue: 1 },
            { period: 'P1', region: 'South', revenue: 2 },
            { period: 'P1', region: 'East', revenue: 3 },
          ],
          config: { x: 'period', color: 'region', metrics: ['revenue'] },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('line')).toBeInTheDocument())
    const data = lastLineProps().data ?? []
    expect(data).toHaveLength(3)
    expect(data.map((trace) => trace.name)).toEqual(['North', 'South', 'East'])
  })

  it('preserves the trace count and sorted name set across row order', async () => {
    const rows = [
      { period: 'P1', region: 'North', revenue: 1 },
      { period: 'P1', region: 'South', revenue: 2 },
    ] as unknown as Data[]
    const graph = (data: Data[]) =>
      makeGraph({
        type: 'line',
        data,
        config: { x: 'period', color: 'region', metrics: ['revenue'] },
      })

    render(<ChartRenderer graph={graph(rows)} />)
    await waitFor(() => expect(screen.getAllByTestId('line')).toHaveLength(1))
    const forward = lastLineProps().data ?? []

    render(<ChartRenderer graph={graph([...rows].reverse())} />)
    await waitFor(() => expect(screen.getAllByTestId('line')).toHaveLength(2))
    const reversed = lastLineProps().data ?? []

    expect(forward).toHaveLength(2)
    expect(reversed).toHaveLength(2)
    // Never assert an identical first trace: groupByColor follows first-seen
    // order, so a reversed fixture reverses the trace order.
    expect([...forward.map((t) => t.name)].sort()).toEqual(
      [...reversed.map((t) => t.name)].sort(),
    )
  })

  it('does not throw on empty data and never reaches either chart', () => {
    // Tripwire, passes before and after: ChartRenderer's length guard fires
    // first. It fails if the branch order changes or the [0] returns.
    expect(() =>
      render(
        <ChartRenderer
          graph={makeGraph({ type: 'line', data: [], config: { x: 'x', metrics: ['y'] } })}
        />,
      ),
    ).not.toThrow()
    expect(screen.getByText('No data available for this chart')).toBeInTheDocument()
    expect(lineSpy).not.toHaveBeenCalled()
    expect(plotlySpy).not.toHaveBeenCalled()
  })

  it('hands LineChart exactly data and layout, no re-stated defaults as props', async () => {
    // Props-level VAL-16-006 tripwire: R2's shipped check inspects props.layout
    // and would miss <LineChart xAxisLabel="Category" />, the idiomatic way to
    // write the mistake. The key set is the whole contract.
    render(
      <ChartRenderer
        graph={makeGraph({
          type: 'line',
          data: [{ period: 'P1', revenue: 1 }],
          config: { x: 'period', metrics: ['revenue'] },
        })}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('line')).toBeInTheDocument())
    expect(Object.keys(lastLineProps()).sort()).toEqual(['data', 'layout'])
  })
})
