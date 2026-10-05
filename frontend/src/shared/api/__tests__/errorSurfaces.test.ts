import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

const toastError = vi.fn()

vi.mock('react-hot-toast', () => ({
  toast: {
    error: (...args: unknown[]): void => {
      toastError(...args)
    },
    success: vi.fn(),
  },
}))

import { axiosInstance } from '../axiosInstance'
import { ErrorCode } from '../../types/enums'
import {
  registerFeatureErrorMessages,
  getFeatureErrorMessage,
  SESSION_EXPIRED_MESSAGE,
} from '../errorSurfaces'

/**
 * Installs an adapter that rejects every request with the given HTTP status and
 * RFC 7807 body, so the real response interceptor runs against a deterministic
 * failure without a network.
 */
function installFailureAdapter(status: number, body: Record<string, unknown>): void {
  const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
    const response: AxiosResponse = {
      data: body,
      status,
      statusText: 'Error',
      headers: {},
      config,
    }
    return Promise.reject(
      Object.assign(new Error(`Request failed with status code ${status}`), {
        isAxiosError: true,
        response,
        config,
        toJSON: () => ({}),
      }),
    )
  }
  axiosInstance.defaults.adapter = adapter
}

describe('response interceptor — one error surface per context', () => {
  beforeEach(() => {
    toastError.mockClear()
    axiosInstance.defaults.adapter = undefined
  })

  it('toasts a background-refetch failure when the caller does not opt out', async () => {
    installFailureAdapter(500, {
      type: 'about:blank',
      title: 'Internal server error',
      status: 500,
      detail: 'boom',
      code: ErrorCode.INTERNAL_ERROR,
    })

    await expect(axiosInstance.get('/dashboards/my')).rejects.toThrow()
    expect(toastError).toHaveBeenCalledTimes(1)
  })

  it('does not toast a main-view failure that opted out with skipErrorToast', async () => {
    installFailureAdapter(500, {
      type: 'about:blank',
      title: 'Internal server error',
      status: 500,
      detail: 'boom',
      code: ErrorCode.INTERNAL_ERROR,
    })

    await expect(
      axiosInstance.get('/data/aggregated', { skipErrorToast: true }),
    ).rejects.toThrow()
    expect(toastError).not.toHaveBeenCalled()
  })

  it('resolves a feature-registered code to its feature message', async () => {
    registerFeatureErrorMessages('test-dashboards', {
      [ErrorCode.DASHBOARD_NOT_FOUND]: 'Dashboard not found or has been deleted',
    })

    installFailureAdapter(404, {
      type: 'about:blank',
      title: 'Not found',
      status: 404,
      code: ErrorCode.DASHBOARD_NOT_FOUND,
    })

    await expect(axiosInstance.get('/dashboards/missing')).rejects.toThrow()
    expect(toastError).toHaveBeenCalledTimes(1)
    const [message] = toastError.mock.calls[0] as [string]
    expect(message.startsWith('Dashboard not found or has been deleted')).toBe(true)
  })

  it('exposes exactly one session-expired sentence', () => {
    expect(SESSION_EXPIRED_MESSAGE).toBe('Session expired. Please login again.')
  })

  it('resolves a feature map previously registered for a known code', () => {
    registerFeatureErrorMessages('regression', {
      [ErrorCode.PERMISSION_DENIED]: 'You do not have permission to perform this action',
    })
    expect(getFeatureErrorMessage(ErrorCode.PERMISSION_DENIED)).toBe(
      'You do not have permission to perform this action',
    )
  })
})
