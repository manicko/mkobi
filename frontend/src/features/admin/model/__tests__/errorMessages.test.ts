import { describe, it, expect } from 'vitest'
import { ErrorCode } from '../../../../shared/types/enums'
import { adminErrorMessages } from '../errorMessages'

describe('adminErrorMessages', () => {
  it('contains all required admin error codes', () => {
    expect(adminErrorMessages[ErrorCode.USER_NOT_FOUND]).toBe('User not found in system')
    expect(adminErrorMessages[ErrorCode.PERMISSION_DENIED]).toBe('Insufficient permissions for administrative operation')
    expect(adminErrorMessages[ErrorCode.EMAIL_ALREADY_EXISTS]).toBe('A user with this email already exists')
    expect(adminErrorMessages[ErrorCode.VALIDATION_ERROR]).toBe('Administrative data validation error')
  })
})
