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
import {
  DASHBOARD_MEASURE_ABSENT_MESSAGE,
  MEASURE_ABSENT_MESSAGE,
  NO_CHARTS_MESSAGE,
  STALE_DATA_MESSAGE,
  DashboardDataState,
  GraphRenderState,
  classifyDashboard,
  classifyGraph,
  hasAbsentMeasure,
  resolveMeasureColumn,
} from './charts/chartStates'
import type { GraphDataWithConfig, FilterDetail } from '../../../shared/types/api.types'
import type { FilterType } from '../../../shared/types/enums'
import {
  CHART_DATA_LOAD_FAILED_MESSAGE,
  DASHBOARD_LOAD_FAILED_MESSAGE,
} from '../../../shared/api/errorSurfaces'
import { formatDateTime } from '../../../shared/utils/formatDate'

const UploadModal = lazy(() =>
  import('../../upload/ui/UploadModal').then((module) => ({ default: module.UploadModal })),
)

const FILTER_STORAGE_KEY_PREFIX = 'dashboard-filters-'

type FilterState = Record<string, string | string[] | number | number[]>

// Helper to get filter storage key for a dashboard
function getFilterStorageKey(dashboardId: string | undefined): string | null {
  if (!dashboardId) return null
  return `${FILTER_STORAGE_KEY_PREFIX}${dashboardId}`
}

/**
 * Reads the `preserveFilters` flag from router location state.
 *
 * `useLocation().state` is `any` in react-router v6, so the value is narrowed
 * here rather than read as `any`. Absent or non-boolean values preserve filters.
 */
function shouldPreserveFilters(state: unknown): boolean {
  if (typeof state !== 'object' || state === null) return true
  return (state as { preserveFilters?: unknown }).preserveFilters !== false
}

/**
 * Narrows an unknown restored value to a usable `FilterState` entry.
 *
 * `loadPersistedFilters` runs as a `useState` initializer, before
 * `useDashboard` resolves, so it cannot consult the declared filter types. It
 * can still decide the one case that is unambiguous from the value alone: a
 * `number[]` is the retired slider's output, and a range is not evaluable, so
 * that entry is dropped. A `string[]` is ambiguous -- it is indistinguishable
 * on the wire from a legitimate two-value multiselect -- and is kept; the
 * server's by-name backstop is what resolves it.
 */
function isRestorableFilterValue(value: unknown): boolean {
  if (Array.isArray(value)) {
    return !value.some((element) => typeof element === 'number')
  }
  return (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  )
}

/**
 * Loads persisted filters for a dashboard.
 *
 * Used as a `useState` initializer so the restore happens once at mount rather
 * than via a synchronous `setState` inside an effect, which React warns against.
 * When `preserveFilters` is false the saved entry is removed and no filters are
 * restored.
 */
function loadPersistedFilters(dashboardId: string | undefined, preserve: boolean): FilterState {
  const storageKey = getFilterStorageKey(dashboardId)
  if (!storageKey) return {}
  try {
    if (!preserve) {
      sessionStorage.removeItem(storageKey)
      return {}
    }
    const saved = sessionStorage.getItem(storageKey)
    if (!saved) return {}
    const parsed: unknown = JSON.parse(saved)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const restored: FilterState = {}
    for (const [key, value] of Object.entries(parsed)) {
      if (isRestorableFilterValue(value)) {
        restored[key] = value as FilterState[string]
      }
    }
    return restored
  } catch {
    // Ignore JSON parse errors - continue with empty filters
    return {}
  }
}

export function DashboardView() {
  const { id } = useParams()
  const location = useLocation()

  const [filters, setFilters] = useState<FilterState>(() =>
    loadPersistedFilters(id, shouldPreserveFilters(location.state)),
  )
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
    dataUpdatedAt,
  } = useAggregatedData(id || '', filters)
  const { invalidateAggregatedData } = useInvalidateDashboard()

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
        {DASHBOARD_LOAD_FAILED_MESSAGE}
      </Alert>
    )
  }

  const canEdit = ['edit', 'admin'].includes(dashboard.permission)

  const hasGraphs = aggregatedData !== undefined && aggregatedData.graphs.length > 0
  // P13: a failed *background* refetch of a query that already succeeded keeps
  // its last good `data` (the probe in `aggregated-stale-data.test.tsx` pins
  // this). That retained data is shown, marked out of date, instead of being
  // replaced by a bare failure — and the failure Alert is suppressed for it.
  const isStale =
    dataError !== null &&
    aggregatedData !== undefined &&
    aggregatedData.graphs.length > 0 &&
    dataUpdatedAt > 0
  // The empty branch is reached when no graph row stack renders: either the
  // response has no graphs, or there is no response. Both are the NO_CHARTS
  // state, so the served list -- absent or empty -- is classified the same way.
  const dashboardDataState =
    aggregatedData !== undefined
      ? classifyDashboard(aggregatedData)
      : DashboardDataState.NO_CHARTS

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

          {dataError && !isStale && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {CHART_DATA_LOAD_FAILED_MESSAGE}
            </Alert>
          )}

          {isStale && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {STALE_DATA_MESSAGE.replace('{time}', formatDateTime(new Date(dataUpdatedAt)))}
            </Alert>
          )}

          {hasGraphs ? (
            <Stack spacing={2}>
              {aggregatedData.graphs.some(hasAbsentMeasure) && (
                <Alert severity="warning">{DASHBOARD_MEASURE_ABSENT_MESSAGE}</Alert>
              )}
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
                  {classifyGraph(graph) === GraphRenderState.MEASURE_ABSENT && (
                    <Typography
                      variant="caption"
                      color="warning.main"
                      component="p"
                      sx={{ mb: 1 }}
                    >
                      {MEASURE_ABSENT_MESSAGE.replace(
                        '{column}',
                        resolveMeasureColumn(graph) ?? '',
                      )}
                    </Typography>
                  )}
                  <Stack sx={{ height: 400 }}>
                    <ChartRenderer graph={graph} />
                  </Stack>
                </Paper>
              ))}
            </Stack>
          ) : (
            !dataLoading &&
            !dataError && (
              <Alert severity="info">
                {dashboardDataState === DashboardDataState.NO_CHARTS
                  ? NO_CHARTS_MESSAGE
                  : null}
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