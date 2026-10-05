import { ErrorCode } from '../../../shared/types/enums'
import { registerFeatureErrorMessages } from '../../../shared/api/errorSurfaces'

/**
 * Auth feature error message map with English strings.
 * Contains error codes specific to authentication flows.
 */
export const authErrorMessages: Partial<Record<ErrorCode, string>> = {
  [ErrorCode.AUTHENTICATION_FAILED]: 'Invalid email or password',
  [ErrorCode.TOKEN_EXPIRED]: 'Session expired. Please log in again.',
  [ErrorCode.TOKEN_REVOKED]: 'Your session was terminated. Please log in again.',
  [ErrorCode.INVALID_TOKEN]: 'Invalid authentication token',
  [ErrorCode.EMAIL_ALREADY_EXISTS]: 'A user with this email is already registered',
  [ErrorCode.INVALID_EMAIL]: 'Please enter a valid email address',
  [ErrorCode.INVALID_PASSWORD]: 'Invalid password',
  [ErrorCode.RATE_LIMIT_EXCEEDED]: 'Too many login attempts. Please try again later.',
}

registerFeatureErrorMessages('auth', authErrorMessages)