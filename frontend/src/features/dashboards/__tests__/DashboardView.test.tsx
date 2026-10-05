import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'

const toastError = vi.fn()
vi.mock('react-hot-toast', () => ({
  toast: {
    error: (...args: unknown[]): void => {
      toastError(...args)
    },
    success: vi.fn(),
  },
}))

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
   useParams: () => ({ id: 'test-dashboard-id' }),
   useLocation: () => ({ state: {} }),
}))

// Mock PlotlyChart component to avoid rendering issues in tests
vi.mock('../ui/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart">Chart</div>,
}))

// Mock LineChart component
vi.mock('../ui/charts/LineChart', () => ({
  LineChart: () => <div data-testid="line-chart">Line Chart</div>,
}))

// Mock TableChart component
vi.mock('../ui/charts/TableChart', () => ({
  TableChart: () => <div data-testid="table-chart">Table Chart</div>,
}))

// Mock DashboardFilters
vi.mock('../ui/DashboardFilters', () => ({
  DashboardFilters: () => <div data-testid="dashboard-filters">Filters Component</div>,
}))

// Mock UploadModal with lazy/suspense-compatible mock
vi.mock('../../upload/ui/UploadModal', () => ({
  UploadModal: () => null,
}))

// The aggregated response the mocked hook returns. Mutable so individual tests
// can drive the truncation contract; the default is untruncated.
let mockAggregatedData: {
  graphs: Array<{
    graph_id: string
    type: string
    name: string
    data: unknown[]
    returned_rows: number
    total_rows: number
    rows_truncated: boolean
    metrics?: string[]
    dimensions?: string[]
    config?: { x?: string; metrics?: string[] }
  }>
  total_rows: number
  truncated: boolean
} = {
  graphs: [
    {
      graph_id: 'graph-1',
      type: 'bar',
      name: 'Sales by Category',
      data: [{ x: ['A', 'B', 'C'], y: [1, 2, 3], type: 'bar' }],
      returned_rows: 1,
      total_rows: 1,
      rows_truncated: false,
    },
    {
      graph_id: 'graph-2',
      type: 'line',
      name: 'Trend Over Time',
      data: [{ x: [1, 2, 3], y: [10, 20, 30], type: 'scatter', mode: 'lines' }],
      returned_rows: 1,
      total_rows: 1,
      rows_truncated: false,
    },
    {
      graph_id: 'graph-3',
      type: 'table',
      name: 'Data Table',
      data: [{ category: 'A', value: 100 }, { category: 'B', value: 200 }],
      returned_rows: 2,
      total_rows: 2,
      rows_truncated: false,
    },
  ],
  total_rows: 4,
  truncated: false,
}

// Error state driven by individual tests. When set, the mocked hooks report a
// failure so the view's persistent inline surface can be asserted.
let mockDashboardError: Error | null = null
let mockAggregatedError: Error | null = null
// P13: whether a failed aggregated query retained its last good data, and the
// timestamp that data reached the browser.
let mockRetainedOnError = false
let mockDataUpdatedAt = 0

// Mock dashboard API
vi.mock('../api/dashboardApi', () => ({
  useDashboard: () => ({
    data: mockDashboardError
      ? undefined
      : {
          id: 'test-dashboard-id',
          name: 'Test Dashboard',
          description: 'A test dashboard for unit tests',
          config: {
            graph_types: ['bar', 'line'],
          },
          permission: 'edit',
        },
    isLoading: false,
    error: mockDashboardError,
  }),
  useAggregatedData: () => ({
    data:
      mockAggregatedError && !mockRetainedOnError ? undefined : mockAggregatedData,
    isLoading: false,
    error: mockAggregatedError,
    dataUpdatedAt: mockDataUpdatedAt,
  }),
  useInvalidateDashboard: () => ({
    invalidateDashboard: vi.fn(),
    invalidateAggregatedData: vi.fn(),
  }),
}))

import { DashboardView } from '../ui/DashboardView'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={null}>
        {children}
      </Suspense>
    </QueryClientProvider>
  )
}

