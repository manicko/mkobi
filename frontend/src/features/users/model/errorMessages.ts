import { ErrorCode } from '../../../shared/types/enums'
import { registerFeatureErrorMessages } from '../../../shared/api/errorSurfaces'

/**
 * Users feature error message map with English strings.
 * Contains error codes specific to user profile operations.
 */
export const userErrorMessages: Partial<Record<ErrorCode, string>> = {
  [ErrorCode.USER_NOT_FOUND]: 'User not found',
  [ErrorCode.INVALID_PASSWORD]: 'Current password is incorrect',
  [ErrorCode.VALIDATION_ERROR]: 'Profile data validation error',
}

registerFeatureErrorMessages('users', userErrorMessages)