import { describe, it, expect } from 'vitest'
import { ErrorCode } from '../../../../shared/types/enums'
import { dashboardErrorMessages } from '../errorMessages'

describe('dashboardErrorMessages', () => {
  it('contains all required dashboard error codes', () => {
    expect(dashboardErrorMessages[ErrorCode.DASHBOARD_NOT_FOUND]).toBe('Dashboard not found or has been deleted')
    expect(dashboardErrorMessages[ErrorCode.PERMISSION_DENIED]).toBe('You do not have permission to perform this action')
    expect(dashboardErrorMessages[ErrorCode.ACCESS_DENIED]).toBe('Access to dashboard denied')
    expect(dashboardErrorMessages[ErrorCode.VALIDATION_ERROR]).toBe('Dashboard data validation error')
  })
})
