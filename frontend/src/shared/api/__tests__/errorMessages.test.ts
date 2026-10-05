import { describe, it, expect } from 'vitest'
import { getErrorMessage, sharedErrorMessages, DEFAULT_ERROR_MESSAGE } from '../errorMessages'
import { ErrorCode } from '../../types/enums'

describe('getErrorMessage', () => {
  it('returns feature-specific message when provided', () => {
    const featureMessages = {
      [ErrorCode.AUTHENTICATION_FAILED]: 'Feature auth error message',
    }

    const result = getErrorMessage(ErrorCode.AUTHENTICATION_FAILED, featureMessages)

    expect(result).toBe('Feature auth error message')
  })

  it('falls back to shared message when feature message not provided', () => {
    const result = getErrorMessage(ErrorCode.AUTHENTICATION_FAILED)

    expect(result).toBe(sharedErrorMessages[ErrorCode.AUTHENTICATION_FAILED])
  })

  it('returns shared message when feature map is empty', () => {
    const result = getErrorMessage(ErrorCode.GRAPH_NOT_FOUND, {})

    // Empty feature map falls back to shared map
    expect(result).toBe(sharedErrorMessages[ErrorCode.GRAPH_NOT_FOUND])
  })

  it('returns shared message when nothing else matches', () => {
    const unknownCode = ErrorCode.GRAPH_NOT_FOUND // Uses shared map message

    const result = getErrorMessage(unknownCode)

    // This should return the shared message
    expect(result).toBe(sharedErrorMessages[unknownCode])
  })

  it('feature message takes priority over shared message', () => {
    const featureMessages = {
      [ErrorCode.AUTHENTICATION_FAILED]: 'Custom auth message',
    }

    const result = getErrorMessage(ErrorCode.AUTHENTICATION_FAILED, featureMessages)

    expect(result).toBe('Custom auth message')
    expect(result).not.toBe(sharedErrorMessages[ErrorCode.AUTHENTICATION_FAILED])
  })

  it('detail takes priority over default when no message found', () => {
    const result = getErrorMessage(
      ErrorCode.DASHBOARD_NOT_FOUND,
      {}, // Empty feature map
      'Custom detail message',
    )

    // Since shared has DASHBOARD_NOT_FOUND, it returns the shared message
    expect(result).toBe(sharedErrorMessages[ErrorCode.DASHBOARD_NOT_FOUND])
  })

  it('returns default message for unhandled error', () => {
    // Test that DEFAULT_ERROR_MESSAGE is used as fallback
    expect(DEFAULT_ERROR_MESSAGE).toBe('An error occurred')
  })
})

describe('sharedErrorMessages', () => {
  it('contains all general error codes', () => {
    expect(sharedErrorMessages[ErrorCode.INTERNAL_ERROR]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.SERVICE_UNAVAILABLE]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.RATE_LIMIT_EXCEEDED]).toBeDefined()
  })

  it('contains all authentication error codes', () => {
    expect(sharedErrorMessages[ErrorCode.AUTHENTICATION_FAILED]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.TOKEN_EXPIRED]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.TOKEN_REVOKED]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INVALID_TOKEN]).toBeDefined()
  })

  it('contains all authorization error codes', () => {
    expect(sharedErrorMessages[ErrorCode.PERMISSION_DENIED]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INSUFFICIENT_PERMISSIONS]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.ACCESS_DENIED]).toBeDefined()
  })

  it('contains all resource error codes', () => {
    expect(sharedErrorMessages[ErrorCode.NOT_FOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.DASHBOARD_NOT_FOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.USER_NOT_FOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.GRAPH_NOT_FOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.FILTER_NOT_FOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.LAYOUT_NOT_FOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.PROCESSING_CONFIG_NOT_FOUND]).toBeDefined()
  })

  it('contains all validation error codes', () => {
    expect(sharedErrorMessages[ErrorCode.VALIDATION_ERROR]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INVALID_EMAIL]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INVALID_PASSWORD]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.MISSING_REQUIRED_FIELD]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INVALID_FIELD_VALUE]).toBeDefined()
  })

  it('contains all file error codes', () => {
    expect(sharedErrorMessages[ErrorCode.FILE_UPLOAD_ERROR]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.FILE_TOO_LARGE]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INVALID_FILE_TYPE]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.FILE_PROCESSING_ERROR]).toBeDefined()
  })

  it('contains all conflict error codes', () => {
    expect(sharedErrorMessages[ErrorCode.EMAIL_ALREADY_EXISTS]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.FILTER_ALREADY_BOUND]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.DUPLICATE_RESOURCE]).toBeDefined()
  })

  it('contains all processing error codes', () => {
    expect(sharedErrorMessages[ErrorCode.PROCESSING_FAILED]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.PROCESSING_IN_PROGRESS]).toBeDefined()
    expect(sharedErrorMessages[ErrorCode.INVALID_TRANSITION]).toBeDefined()
  })

  it('all messages are in English', () => {
    const cyrillicPattern = /[а-яё]/i
    Object.values(sharedErrorMessages).forEach((message) => {
      expect(cyrillicPattern.test(message)).toBe(false)
    })
  })
})
