import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'

// D-16-7: a completed upload replaces the file the dashboard was built from,
// so the filter-option lists must be invalidated alongside the aggregated data.
// This asserts on the invalidation *payload* (the hook call), not on rendering:
// a rendered option list could be served from a stale cache and still look
// correct, which is exactly the defect.

const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: 'test-dashboard-id' }),
  useLocation: () => ({ state: {} }),
  useNavigate: () => mockNavigate,
}))

vi.mock('../ui/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart">Chart</div>,
}))

vi.mock('../ui/charts/LineChart', () => ({
  LineChart: () => <div data-testid="line-chart">Line Chart</div>,
}))

vi.mock('../ui/charts/TableChart', () => ({
  TableChart: () => <div data-testid="table-chart">Table Chart</div>,
}))

// Expose the `onUploadComplete` prop the view passes down and invoke it, so the
// test drives the real completion path rather than a re-implementation of it.
vi.mock('../../upload/ui/UploadModal', () => ({
  UploadModal: ({ onUploadComplete }: { onUploadComplete?: () => void }) => (
    <button data-testid="complete-upload" onClick={() => onUploadComplete?.()}>
      Complete Upload
    </button>
  ),
}))

vi.mock('../ui/DashboardFilters', () => ({
  DashboardFilters: () => <div data-testid="dashboard-filters" />,
}))

// The single hook both invalidations flow through. Spying on it proves the view
// calls the filter-values invalidation with the dashboard id on upload.
const invalidatePayloads = vi.hoisted(() => ({
  aggregated: [] as string[],
  filterValues: [] as string[],
}))

vi.mock('../api/dashboardApi', () => ({
  useDashboard: () => ({
    data: {
      id: 'test-dashboard-id',
      name: 'Test Dashboard',
      description: null,
      config: { graph_types: ['bar'], filters: [{ field: 'region', type: 'select' }] },
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
          data: [{ x: ['North'], y: [100], type: 'bar' }],
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
    dataUpdatedAt: 1,
  }),
  useInvalidateDashboard: () => ({
    invalidateDashboard: vi.fn(),
    invalidateAggregatedData: (id: string) => {
      invalidatePayloads.aggregated.push(id)
      return Promise.resolve()
    },
    invalidateFilterValues: (id: string) => {
      invalidatePayloads.filterValues.push(id)
      return Promise.resolve()
    },
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

describe('DashboardView - upload completion invalidation', () => {
  beforeEach(() => {
    invalidatePayloads.aggregated.length = 0
    invalidatePayloads.filterValues.length = 0
    sessionStorage.clear()
  })

  it('invalidates both the aggregated data and the filter values on upload', async () => {
    // Discriminates the fix: at HEAD the view only calls
    // invalidateAggregatedData, so `filterValues` stays empty and fails here.
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <DashboardView />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('Test Dashboard')).toBeInTheDocument()
    })

    // Open the modal so the lazily-imported modal mock mounts.
    fireEvent.click(screen.getByText('Upload Data'))

    await waitFor(() => {
      expect(screen.getByTestId('complete-upload')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('complete-upload'))

    await waitFor(() => {
      expect(invalidatePayloads.filterValues).toEqual(['test-dashboard-id'])
    })
    expect(invalidatePayloads.aggregated).toEqual(['test-dashboard-id'])
  })
})
