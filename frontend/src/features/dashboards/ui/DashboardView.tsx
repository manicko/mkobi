import { useCallback, useState, lazy, Suspense, useEffect } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import {
  Typography,
  CircularProgress,
  Alert,
  Button,
  Grid,
  Paper,
  Stack,
} from '@mui/material'
import { useDashboard, useAggregatedData, useInvalidateDashboard } from '../api/dashboardApi'
import { DashboardFilters } from './DashboardFilters'
import { ChartRenderer } from './charts/ChartRenderer'
import { SkeletonChart } from './charts/SkeletonChart'
import type { GraphDataWithConfig, FilterDetail } from '../../../shared/types/api.types'
import type { FilterType } from '../../../shared/types/enums'

const UploadModal = lazy(() =>
  import('../../upload/ui/UploadModal').then((module) => ({ default: module.UploadModal })),
)

const FILTER_STORAGE_KEY_PREFIX = 'dashboard-filters-'

// Helper to get filter storage key for a dashboard
function getFilterStorageKey(dashboardId: string | undefined): string | null {
  if (!dashboardId) return null
  return `${FILTER_STORAGE_KEY_PREFIX}${dashboardId}`
}

export function DashboardView() {
const { id } = useParams()
   const location = useLocation()

  const [filters, setFilters] = useState<
    Record<string, string | string[] | number | number[]>
  >({})
  const [uploadModalOpen, setUploadModalOpen] = useState(false)

  const {
    data: dashboard,
    isLoading: dashboardLoading,
    error: dashboardError,
  } = useDashboard(id || '')
  const {
    data: aggregatedData,
    isLoading: dataLoading,
    error: dataError,
  } = useAggregatedData(id || '', filters)
  const { invalidateAggregatedData } = useInvalidateDashboard()

  // Load persisted filters from sessionStorage on mount
  useEffect(() => {
    const storageKey = getFilterStorageKey(id)
    if (storageKey) {
      try {
        if (location.state?.preserveFilters === false) {
          // Clear saved filters when explicitly requested
          sessionStorage.removeItem(storageKey)
        } else {
          // Restore saved filters (default behavior)
          const savedFilters = sessionStorage.getItem(storageKey)
          if (savedFilters) {
            const parsed = JSON.parse(savedFilters) as Record<string, string | string[] | number | number[]>
            setFilters(parsed)
          }
        }
      } catch {
        // Ignore JSON parse errors - continue with empty filters
      }
    }
  }, [id, location.state?.preserveFilters])

  // Save filters to sessionStorage whenever they change
  useEffect(() => {
    const storageKey = getFilterStorageKey(id)
    if (storageKey && Object.keys(filters).length > 0) {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(filters))
      } catch {
        // Ignore storage errors
      }
    }
  }, [id, filters])

  // Derive filterDetails from dashboard config
  const filterDetails: FilterDetail[] = dashboard?.config?.filters && dashboard.config.filters.length > 0
    ? dashboard.config.filters.map(
        (filterConfig, index) => ({
          id: `filter-${index}-${filterConfig.field}`,
          name: filterConfig.field,
          type: filterConfig.type as FilterType,
          config: {
            field: filterConfig.field,
            source: filterConfig.source,
            multi: filterConfig.multi,
          },
        })
      )
    : []

  const handleFilterChange = useCallback(
    (newFilters: Record<string, string | string[] | number | number[]>) => {
      setFilters(newFilters)
    },
    []
  )

  const handleResetFilters = useCallback(() => {
    setFilters({})
    const storageKey = getFilterStorageKey(id)
    if (storageKey) {
      sessionStorage.removeItem(storageKey)
    }
  }, [id])

  if (dashboardLoading) {
    return (
      <Stack sx={{ alignItems: 'center', p: 4 }}>
        <CircularProgress />
      </Stack>
    )
  }

  if (dashboardError || !dashboard) {
    return (
      <Alert severity="error" sx={{ m: 2 }}>
        Failed to load dashboard. Please try again.
      </Alert>
    )
  }

  const canEdit = ['edit', 'admin'].includes(dashboard.permission)

  return (
    <Stack sx={{ p: 3 }} spacing={2}>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 3 }}
      >
        <Typography variant="h4">{dashboard.name}</Typography>
        {canEdit && (
          <Button
            variant="contained"
            onClick={() => setUploadModalOpen(true)}
          >
            Upload Data
          </Button>
        )}
      </Stack>

      {dashboard.description && (
        <Typography variant="body1" color="text.secondary" component="p" sx={{ mb: 2 }}>
          {dashboard.description}
        </Typography>
      )}

      <Grid container spacing={2}>
        {dashboard.config.filters && dashboard.config.filters.length > 0 && (
          <Grid size={{ xs: 12, md: 3 }}>
            <DashboardFilters
              filters={filterDetails}
              values={filters}
              onChange={handleFilterChange}
              onReset={handleResetFilters}
              dashboardId={id || ''}
            />
          </Grid>
        )}

        <Grid
          size={{
            xs: 12,
            md: dashboard.config.filters && dashboard.config.filters.length > 0 ? 9 : 12,
          }}
        >
          {dataLoading && (
            <SkeletonChart count={dashboard.config.charts?.length ?? 1} />
          )}

          {dataError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Failed to load chart data.
            </Alert>
          )}

          {aggregatedData?.graphs && aggregatedData.graphs.length > 0 ? (
            <Stack spacing={2}>
              {aggregatedData.graphs.map((graph: GraphDataWithConfig) => (
                <Paper key={graph.graph_id} variant="outlined" sx={{ p: 2 }}>
                  <Typography variant="h6" gutterBottom>
                    {graph.name}
                  </Typography>
                  {graph.rows_truncated && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      component="p"
                      sx={{ mb: 1 }}
                    >
                      Showing {graph.returned_rows} of {graph.total_rows}
                    </Typography>
                  )}
                  <Stack sx={{ height: 400 }}>
                    <ChartRenderer graph={graph} />
                  </Stack>
                </Paper>
              ))}
            </Stack>
          ) : (
            !dataLoading && (
              <Alert severity="info">
                No data available for this dashboard. Upload data to see charts.
              </Alert>
            )
          )}
        </Grid>
      </Grid>

      <Suspense fallback={null}>
        <UploadModal
          open={uploadModalOpen}
          onClose={() => setUploadModalOpen(false)}
          dashboardId={id || ''}
          onUploadComplete={() => {
            setUploadModalOpen(false)
            if (id) {
              void invalidateAggregatedData(id)
            }
          }}
        />
      </Suspense>
    </Stack>
  )
}