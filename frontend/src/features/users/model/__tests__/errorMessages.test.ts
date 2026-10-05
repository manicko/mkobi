import { describe, it, expect } from 'vitest'
import { ErrorCode } from '../../../../shared/types/enums'
import { userErrorMessages } from '../errorMessages'

describe('userErrorMessages', () => {
  it('contains all required user error codes', () => {
    expect(userErrorMessages[ErrorCode.USER_NOT_FOUND]).toBe('User not found')
    expect(userErrorMessages[ErrorCode.INVALID_PASSWORD]).toBe('Current password is incorrect')
    expect(userErrorMessages[ErrorCode.VALIDATION_ERROR]).toBe('Profile data validation error')
  })
})
