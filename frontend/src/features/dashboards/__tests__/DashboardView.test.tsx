import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'

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

// Mock dashboard API
vi.mock('../api/dashboardApi', () => ({
  useDashboard: () => ({
    data: {
      id: 'test-dashboard-id',
      name: 'Test Dashboard',
      description: 'A test dashboard for unit tests',
      config: {
        graph_types: ['bar', 'line'],
      },
      permission: 'edit',
    },
    isLoading: false,
    error: null,
  }),
  useAggregatedData: () => ({
    data: mockAggregatedData,
    isLoading: false,
    error: null,
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
})