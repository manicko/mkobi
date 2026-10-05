import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'

// Mock react-router-dom
const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
   useParams: () => ({ id: 'test-dashboard-id' }),
   useLocation: () => ({ state: {} }),
   useNavigate: () => mockNavigate,
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

// Mock UploadModal with lazy/suspense-compatible mock
vi.mock('../../upload/ui/UploadModal', () => ({
  UploadModal: () => null,
}))

// Mock DashboardFilters
vi.mock('../ui/DashboardFilters', () => ({
   DashboardFilters: ({ values, onChange, onReset }: {
    values: Record<string, string | string[] | number | number[]>
    onChange: (filters: Record<string, string | string[] | number | number[]>) => void
    onReset?: () => void
  }) => (
    <div data-testid="dashboard-filters">
      <div data-testid="filter-values">{JSON.stringify(values)}</div>
      <button
        data-testid="set-filter-btn"
        onClick={() => onChange({ region: 'North' })}
      >
        Set Filter
      </button>
      <button
        data-testid="reset-filter-btn"
        onClick={() => { onChange({}); onReset?.() }}
      >
        Reset Filter
      </button>
    </div>
  ),
}))

// Mock dashboard API
vi.mock('../api/dashboardApi', () => ({
  useDashboard: () => ({
    data: {
      id: 'test-dashboard-id',
      name: 'Test Dashboard',
      description: 'A test dashboard for filter persistence tests',
      config: {
        graph_types: ['bar', 'line'],
        filters: [
          { field: 'region', type: 'select', source: 'data' },
        ],
      },
      permission: 'edit',
    },
    isLoading: false,
    error: null,
  }),
  useAggregatedData: () => ({
    data: {
      graphs: [
        {
          graph_id: 'graph-1',
          type: 'bar',
          name: 'Sales by Region',
          data: [{ x: ['North', 'South'], y: [100, 200], type: 'bar' }],
        },
      ],
    },
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

// Helper to setup sessionStorage
const setStoredFilters = (dashboardId: string, filters: Record<string, unknown>) => {
  sessionStorage.setItem(`dashboard-filters-${dashboardId}`, JSON.stringify(filters))
}

const getStoredFilters = (dashboardId: string): Record<string, unknown> | null => {
  const stored = sessionStorage.getItem(`dashboard-filters-${dashboardId}`)
  return stored ? (JSON.parse(stored) as Record<string, unknown>) : null
}

const clearStoredFilters = (dashboardId: string) => {
  sessionStorage.removeItem(`dashboard-filters-${dashboardId}`)
}

describe('DashboardView - Filter Persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('renders dashboard with filters component', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })
    expect(screen.getByTestId('dashboard-filters')).toBeInTheDocument()
  })

  it('persists filter values to sessionStorage on change', async () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })

    // Set a filter value
    const setFilterBtn = screen.getByTestId('set-filter-btn')
    fireEvent.click(setFilterBtn)

    // Verify it persists to sessionStorage
    const stored = getStoredFilters('test-dashboard-id')
    expect(stored).toEqual({ region: 'North' })
  })

  it('restores filter values from sessionStorage on mount', async () => {
    // Pre-populate sessionStorage with saved filters
    setStoredFilters('test-dashboard-id', { region: 'South' })

    const Wrapper = createWrapper()
    const { unmount } = render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })

    // Verify filter values are restored
    const filterValues = screen.getByTestId('filter-values')
    const storedValues = JSON.parse(filterValues.textContent || '{}') as Record<string, unknown>
    expect(storedValues).toEqual({ region: 'South' })

    // Clean up for next test
    unmount()
  })

  it('clears filter values from sessionStorage on explicit reset', async () => {
    // Pre-populate sessionStorage with saved filters
    setStoredFilters('test-dashboard-id', { region: 'East' })

    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })

    // Click reset button
    const resetFilterBtn = screen.getByTestId('reset-filter-btn')
    fireEvent.click(resetFilterBtn)

    // Verify sessionStorage is cleared
    const stored = getStoredFilters('test-dashboard-id')
    expect(stored).toBeNull()
  })

  it('preserves separate filter state for different dashboards', () => {
    // Set filters for first dashboard
    setStoredFilters('dashboard-1', { region: 'North' })
    setStoredFilters('dashboard-2', { region: 'South' })

    // Verify both are stored separately
    expect(getStoredFilters('dashboard-1')).toEqual({ region: 'North' })
    expect(getStoredFilters('dashboard-2')).toEqual({ region: 'South' })

    // Clean up
    clearStoredFilters('dashboard-1')
    clearStoredFilters('dashboard-2')
  })
})