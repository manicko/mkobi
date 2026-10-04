/**
 * Shared enum definitions matching backend StrEnum values.
 * These constants ensure type safety and consistency between frontend and backend.
 * Using const objects instead of enums for erasableSyntaxOnly compatibility.
 */

export const UserRole = {
  ADMIN: 'admin',
  EDITOR: 'editor',
  VIEWER: 'viewer',
} as const

export type UserRole = (typeof UserRole)[keyof typeof UserRole]

export const DashboardPermission = {
  VIEW: 'view',
  EDIT: 'edit',
  ADMIN: 'admin',
} as const

export type DashboardPermission = (typeof DashboardPermission)[keyof typeof DashboardPermission]

export const GraphType = {
  BAR: 'bar',
  LINE: 'line',
  PIE: 'pie',
  TABLE: 'table',
} as const

export type GraphType = (typeof GraphType)[keyof typeof GraphType]

export const FilterType = {
  SELECT: 'select',
  MULTISELECT: 'multiselect',
  RANGE: 'range',
  DATE: 'date',
} as const

export type FilterType = (typeof FilterType)[keyof typeof FilterType]

export const RegistrationStatus = {
  PENDING: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
} as const

export type RegistrationStatus = (typeof RegistrationStatus)[keyof typeof RegistrationStatus]

export const UploadMode = {
  OVERWRITE: 'overwrite',
  APPEND: 'append',
} as const

export type UploadMode = (typeof UploadMode)[keyof typeof UploadMode]

export const ProcessingStatus = {
    STARTED: 'started',
    UPLOADED: 'uploaded',
    PROCESSING: 'processing',
    COMPLETED: 'completed',
    FAILED: 'failed',
} as const

export type ProcessingStatus = (typeof ProcessingStatus)[keyof typeof ProcessingStatus]

export const FileUploadStatus = {
  PENDING: 'pending',
  UPLOADING: 'uploading',
  SUCCESS: 'success',
  ERROR: 'error',
} as const

export type FileUploadStatus = (typeof FileUploadStatus)[keyof typeof FileUploadStatus]

/**
 * Bar chart display mode, mirroring the backend ``BarmodeEnum``
 * (``src/mkobi/models/enums.py``). Named verbatim after the backend class so the
 * cross-tier parity test keys on the class name with no rename table.
 */
export const BarmodeEnum = { GROUP: 'group', STACK: 'stack' } as const
export type BarmodeEnum = (typeof BarmodeEnum)[keyof typeof BarmodeEnum]

/**
 * Server-only `StrEnum` families deliberately not mirrored to the client:
 * either there is no client consumer, or the family is backend presentation
 * vocabulary with no client counterpart (D-08-3 for `ButtonVariant` and
 * `ComponentSize`). Recorded here so a missing mirror is an explicit decision,
 * not an undocumented absence.
 */
export const SERVER_ONLY_FAMILIES = [
  'LeaseAcquisitionResult',
  'ReconcilerLeaseState',
  'EnvironmentEnum',
  'MimeTypeEnum',
  'FileExtensionEnum',
  'ButtonVariant',
  'ComponentSize',
  'OrientationEnum',
  'YoyModeEnum',
  'AggregationFunctionEnum',
  'FilterOperatorEnum',
] as const

/**
 * Client-only families with no backend counterpart. Recorded so the
 * two-directional asymmetry between the tiers is explicit.
 */
export const CLIENT_ONLY_FAMILIES = ['FileUploadStatus'] as const

/**
 * Frontend ErrorCode enum matching backend StrEnum values.
 * All codes use UPPER_SNAKE_CASE convention for type safety.
 */
export const ErrorCode = {
  // General errors
  INTERNAL_ERROR: 'INTERNAL_ERROR',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
  RATE_LIMIT_EXCEEDED: 'RATE_LIMIT_EXCEEDED',
  // Authentication errors
  AUTHENTICATION_FAILED: 'AUTHENTICATION_FAILED',
  TOKEN_EXPIRED: 'TOKEN_EXPIRED',
  TOKEN_REVOKED: 'TOKEN_REVOKED',
  INVALID_TOKEN: 'INVALID_TOKEN',
  // Authorization errors
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  INSUFFICIENT_PERMISSIONS: 'INSUFFICIENT_PERMISSIONS',
  ACCESS_DENIED: 'ACCESS_DENIED',
  // Resource errors
  NOT_FOUND: 'NOT_FOUND',
  DASHBOARD_NOT_FOUND: 'DASHBOARD_NOT_FOUND',
  USER_NOT_FOUND: 'USER_NOT_FOUND',
  GRAPH_NOT_FOUND: 'GRAPH_NOT_FOUND',
  FILTER_NOT_FOUND: 'FILTER_NOT_FOUND',
  LAYOUT_NOT_FOUND: 'LAYOUT_NOT_FOUND',
  PROCESSING_CONFIG_NOT_FOUND: 'PROCESSING_CONFIG_NOT_FOUND',
  // Validation errors
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  INVALID_EMAIL: 'INVALID_EMAIL',
  INVALID_PASSWORD: 'INVALID_PASSWORD',
  MISSING_REQUIRED_FIELD: 'MISSING_REQUIRED_FIELD',
  INVALID_FIELD_VALUE: 'INVALID_FIELD_VALUE',
  // File errors
  FILE_UPLOAD_ERROR: 'FILE_UPLOAD_ERROR',
  FILE_TOO_LARGE: 'FILE_TOO_LARGE',
  INVALID_FILE_TYPE: 'INVALID_FILE_TYPE',
  FILE_PROCESSING_ERROR: 'FILE_PROCESSING_ERROR',
  // Conflict errors
  EMAIL_ALREADY_EXISTS: 'EMAIL_ALREADY_EXISTS',
  FILTER_ALREADY_BOUND: 'FILTER_ALREADY_BOUND',
  DUPLICATE_RESOURCE: 'DUPLICATE_RESOURCE',
  // Processing errors
  PROCESSING_FAILED: 'PROCESSING_FAILED',
  PROCESSING_IN_PROGRESS: 'PROCESSING_IN_PROGRESS',
  INVALID_TRANSITION: 'INVALID_TRANSITION',
} as const

export type ErrorCode = (typeof ErrorCode)[keyof typeof ErrorCode]
