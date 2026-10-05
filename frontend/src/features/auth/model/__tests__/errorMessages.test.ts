import { describe, it, expect } from 'vitest'
import { ErrorCode } from '../../../../shared/types/enums'
import { authErrorMessages } from '../errorMessages'

describe('authErrorMessages', () => {
  it('contains all required auth error codes', () => {
    expect(authErrorMessages[ErrorCode.AUTHENTICATION_FAILED]).toBe('Invalid email or password')
    expect(authErrorMessages[ErrorCode.TOKEN_EXPIRED]).toBe('Session expired. Please log in again.')
    expect(authErrorMessages[ErrorCode.TOKEN_REVOKED]).toBe('Your session was terminated. Please log in again.')
    expect(authErrorMessages[ErrorCode.INVALID_TOKEN]).toBe('Invalid authentication token')
    expect(authErrorMessages[ErrorCode.EMAIL_ALREADY_EXISTS]).toBe('A user with this email is already registered')
    expect(authErrorMessages[ErrorCode.INVALID_EMAIL]).toBe('Please enter a valid email address')
    expect(authErrorMessages[ErrorCode.INVALID_PASSWORD]).toBe('Invalid password')
    expect(authErrorMessages[ErrorCode.RATE_LIMIT_EXCEEDED]).toBe('Too many login attempts. Please try again later.')
  })
})
