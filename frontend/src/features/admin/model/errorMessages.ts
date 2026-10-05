import { ErrorCode } from '../../../shared/types/enums'
import { registerFeatureErrorMessages } from '../../../shared/api/errorSurfaces'

/**
 * Admin feature error message map with English strings.
 * Contains error codes specific to admin operations.
 */
export const adminErrorMessages: Partial<Record<ErrorCode, string>> = {
  [ErrorCode.USER_NOT_FOUND]: 'User not found in system',
  [ErrorCode.PERMISSION_DENIED]: 'Insufficient permissions for administrative operation',
  [ErrorCode.EMAIL_ALREADY_EXISTS]: 'A user with this email already exists',
  [ErrorCode.VALIDATION_ERROR]: 'Administrative data validation error',
  [ErrorCode.INVALID_TRANSITION]: 'Invalid status transition for processing log',
}

registerFeatureErrorMessages('admin', adminErrorMessages)