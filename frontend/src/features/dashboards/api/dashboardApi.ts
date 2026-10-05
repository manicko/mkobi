import { useQuery, useQueryClient } from '@tanstack/react-query'
import axiosInstance from '../../../shared/api/axiosInstance'
import { useAuthToken } from '../../../features/auth/model/authToken'
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

export function useInvalidateDashboard() {
  const queryClient = useQueryClient()
  return {
    invalidateDashboard: (id: string) =>
      queryClient.invalidateQueries({ queryKey: ['dashboards', id] }),
    invalidateAggregatedData: (dashboardId: string) =>
      queryClient.invalidateQueries({ queryKey: ['aggregatedData', dashboardId] }),
  }
}

export function useFilterValues(dashboardId: string, filterName: string) {
  const accessToken = useAuthToken()
  return useQuery({
    queryKey: ['filterValues', dashboardId, filterName],
    queryFn: () => dashboardApi.getFilterValues(dashboardId, filterName),
    enabled: !!dashboardId && !!filterName && !!accessToken,
  })
}
