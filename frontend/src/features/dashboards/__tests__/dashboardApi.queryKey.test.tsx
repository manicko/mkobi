import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { AggregatedDataResponse, FilterValuesResponse } from '../../../shared/types/api.types'

// The aggregated-data cache key must include the graph id. Two per-graph
// fetches for one dashboard with identical filters must land on two distinct
// cache entries; otherwise the second graph renders the first graph's data.

const { aggregatedGet, filterValuesGet } = vi.hoisted(() => ({
  aggregatedGet: vi.fn<
    (url: string, config: { params: { graph_id?: string } }) => Promise<{
      data: AggregatedDataResponse
    }>
  >(),
  filterValuesGet: vi.fn<
    (url: string, config: { params: { filter_name?: string } }) => Promise<{
      data: FilterValuesResponse
    }>
  >(),
}))

vi.mock('../../../shared/api/axiosInstance', () => ({
  default: {
    get: (
      url: string,
      config: { params: { graph_id?: string; filter_name?: string } }
    ) =>
      url.endsWith('/filter-values')
        ? filterValuesGet(url, config)
        : aggregatedGet(url, config),
  },
}))

vi.mock('../../../shared/auth/tokenStore', () => ({
  useAuthToken: () => 'test-token',
}))

import {
  useAggregatedData,
  useFilterValues,
  useInvalidateDashboard,
} from '../api/dashboardApi'

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

// D-16-7: after an upload, the filter-option lists must stop describing the
// previous file. The invalidation must target exactly the key the hook
// registers, so the option lists are re-fetched rather than left pinned.
function FilterValuesProbe({
  dashboardId,
  filterName,
}: {
  dashboardId: string
  filterName: string
}) {
  useFilterValues(dashboardId, filterName)
  return null
}

describe('filter-values invalidation matches the registered key', () => {
  beforeEach(() => {
    filterValuesGet.mockReset()
    filterValuesGet.mockImplementation(
      (_url: string, config: { params: { filter_name?: string } }) =>
        Promise.resolve({
          data: {
            filter_name: config.params.filter_name ?? 'region',
            values: ['North', 'South'],
            total_values: 2,
          },
        })
    )
  })

  it('pins staleTime on the hook so the list stops background refetching', () => {
    // Discriminates the D-16-7 option (b) placement: HEAD carries no staleTime
    // here, so this fails before the change and passes after. The option list is
    // a function of the uploaded file and changes only on upload.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    const { result } = renderHook(() => useFilterValues('dash-1', 'region'), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      ),
    })

    expect(result.current).toBeDefined()
    const entry = queryClient
      .getQueryCache()
      .find({ queryKey: ['filterValues', 'dash-1', 'region'] })
    expect(entry).toBeDefined()
    // The resolved option wins over the five-minute global default.
    const resolved = queryClient.defaultQueryOptions({
      ...entry!.options,
      queryKey: entry!.queryKey,
    })
    expect(resolved.staleTime).toBe(Infinity)
  })

  it('invalidates exactly the key the hook registered, and only that key', async () => {
    // Discriminates the invalidation branch: HEAD's returned object has no
    // invalidateFilterValues and never names the filterValues key, so the
    // assertion below cannot hold before the change. `invalidateQueries` marks
    // the matching entry stale; a key that does not match leaves it fresh.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    renderProbe(
      <FilterValuesProbe dashboardId="dash-1" filterName="region" />,
      queryClient
    )

    await waitFor(() => {
      expect(filterValuesGet).toHaveBeenCalledTimes(1)
    })

    const key = ['filterValues', 'dash-1', 'region']
    const entry = queryClient.getQueryCache().find({ queryKey: key })
    expect(entry).toBeDefined()

    const { result } = renderHook(() => useInvalidateDashboard(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      ),
    })

    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    await result.current.invalidateFilterValues('dash-1')

    // The payload names the dashboard-scoped filterValues prefix -- the same
    // key the hook registers above -- and nothing else.
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['filterValues', 'dash-1'],
    })

    const invalidated = queryClient
      .getQueryCache()
      .findAll({ queryKey: ['filterValues', 'dash-1'] })
    expect(invalidated).toHaveLength(1)
    expect(invalidated[0].queryKey).toEqual(key)
  })
})
