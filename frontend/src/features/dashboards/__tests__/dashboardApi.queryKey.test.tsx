import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { AggregatedDataResponse } from '../../../shared/types/api.types'

// The aggregated-data cache key must include the graph id. Two per-graph
// fetches for one dashboard with identical filters must land on two distinct
// cache entries; otherwise the second graph renders the first graph's data.

const { aggregatedGet } = vi.hoisted(() => ({
  aggregatedGet: vi.fn<
    (url: string, config: { params: { graph_id?: string } }) => Promise<{
      data: AggregatedDataResponse
    }>
  >(),
}))

vi.mock('../../../shared/api/axiosInstance', () => ({
  default: {
    get: (url: string, config: { params: { graph_id?: string } }) =>
      aggregatedGet(url, config),
  },
}))

vi.mock('../../auth/model/authToken', () => ({
  useAuthToken: () => 'test-token',
}))

import { useAggregatedData } from '../api/dashboardApi'

function renderProbe(children: ReactNode, queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

function AggregatedProbe({
  dashboardId,
  filters,
  graphId,
}: {
  dashboardId: string
  filters: Record<string, string | string[] | number | number[]>
  graphId: string
}) {
  useAggregatedData(dashboardId, filters, graphId)
  return null
}

function NoGraphProbe({
  dashboardId,
  filters,
}: {
  dashboardId: string
  filters: Record<string, string | string[] | number | number[]>
}) {
  useAggregatedData(dashboardId, filters)
  return null
}

describe('useAggregatedData cache key', () => {
  beforeEach(() => {
    aggregatedGet.mockReset()
    aggregatedGet.mockImplementation(
      (_url: string, config: { params: { graph_id?: string } }) => {
        const graphId = config.params.graph_id
        return Promise.resolve({
          data: {
            graphs: [
              {
                graph_id: graphId ?? 'no-graph',
                type: 'bar',
                name: `Graph ${graphId ?? 'none'}`,
                data: [{ x: [graphId ?? 'none'], y: [1], type: 'bar' }],
                returned_rows: 1,
                total_rows: 1,
                rows_truncated: false,
              },
            ],
            total_rows: 1,
            truncated: false,
          },
        })
      }
    )
  })

  it('keys two per-graph fetches for one dashboard on distinct cache entries', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const filters = { region: 'North' }

    renderProbe(
      <>
        <AggregatedProbe dashboardId="dash-1" filters={filters} graphId="graph-a" />
        <AggregatedProbe dashboardId="dash-1" filters={filters} graphId="graph-b" />
      </>,
      queryClient
    )

    await waitFor(() => {
      expect(aggregatedGet).toHaveBeenCalledTimes(2)
    })

    const aggregatedEntries = queryClient
      .getQueryCache()
      .findAll({ queryKey: ['aggregatedData', 'dash-1'] })

    // Two distinct graphs must occupy two distinct cache entries.
    expect(aggregatedEntries).toHaveLength(2)

    const graphA = aggregatedEntries.find((entry) =>
      JSON.stringify(entry.queryKey).includes('graph-a')
    )
    const graphB = aggregatedEntries.find((entry) =>
      JSON.stringify(entry.queryKey).includes('graph-b')
    )

    expect(graphA).toBeDefined()
    expect(graphB).toBeDefined()

    // Each entry must retain its own response, not the other graph's data.
    expect(graphA?.state.data).toMatchObject({
      graphs: [{ graph_id: 'graph-a' }],
    })
    expect(graphB?.state.data).toMatchObject({
      graphs: [{ graph_id: 'graph-b' }],
    })
  })

  it('keeps the absent-graph key unambiguous against a present graph id', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const filters = { region: 'North' }

    renderProbe(
      <>
        <AggregatedProbe dashboardId="dash-1" filters={filters} graphId="graph-a" />
        <NoGraphProbe dashboardId="dash-1" filters={filters} />
      </>,
      queryClient
    )

    await waitFor(() => {
      expect(aggregatedGet).toHaveBeenCalledTimes(2)
    })

    const aggregatedEntries = queryClient
      .getQueryCache()
      .findAll({ queryKey: ['aggregatedData', 'dash-1'] })

    expect(aggregatedEntries).toHaveLength(2)
  })
})
