import { describe, it, expect } from 'vitest'
import type {
  AggregatedDataResponse,
  GraphDataWithConfig,
} from '../../../../shared/types/api.types'
import {
  DashboardDataState,
  GraphRenderState,
  classifyDashboard,
  classifyGraph,
  hasAbsentMeasure,
} from './chartStates'

/**
 * Builds a graph fixture from the **server wire shape** for `data`: a list of
 * flat records, not Plotly traces. `GraphDataWithConfig.data` is declared as
 * `Data[]`, so the wire shape is bridged here with one documented cast at the
 * fixture boundary; the production classifiers never cast.
 */
function makeGraph(
  overrides: Partial<GraphDataWithConfig> & { data?: unknown[] } = {},
): GraphDataWithConfig {
  const { data = [], ...rest } = overrides
  return {
    graph_id: 'g1',
    type: 'bar',
    name: 'Test',
    returned_rows: data.length,
    total_rows: data.length,
    rows_truncated: false,
    ...rest,
    data,
  }
}

function makeResponse(graphs: GraphDataWithConfig[]): AggregatedDataResponse {
  return { graphs, total_rows: 0, truncated: false }
}

describe('chartStates', () => {
  it('classifies an empty graph list as NO_CHARTS and no graph state applies', () => {
    const response = makeResponse([])
    expect(classifyDashboard(response)).toBe(DashboardDataState.NO_CHARTS)
    // There is no graph to classify: the dashboard state names the whole graph
    // list being empty, which is the only signal for this state.
    expect(response.graphs).toHaveLength(0)
  })

  it('classifies a graph with no rows as NO_ROWS, not MEASURE_ABSENT or RENDERED', () => {
    const graph = makeGraph({ data: [], metrics: ['revenue'] })
    expect(classifyGraph(graph)).toBe(GraphRenderState.NO_ROWS)
    expect(classifyGraph(graph)).not.toBe(GraphRenderState.MEASURE_ABSENT)
    expect(classifyGraph(graph)).not.toBe(GraphRenderState.RENDERED)
  })

  it('classifies rows carrying only the dimension as MEASURE_ABSENT', () => {
    const graph = makeGraph({
      data: [{ category: 'A' }, { category: 'B' }],
      metrics: ['revenue'],
      dimensions: ['category'],
      config: { x: 'category', metrics: ['revenue'] },
    })
    expect(classifyGraph(graph)).toBe(GraphRenderState.MEASURE_ABSENT)
    expect(classifyGraph(graph)).not.toBe(GraphRenderState.NO_ROWS)
    expect(classifyGraph(graph)).not.toBe(GraphRenderState.RENDERED)
    expect(hasAbsentMeasure(graph)).toBe(true)
  })

  it('classifies a present-zero measure as RENDERED, not MEASURE_ABSENT', () => {
    // The discriminator for the whole block: today this row is indistinguishable
    // from an absent one, because a `0` and a missing key both rendered as `0`.
    const graph = makeGraph({
      data: [{ category: 'A', revenue: 0 }],
      metrics: ['revenue'],
      dimensions: ['category'],
      config: { x: 'category', metrics: ['revenue'] },
    })
    expect(classifyGraph(graph)).toBe(GraphRenderState.RENDERED)
    expect(classifyGraph(graph)).not.toBe(GraphRenderState.MEASURE_ABSENT)
    expect(hasAbsentMeasure(graph)).toBe(false)
  })

  it('is pairwise exclusive across one fixture per graph state', () => {
    const fixtures: Array<{ state: GraphRenderState; graph: GraphDataWithConfig }> = [
      {
        state: GraphRenderState.NO_ROWS,
        graph: makeGraph({ data: [], metrics: ['revenue'] }),
      },
      {
        state: GraphRenderState.MEASURE_ABSENT,
        graph: makeGraph({ data: [{ category: 'A' }], metrics: ['revenue'] }),
      },
      {
        state: GraphRenderState.RENDERED,
        graph: makeGraph({ data: [{ category: 'A', revenue: 0 }], metrics: ['revenue'] }),
      },
    ]
    for (const { state } of fixtures) {
      const matches = fixtures.filter((fixture) => classifyGraph(fixture.graph) === state)
      expect(matches).toHaveLength(1)
    }
  })
})