const defaultGraphs = (): typeof mockAggregatedData => ({
  graphs: [
    {
      graph_id: 'graph-1',
      type: 'bar',
      name: 'Sales by Category',
      data: [{ x: ['A', 'B', 'C'], y: [1, 2, 3], type: 'bar' }],
      returned_rows: 1,
      total_rows: 1,
      rows_truncated: false,
    },
    {
      graph_id: 'graph-2',
      type: 'line',
      name: 'Trend Over Time',
      data: [{ x: [1, 2, 3], y: [10, 20, 30], type: 'scatter', mode: 'lines' }],
      returned_rows: 1,
      total_rows: 1,
      rows_truncated: false,
    },
    {
      graph_id: 'graph-3',
      type: 'table',
      name: 'Data Table',
      data: [{ category: 'A', value: 100 }, { category: 'B', value: 200 }],
      returned_rows: 2,
      total_rows: 2,
      rows_truncated: false,
    },
  ],
  total_rows: 4,
  truncated: false,
})

describe('DashboardView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAggregatedData = defaultGraphs()
    mockDashboardError = null
    mockAggregatedError = null
    mockRetainedOnError = false
    mockDataUpdatedAt = 0
  })

  it('renders dashboard title', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })
  })

  it('renders dashboard description when present', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('A test dashboard for unit tests')).toBeInTheDocument()
    })
  })

  it('renders upload button when user has edit permission', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /upload data/i })).toBeInTheDocument()
    })
  })

  it('renders chart titles from aggregated data', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Sales by Category')).toBeInTheDocument()
      expect(screen.getByText('Trend Over Time')).toBeInTheDocument()
      expect(screen.getByText('Data Table')).toBeInTheDocument()
    })
  })

  it('renders multiple plotly charts', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      const charts = screen.getAllByTestId('plotly-chart')
      expect(charts).toHaveLength(1)
    })
  })

  it('renders line chart', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId('line-chart')).toBeInTheDocument()
    })
  })

  it('renders table chart', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId('table-chart')).toBeInTheDocument()
    })
  })

  it('renders the status line from the server counts, not a client count', async () => {
    // The server says the graph has 5000 rows and returned 42. The fixture's
    // `data` deliberately holds a single point, so a client that invented the
    // lower bound from `data.length` would render "1 of 5000". The assertion
    // pins the server's `returned_rows` as the source of the displayed count.
    mockAggregatedData = {
      graphs: [
        {
          graph_id: 'graph-1',
          type: 'bar',
          name: 'Sales by Category',
          data: [{ x: ['A'], y: [1], type: 'bar' }],
          returned_rows: 42,
          total_rows: 5000,
          rows_truncated: true,
        },
      ],
      total_rows: 5000,
      truncated: true,
    }

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Showing 42 of 5000')).toBeInTheDocument()
    })
    expect(screen.queryByText('Showing 1 of 5000')).not.toBeInTheDocument()
  })

  it('renders no status line when the graph is not truncated', async () => {
    mockAggregatedData = defaultGraphs()

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Sales by Category')).toBeInTheDocument()
    })
    expect(screen.queryByText(/^Showing /)).not.toBeInTheDocument()
  })

  it('shows the inline message for a main-view failure and raises no toast', async () => {
    mockDashboardError = new Error('boom')

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(
        screen.getByText('Failed to load dashboard. Please try again.'),
      ).toBeInTheDocument()
    })
    expect(toastError).not.toHaveBeenCalled()
  })

  it('shows the inline message for a chart-data failure and raises no toast', async () => {
    mockAggregatedError = new Error('boom')

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Failed to load chart data.')).toBeInTheDocument()
    })
    expect(toastError).not.toHaveBeenCalled()
  })

  // --- R6: the dashboard render states ---

  it('shows the no-charts message for an empty graph list and not the upload advice', async () => {
    mockAggregatedData = { graphs: [], total_rows: 0, truncated: false }

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('This dashboard has no charts to display.')).toBeInTheDocument()
    })
    expect(screen.queryByText(/Upload data to see charts/)).not.toBeInTheDocument()
  })

  it('shows the per-graph marker naming the absent measure column', async () => {
    mockAggregatedData = {
      graphs: [
        {
          graph_id: 'graph-1',
          type: 'bar',
          name: 'Sales by Category',
          data: [{ category: 'A' }, { category: 'B' }],
          returned_rows: 2,
          total_rows: 2,
          rows_truncated: false,
          metrics: ['revenue'],
          dimensions: ['category'],
        },
      ],
      total_rows: 2,
      truncated: false,
    }

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(
        screen.getByText(
          'The measure "revenue" is not in the served data, so this chart shows a gap instead of a value.',
        ),
      ).toBeInTheDocument()
    })
  })

  it('warns once per dashboard and marks each absent-measure graph', async () => {
    mockAggregatedData = {
      graphs: [
        {
          graph_id: 'graph-1',
          type: 'bar',
          name: 'Sales by Category',
          data: [{ category: 'A' }],
          returned_rows: 1,
          total_rows: 1,
          rows_truncated: false,
          metrics: ['revenue'],
          dimensions: ['category'],
        },
        {
          graph_id: 'graph-2',
          type: 'bar',
          name: 'Cost by Category',
          data: [{ category: 'A' }],
          returned_rows: 1,
          total_rows: 1,
          rows_truncated: false,
          metrics: ['cost'],
          dimensions: ['category'],
        },
      ],
      total_rows: 2,
      truncated: false,
    }

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(
        screen.getByText(
          'Sales by Category',
        ),
      ).toBeInTheDocument()
    })
    // The roll-up names the aggregate: exactly one, at dashboard scope.
    expect(
      screen.getAllByText(
        'One or more charts have a measure that is not in the served data. Those charts are drawn as gaps, not zeros.',
      ),
    ).toHaveLength(1)
    // The per-graph marker names each column: once per affected graph.
    expect(screen.getAllByText(/The measure ".+" is not in the served data/)).toHaveLength(2)
  })

  it('does not warn for a present-zero measure', async () => {
    // The volume discriminator: today's dashboards are full of zeros and this
    // block must not warn about them.
    mockAggregatedData = {
      graphs: [
        {
          graph_id: 'graph-1',
          type: 'bar',
          name: 'Sales by Category',
          data: [{ category: 'A', revenue: 0 }],
          returned_rows: 1,
          total_rows: 1,
          rows_truncated: false,
          metrics: ['revenue'],
          dimensions: ['category'],
        },
      ],
      total_rows: 1,
      truncated: false,
    }

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Sales by Category')).toBeInTheDocument()
    })
    expect(
      screen.queryByText(
        'One or more charts have a measure that is not in the served data. Those charts are drawn as gaps, not zeros.',
      ),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/is not in the served data/)).not.toBeInTheDocument()
  })

  it('renders only the error alert on a failed load with no cached data', async () => {
    mockAggregatedError = new Error('boom')

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Failed to load chart data.')).toBeInTheDocument()
    })
    // Today both render, so the view asserts a false "no data" on a failure.
    expect(
      screen.queryByText('This dashboard has no charts to display.'),
    ).not.toBeInTheDocument()
  })

  // --- P13: stale data is shown, marked, and not replaced by an error ---

  it('keeps the last good graphs and marks them out of date on a failed refetch', async () => {
    mockAggregatedError = new Error('refetch failed')
    mockRetainedOnError = true
    mockDataUpdatedAt = Date.UTC(2024, 5, 15, 10, 30)

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText(/Data may be out of date — last updated/)).toBeInTheDocument()
    })
    // The retained graphs still render.
    expect(screen.getByText('Sales by Category')).toBeInTheDocument()
    // The failure Alert is suppressed while the retained data is shown.
    expect(screen.queryByText('Failed to load chart data.')).not.toBeInTheDocument()
  })

  it('shows no stale marker on a first load that fails with no previous data', async () => {
    mockAggregatedError = new Error('boom')
    mockRetainedOnError = false

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Failed to load chart data.')).toBeInTheDocument()
    })
    expect(screen.queryByText(/Data may be out of date/)).not.toBeInTheDocument()
  })
})