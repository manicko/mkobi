import { useQuery, useQueryClient } from '@tanstack/react-query'
import axiosInstance from '../../../shared/api/axiosInstance'
import { useAuthToken } from '../../../shared/auth/tokenStore'
import type {
  DashboardSummary,
  DashboardDetail,
  AggregatedDataRequest,
  AggregatedDataResponse,
  FilterValuesResponse,
} from '../../../shared/types/api.types'

export const dashboardApi = {
  getMyDashboards: async (): Promise<DashboardSummary[]> => {
    const response = await axiosInstance.get<DashboardSummary[]>('/dashboards/my')
    return response.data
  },

  // The dashboard main view renders a persistent inline error, so the shared
  // interceptor must not also raise a toast for these requests (`skipErrorToast`).
  getDashboard: async (id: string): Promise<DashboardDetail> => {
    const response = await axiosInstance.get<DashboardDetail>(`/dashboards/${id}`, {
      skipErrorToast: true,
    })
    return response.data
  },

  getAggregatedData: async (
    params: AggregatedDataRequest
  ): Promise<AggregatedDataResponse> => {
    const response = await axiosInstance.get<AggregatedDataResponse>('/data/aggregated', {
      params,
      skipErrorToast: true,
    })
    return response.data
  },

  getFilterValues: async (
    dashboardId: string,
    filterName: string
  ): Promise<FilterValuesResponse> => {
    const response = await axiosInstance.get<FilterValuesResponse>(
      `/dashboards/${dashboardId}/filter-values`,
      { params: { filter_name: filterName } }
    )
    return response.data
  },
}

export function useMyDashboards() {
  const accessToken = useAuthToken()
  return useQuery({
    queryKey: ['dashboards', 'my'],
    queryFn: () => dashboardApi.getMyDashboards(),
    enabled: !!accessToken,
  })
}

export function useDashboard(id: string) {
  const accessToken = useAuthToken()
  return useQuery({
    queryKey: ['dashboards', id],
    queryFn: () => dashboardApi.getDashboard(id),
    enabled: !!id && !!accessToken,
  })
}

export function useAggregatedData(
  dashboardId: string,
  filters?: Record<string, string | string[] | number | number[]>,
  graphId?: string
) {
  const accessToken = useAuthToken()
  return useQuery({
    // ``graphId`` is part of the key: two per-graph fetches for one dashboard
    // with identical filters must not collide on a single cache entry.
    // ``graphId ?? null`` keeps the key unambiguous when it is absent.
    queryKey: ['aggregatedData', dashboardId, graphId ?? null, filters],
    queryFn: () =>
      dashboardApi.getAggregatedData({
        dashboard_id: dashboardId,
        graph_id: graphId,
        filters: filters ? JSON.stringify(filters) : undefined,
      }),
    enabled: !!dashboardId && !!accessToken,
  })
}

// The filter-values key names the *dashboard* and the *filter*, exactly as
// `useFilterValues` registers it. Exported so the invalidation below and the
// hook share one factory: two hand-written key literals that drift is the
// defect this factory exists to prevent.
export function filterValuesQueryKey(dashboardId: string, filterName: string) {
  return ['filterValues', dashboardId, filterName] as const
}

export function useInvalidateDashboard() {
  const queryClient = useQueryClient()
  return {
    invalidateDashboard: (id: string) =>
      queryClient.invalidateQueries({ queryKey: ['dashboards', id] }),
    invalidateAggregatedData: (dashboardId: string) =>
      queryClient.invalidateQueries({ queryKey: ['aggregatedData', dashboardId] }),
    // One upload replaces the file the dashboards were built from, so both the
    // aggregated data and the filter-option lists go stale together. The option
    // lists are cached with `staleTime: Infinity` (D-16-7 option (b)); without
    // this invalidation they would keep describing the previous file for the
    // lifetime of the process.
    invalidateFilterValues: (dashboardId: string) =>
      queryClient.invalidateQueries({ queryKey: ['filterValues', dashboardId] }),
  }
}

export function useFilterValues(dashboardId: string, filterName: string) {
  const accessToken = useAuthToken()
  return useQuery({
    queryKey: filterValuesQueryKey(dashboardId, filterName),
    queryFn: () => dashboardApi.getFilterValues(dashboardId, filterName),
    enabled: !!dashboardId && !!filterName && !!accessToken,
    // D-16-7 option (b): the option list is a function of the uploaded file, so
    // it changes only on upload and there is no other producer of change. Pin
    // it for the process lifetime and invalidate the key explicitly on upload;
    // a bounded stale window would still show stale options for its duration.
    // Placed on this query alone -- a global Infinity would silently disable
    // background refetching for every query in the application.
    staleTime: Infinity,
  })
}
