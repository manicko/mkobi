import axios, { AxiosError } from 'axios'
import { toast } from 'react-hot-toast'
import { getTokenWithExpirationCheck, removeToken, setToken } from '../../features/auth/model/authToken'
import { getRefreshHandler } from './refreshHandler'
import { extractApiError } from './errorHandler'
import { getErrorMessage } from './errorMessages'
import { getFeatureErrorMessage, SESSION_EXPIRED_MESSAGE } from './errorSurfaces'
import './axiosRequestConfig'

export const axiosInstance = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  maxRedirects: 0,
})

// Request interceptor - add JWT token with expiration check
axiosInstance.interceptors.request.use(
  (config) => {
    const token = getTokenWithExpirationCheck()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    } else {
      // Token was expired and removed
      removeToken()
    }
    return config
  },
  (error) => Promise.reject(error instanceof Error ? error : new Error(String(error)))
)

// Request queuing for concurrent 401 handling
let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (error: Error) => void
}> = []

type ProcessQueueParams =
  | { error: Error; token?: never }
  | { error?: never; token: string }

const processQueue = (params: ProcessQueueParams): void => {
  failedQueue.forEach((prom) => {
    if (params.error) {
      prom.reject(params.error)
    } else {
      prom.resolve(params.token)
    }
  })
  failedQueue = []
}

// Response interceptor - handle errors
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status

    // Handle rate limit (429) - skip toast/redirect, let caller handle silently
    // This is important for refresh endpoint where rate limiting is expected behavior
    if (status === 429) {
      return Promise.reject(error)
    }

    if (status === 401) {
      // Skip redirect/toast for login endpoint - let inline form error handle it
      if (error.config?.url?.includes('/auth/login')) {
        return Promise.reject(error)
      }

      // Skip retry for refresh endpoint - prevents infinite loop when no refresh cookie exists
      if (error.config?.url?.includes('/auth/refresh')) {
        removeToken()
        return Promise.reject(error)
      }

      const originalConfig = error.config

      // If config is missing, reject immediately
      if (!originalConfig) {
        removeToken()
        toast.error(SESSION_EXPIRED_MESSAGE)
        window.location.href = '/login'
        return Promise.reject(error)
      }

      // If already refreshing, queue the request
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalConfig.headers.Authorization = `Bearer ${token}`
            return axiosInstance(originalConfig)
          })
          .catch((err) => Promise.reject(err instanceof Error ? err : new Error(String(err))))
      }

      // Mark as refreshing and attempt token refresh
      isRefreshing = true

      try {
        // Use registered refresh handler instead of direct import
        const handler = getRefreshHandler()
        if (!handler) {
          throw new Error('Refresh handler not registered')
        }
        const newToken = await handler()
        setToken(newToken.access_token)
        processQueue({ token: newToken.access_token })
        originalConfig.headers.Authorization = `Bearer ${newToken.access_token}`
        return axiosInstance(originalConfig)
      } catch (err) {
        const errorToReject = err instanceof Error ? err : new Error(String(err))
        processQueue({ error: errorToReject })
        removeToken()
        toast.error(SESSION_EXPIRED_MESSAGE)
        window.location.href = '/login'
        return Promise.reject(errorToReject)
      } finally {
        isRefreshing = false
      }
    }

    // Handle 403 and other non-401/429 errors with a localized toast.
    // One surface per context: a caller that renders its own persistent inline
    // message opts out with `skipErrorToast`, so the failure is not shown twice.
    if (status && status !== 401 && status !== 429) {
      // Skip toast for login endpoint - let inline form error handle it
      if (error.config?.url?.includes('/auth/login')) {
        return Promise.reject(error)
      }
      if (error.config?.skipErrorToast) {
        return Promise.reject(error)
      }
      const { code, message } = extractApiError(error)
      const localizedMessage = getFeatureErrorMessage(code) ?? getErrorMessage(code)
      const finalMessage = message ? `${localizedMessage}: ${message}` : localizedMessage
      toast.error(finalMessage)
    }
    return Promise.reject(error)
  }
)

export default axiosInstance