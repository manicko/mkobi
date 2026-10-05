import { ErrorCode } from '../../../shared/types/enums'
import { registerFeatureErrorMessages } from '../../../shared/api/errorSurfaces'

/**
 * Dashboards feature error message map with English strings.
 * Contains error codes specific to dashboard operations.
 */
export const dashboardErrorMessages: Partial<Record<ErrorCode, string>> = {
  [ErrorCode.DASHBOARD_NOT_FOUND]: 'Dashboard not found or has been deleted',
  [ErrorCode.PERMISSION_DENIED]: 'You do not have permission to perform this action',
  [ErrorCode.ACCESS_DENIED]: 'Access to dashboard denied',
  [ErrorCode.VALIDATION_ERROR]: 'Dashboard data validation error',
}

// Feature→code registry consumed by the shared response interceptor, so an
// error code maps to a sentence without every feature inventing a string.
registerFeatureErrorMessages('dashboards', dashboardErrorMessages)