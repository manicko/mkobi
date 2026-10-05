import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { AggregatedDataResponse } from '../../../shared/types/api.types'

// A real QueryClient against a mocked transport: this probe verifies the
// library's retention behaviour, which is P13's precondition. Mocking
// `dashboardApi` would only verify the mock.
const get = vi.hoisted(() => vi.fn())
vi.mock('../../../shared/api/axiosInstance', () => ({
  default: { get },
}))

// The hook gates on a token; supply one without touching real auth.
const TOKEN = 'probe-token'
vi.mock('../../../shared/auth/tokenStore', () => ({
  useAuthToken: () => TOKEN,
}))

import { useAggregatedData } from '../api/dashboardApi'

// The wire shape for `data` is a flat record, while `GraphDataWithConfig.data`
// is declared `Data[]`. The `unknown[]` override intersected with `Partial<>`
// bridges that once at the fixture boundary without a cast; the hook under test
// returns the object verbatim. This mirrors the fixture helper in
// ChartRenderer.test.tsx.
function makeGraphFixture(
  overrides: Partial<AggregatedDataResponse['graphs'][number]> & { data?: unknown[] },
): AggregatedDataResponse['graphs'][number] {
  const { data = [], ...rest } = overrides
  return {
    graph_id: 'graph-1',
    type: 'bar',
    name: 'Sales by Category',
    returned_rows: data.length,
    total_rows: data.length,
    rows_truncated: false,
    ...rest,
    data,
  }
}

const GOOD_RESPONSE: AggregatedDataResponse = {
  graphs: [makeGraphFixture({ data: [{ category: 'A', revenue: 1 }] })],
  total_rows: 1,
  truncated: false,
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('aggregated data retention across a failed refetch', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('keeps the last good data after a background refetch fails', async () => {
    get.mockResolvedValueOnce({ data: GOOD_RESPONSE }).mockRejectedValueOnce(
      new Error('refetch failed'),
    )

    const { result } = renderHook(() => useAggregatedData('test-dashboard-id', {}), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.data).toEqual(GOOD_RESPONSE))
    expect(result.current.dataUpdatedAt).toBeGreaterThan(0)

    void result.current.refetch()

    await waitFor(() => expect(result.current.error).not.toBeNull())
    // The precondition P13 rests on: the library retains the last successful
    // `data` on a failed background refetch.
    expect(result.current.data).toEqual(GOOD_RESPONSE)
  })
})
