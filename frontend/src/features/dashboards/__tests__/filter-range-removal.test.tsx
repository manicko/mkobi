import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: 'test-dashboard-id' }),
  useLocation: () => ({ state: {} }),
}))

// Mock chart components to avoid rendering issues in tests
vi.mock('../ui/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart">Chart</div>,
}))
vi.mock('../ui/charts/LineChart', () => ({
  LineChart: () => <div data-testid="line-chart">Line Chart</div>,
}))
vi.mock('../ui/charts/TableChart', () => ({
  TableChart: () => <div data-testid="table-chart">Table Chart</div>,
}))

// Mock UploadModal with lazy/suspense-compatible mock
vi.mock('../../upload/ui/UploadModal', () => ({
  UploadModal: () => null,
}))

// The dashboard config is driven per test; the default declares a `range`
// filter, which must render no control and send no value.
let mockDashboardConfig: {
  graph_types: string[]
  filters: Array<{ field: string; type: string }>
} = {
  graph_types: ['bar'],
  filters: [{ field: 'price', type: 'range' }],
}

// Captures the `filters` argument of every `useAggregatedData` call, so the
// submitted filters can be observed without a network spy.
let capturedFilters: Array<Record<string, unknown> | undefined> = []

vi.mock('../api/dashboardApi', () => ({
  useDashboard: () => ({
    data: {
      id: 'test-dashboard-id',
      name: 'Test Dashboard',
      description: null,
      config: mockDashboardConfig,
      permission: 'edit',
    },
    isLoading: false,
    error: null,
  }),
  useAggregatedData: (_dashboardId: string, filters?: Record<string, unknown>) => {
    capturedFilters.push(filters)
    return {
      data: {
        graphs: [
          {
            graph_id: 'graph-1',
            type: 'bar',
            name: 'Sales by Category',
            data: [{ x: ['A'], y: [1], type: 'bar' }],
            returned_rows: 1,
            total_rows: 1,
            rows_truncated: false,
          },
        ],
        total_rows: 1,
        truncated: false,
      },
      isLoading: false,
      error: null,
    }
  },
  useFilterValues: () => ({ data: { values: ['A', 'B'], total_values: 2 } }),
  useInvalidateDashboard: () => ({
    invalidateDashboard: vi.fn(),
    invalidateAggregatedData: vi.fn(),
    invalidateFilterValues: vi.fn(),
  }),
}))

import { DashboardView } from '../ui/DashboardView'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={null}>{children}</Suspense>
    </QueryClientProvider>
  )
}

const setStoredFilters = (dashboardId: string, filters: Record<string, unknown>) => {
  sessionStorage.setItem(`dashboard-filters-${dashboardId}`, JSON.stringify(filters))
}

describe('DashboardView - range control removal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capturedFilters = []
    sessionStorage.clear()
    mockDashboardConfig = {
      graph_types: ['bar'],
      filters: [{ field: 'price', type: 'range' }],
    }
  })

  it('renders no control and sends no value for a declared range filter', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })

    expect(screen.queryByRole('slider')).toBeNull()
    expect(
      screen.getByText(/Filter "price".*Declared type is "range"/),
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(capturedFilters.length).toBeGreaterThan(0)
    })
    for (const filters of capturedFilters) {
      expect(filters).not.toHaveProperty('price')
    }
  })

  it('drops a restored numeric-array filter before any request', async () => {
    setStoredFilters('test-dashboard-id', { price: [0, 100] })

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(capturedFilters.length).toBeGreaterThan(0)
    })
    for (const filters of capturedFilters) {
      expect(filters).not.toHaveProperty('price')
    }
  })

  it('preserves a restored string-array filter byte-identical', async () => {
    setStoredFilters('test-dashboard-id', { category: ['A', 'B'] })

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(capturedFilters.some((f) => f?.category !== undefined)).toBe(true)
    })
    const withCategory = capturedFilters.find((f) => f?.category !== undefined)
    expect(withCategory?.category).toEqual(['A', 'B'])
  })

  it('drops a restored boolean-array filter so it cannot blank the dashboard', async () => {
    // Discriminates the tightened predicate: HEAD admitted a `boolean[]` (it
    // only dropped arrays containing a number), which serialises into the
    // `filters` payload and is refused by `list[str]` with a 422 rendered as a
    // dashboard-scope alert. Every element must be a string.
    setStoredFilters('test-dashboard-id', { flags: [true, false] })

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(capturedFilters.length).toBeGreaterThan(0)
    })
    for (const filters of capturedFilters) {
      expect(filters).not.toHaveProperty('flags')
    }
  })

  it('preserves a restored scalar filter unchanged', async () => {
    setStoredFilters('test-dashboard-id', { region: 'North' })

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(capturedFilters.some((f) => f?.region !== undefined)).toBe(true)
    })
    const withRegion = capturedFilters.find((f) => f?.region !== undefined)
    expect(withRegion?.region).toBe('North')
  })
})
