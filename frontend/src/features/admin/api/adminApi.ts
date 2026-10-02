import { axiosInstance } from '../../../shared/api/axiosInstance'
import type {
  AdminUser,
  CreateUserRequest,
  RegistrationRequestItem,
  DashboardAdmin,
  CreateDashboardRequest,
  UpdateDashboardRequest,
  GrantAccessRequest,
  ProcessingLog,
  LogFilters,
  LayoutRead,
  DashboardDetail,
} from '../../../shared/types/api.types'

// User Management API
export async function getUsers(): Promise<AdminUser[]> {
  const response = await axiosInstance.get<AdminUser[]>('/admin/users')
  return response.data
}

export async function createUser(data: CreateUserRequest): Promise<AdminUser> {
  const response = await axiosInstance.post<AdminUser>('/users/', data)
  return response.data
}

export async function changeUserRole(userId: string, role: string): Promise<AdminUser> {
  const response = await axiosInstance.patch<AdminUser>(`/admin/users/${userId}/role`, { role })
  return response.data
}

export async function deleteUser(userId: string): Promise<void> {
  await axiosInstance.delete(`/admin/users/${userId}`)
}

export async function resetUserPassword(userId: string): Promise<{
  message: string
  user_id: string
  retrieval_token: string
}> {
  const response = await axiosInstance.post<{
    message: string
    user_id: string
    retrieval_token: string
  }>(`/admin/users/${userId}/reset-password`)
  return response.data
}

// Registration Requests API
export async function getRegistrationRequests(): Promise<RegistrationRequestItem[]> {
  const response = await axiosInstance.get<RegistrationRequestItem[]>('/admin/registration-requests')
  return response.data
}

export async function approveRequest(requestId: string): Promise<{
  message: string
  user_id: string
  retrieval_token: string
}> {
  const response = await axiosInstance.post<{
    message: string
    user_id: string
    retrieval_token: string
  }>(`/admin/registration-requests/${requestId}/approve`)
  return response.data
}

export async function retrieveTempPassword(retrievalToken: string): Promise<{
  temp_password: string
}> {
  const response = await axiosInstance.post<{ temp_password: string }>(
    '/admin/temp-passwords',
    { retrieval_token: retrievalToken }
  )
  return response.data
}

export async function rejectRequest(requestId: string): Promise<void> {
  await axiosInstance.post(`/admin/registration-requests/${requestId}/reject`)
}

// Layout API
export async function getLayouts(): Promise<LayoutRead[]> {
  const response = await axiosInstance.get<LayoutRead[]>('/layouts')
  return response.data
}

export async function getLayoutByName(name: string): Promise<LayoutRead | null> {
  const layouts = await getLayouts()
  return layouts.find((layout) => layout.name === name) || null
}

// Dashboard Management API
export async function getDashboardsAdmin(): Promise<DashboardAdmin[]> {
  const response = await axiosInstance.get<DashboardAdmin[]>('/dashboards/')
  return response.data
}

export async function createDashboard(data: CreateDashboardRequest): Promise<DashboardDetail> {
  const payload: Record<string, unknown> = { name: data.name }
  if (data.description) {
    payload.description = data.description
  }
  // Fetch layout by name dynamically instead of using hardcoded UUID mapping
  if (data.layout) {
    const layout = await getLayoutByName(data.layout)
    if (layout) {
      payload.layout_id = layout.id
    }
    // Graceful fallback: layout_id is optional, backend will use default if not provided
  }
  // config is optional - will use backend default if not provided
  const response = await axiosInstance.post<DashboardDetail>('/dashboards/', payload)
  return response.data
}

export async function updateDashboard(
  dashboardId: string,
  data: UpdateDashboardRequest,
): Promise<DashboardDetail> {
  const response = await axiosInstance.put<DashboardDetail>(`/dashboards/${dashboardId}`, data)
  return response.data
}

export async function deleteDashboard(dashboardId: string): Promise<void> {
  await axiosInstance.delete(`/dashboards/${dashboardId}`)
}

export async function grantDashboardAccess(dashboardId: string, data: GrantAccessRequest): Promise<void> {
  await axiosInstance.post(`/dashboards/${dashboardId}/access`, {
    ...data,
    dashboard_id: dashboardId,
  })
}

// Logs API
export async function getLogs(filters?: LogFilters): Promise<ProcessingLog[]> {
  const response = await axiosInstance.get<ProcessingLog[]>('/admin/logs/', { params: filters })
  return response.data
}