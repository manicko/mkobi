import type { UserRole, DashboardPermission, GraphType, FilterType, ProcessingStatus, RegistrationStatus, BarmodeEnum } from './enums'
import type { Data } from 'react-plotly.js'
import { ErrorCode } from './enums'

// Re-export ErrorCode type for external use
export type { ErrorCode }

/**
 * SuccessResponse interface for endpoints returning a simple success message.
 */
export interface SuccessResponse {
  message: string
}

/**
 * ApiError interface matching backend RFC 7807 Problem Details format.
 * All fields are required per the specification.
 */
export interface ApiError {
  type: string
  title: string
  status: number
  detail: string
  code: ErrorCode
  details?: Record<string, unknown>
}

/**
 * Legacy FastAPI validation error format structure.
 */
export interface ValidationFieldError {
  loc: string[]
  msg: string
  type: string
  input?: string
}

// Layout type matching backend LayoutRead model (moved from adminApi.ts)
export interface LayoutRead {
  id: string
  name: string
  definition: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface UserProfile {
  id: string
  email: string
  role: UserRole
  display_name: string
  created_at: string
  force_password_change: boolean
}

export interface DashboardSummary {
  id: string
  name: string
  description: string | null
  permission: DashboardPermission
  created_at: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface Token {
  access_token: string
  token_type: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: UserProfile
}

export interface Dashboard {
  id: string
  name: string
  description: string | null
  config: DashboardConfig
}

export interface Filter {
  id: string
  name: string
  type: FilterType
  options?: Record<string, unknown>
}

export interface UploadResponse {
  task_id: string
  filename: string
  dashboard_id: string
  status: string
  message: string
  uploaded_at: string
}

export interface DashboardConfig {
  graph_types: GraphType[]
  filters?: DashboardFilterConfig[]
  aggregations?: DashboardAggregationConfig[]
  charts?: DashboardChartConfig[]
  title?: string
  description?: string
}

export interface DashboardFilterConfig {
  field: string
  type: string
  multi?: boolean
  source?: string
  options?: Array<{ label: string; value: string }>
  default?: string | string[] | number
}

export interface DashboardAggregationConfig {
  type: string
  field: string
}

export interface DashboardChartConfig {
  type: GraphType
  x?: string
  y?: string
  title?: string
  config?: Record<string, unknown>
}

export interface FilterDetail {
  id: string
  name: string
  type: FilterType
  config: FilterConfig
}

export interface FilterConfig {
  field: string
  source?: string
  multi?: boolean
  min?: number
  max?: number
  options?: Array<{ label: string; value: string }>
}

export interface FilterValuesResponse {
  filter_name: string
  values: string[]
}

export interface RegistrationRequest {
  email: string
}

export interface RegistrationResponse {
  message: string
  id: string
}

export interface DashboardDetail {
  id: string
  name: string
  description: string | null
  config: DashboardConfig
  permission: DashboardPermission
  layout_id: string | null
  layout: LayoutRead | null
  created_at: string
  updated_at: string
}

export interface AggregatedDataRequest {
  dashboard_id: string
  graph_id?: string
  filters?: string
}

export interface AggregatedDataResponse {
  graphs: GraphDataWithConfig[]
  /** The dashboard-wide true, untruncated row count (server-supplied). */
  total_rows: number
  /** True when any graph's rows were bounded by the server caps. */
  truncated: boolean
}

export interface AxisConfig {
  title?: string
  label?: string
  range?: number[]
  type?: string
}

export interface ChartLayoutConfig {
  title?: string
  xaxis?: AxisConfig
  yaxis?: AxisConfig
  showlegend?: boolean
  height?: number
  width?: number
  template?: string
}

export interface GraphDataWithConfig {
  graph_id: string
  type: GraphType
  name: string
  data: Data[]
  /**
   * The graph's true, untruncated row count, supplied by the server. The
   * "Showing N of M" status line renders from this field — never from a
   * client-side count of `data`, which would be an invented signal.
   */
  total_rows: number
  /** True exactly when `data` holds fewer rows than `total_rows`. */
  rows_truncated: boolean
  layout?: ChartLayoutConfig
  config?: {
    x?: string
    color?: string
    metrics?: string[]
    orientation?: string
    barmode?: BarmodeEnum
  }
}

// Upload types
// UploadMode is now imported from './enums'

export interface ProcessingStatusResponse {
  task_id: string
  filename: string
  dashboard_id: string
  status: ProcessingStatus
  progress: number
  message?: string
  started_at: string | null
  finished_at: string | null
  // Error code for RFC 7807 compliant error reporting when processing fails
  error_code?: ErrorCode | null
}

export interface ProcessingResult {
  success: boolean
  task_id: string
  dashboard_id: string
  rows_processed: number
  message: string
}

// Admin types
export interface AdminUser {
  id: string
  email: string
  role: UserRole
  created_at: string
  force_password_change: boolean
}

export interface UpdateUserRoleRequest {
  role: UserRole
}

export interface CreateUserRequest {
  email: string
  password: string
  role: UserRole
}

export interface RegistrationRequestItem {
  id: string
  email: string
  status: RegistrationStatus
  requested_by_ip?: string
  reviewed_by?: string
  reviewed_at?: string
  created_at: string
}

export interface DashboardAdmin {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface CreateDashboardRequest {
  name: string
  description?: string
  layout?: string
}

export interface UpdateDashboardRequest {
  name?: string
  description?: string
  layout_id?: string | null
  config?: DashboardConfig
}

export interface DashboardAccess {
  user_id: string
  dashboard_id: string
  permission: DashboardPermission
}

export interface GrantAccessRequest {
  dashboard_id: string
  user_id: string
  permission: DashboardPermission
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
  confirm_password: string
}

export interface ProcessingLog {
  id: string
  dashboard_id: string | null
  dashboard_name?: string | null
  status: ProcessingStatus
  message?: string
  started_at: string | null
  finished_at: string | null
  // Error code for RFC 7807 compliant error reporting when processing fails
  error_code?: ErrorCode | null
}

export interface LogFilters {
  dashboard_id?: string
  status_filter?: ProcessingStatus
  date_from?: string
  date_to?: string
}
