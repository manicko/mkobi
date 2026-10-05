import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { MemoryRouter } from 'react-router-dom'

// Mock react-router-dom's navigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// Mock the auth API
vi.mock('../../api/authApi', () => ({
  login: vi.fn(),
  registerRequest: vi.fn(),
  getProfile: vi.fn(),
  logout: vi.fn(),
  refreshToken: vi.fn(),
  logoutClient: vi.fn(),
}))

// Mock the shared token store
vi.mock('../../../../shared/auth/tokenStore', () => ({
  getToken: vi.fn(),
  setToken: vi.fn(),
  removeToken: vi.fn(),
  useAuthToken: vi.fn(),
}))

import { useAuth } from '../useAuth'
import { login, registerRequest, getProfile, logout, refreshToken, logoutClient } from '../../api/authApi'
import { getToken, setToken, removeToken, useAuthToken } from '../../../../shared/auth/tokenStore'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const profile = {
  id: '1',
  email: 'user@test.com',
  role: 'viewer' as const,
  display_name: 'Test User',
  created_at: '',
  force_password_change: false,
}

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuthToken).mockReturnValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('initialization', () => {
    it('goes from loading to settled and exposes the fetched identity', async () => {
      vi.mocked(getToken).mockReturnValue('valid-token')
      vi.mocked(getProfile).mockResolvedValue(profile)
      vi.mocked(useAuthToken).mockReturnValue('valid-token')

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.isLoading).toBe(false))
      expect(result.current.user).toEqual(profile)
      expect(result.current.accessToken).toBe('valid-token')
    })

    it('refreshes silently when no token exists', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockResolvedValue({ access_token: 'new-token', token_type: 'bearer' })
      vi.mocked(getProfile).mockResolvedValue(profile)

      renderHook(() => useAuth(), { wrapper: createWrapper() })

      await waitFor(() => expect(refreshToken).toHaveBeenCalled())
      expect(setToken).toHaveBeenCalledWith('new-token')
    })

    it('clears the token and reports no user when the silent refresh fails', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('No refresh cookie'))

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })

      await waitFor(() => expect(result.current.isLoading).toBe(false))
      expect(result.current.user).toBeNull()
      expect(removeToken).toHaveBeenCalled()
    })
  })

  describe('login', () => {
    it('stores the token and the returned identity', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(login).mockResolvedValue({
        access_token: 'new-token',
        token_type: 'bearer',
        user: profile,
      })

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await result.current.login('user@test.com', 'password123')
      })

      expect(login).toHaveBeenCalledWith('user@test.com', 'password123')
      expect(setToken).toHaveBeenCalledWith('new-token')
      await waitFor(() => expect(result.current.user).toEqual(profile))
    })

    it('clears auth state when login fails', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(login).mockRejectedValue(new Error('Invalid credentials'))

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await expect(result.current.login('user@test.com', 'wrong')).rejects.toThrow('Invalid credentials')
      })

      expect(removeToken).toHaveBeenCalled()
      expect(result.current.user).toBeNull()
    })
  })

  describe('logout', () => {
    it('calls the logout API, clears the client token and the identity', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(logout).mockResolvedValue({ message: 'Logged out successfully' })

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await result.current.logout()
      })

      expect(logout).toHaveBeenCalled()
      expect(logoutClient).toHaveBeenCalled()
      expect(result.current.user).toBeNull()
    })

    it('still clears the identity when the logout API fails', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(logout).mockRejectedValue(new Error('Not logged in'))

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await result.current.logout()
      })

      expect(result.current.user).toBeNull()
    })
  })

  describe('registerRequest', () => {
    it('calls the registerRequest API with the email', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(registerRequest).mockResolvedValue({
        message: 'Registration request submitted',
        id: 'req-123',
      })

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await result.current.registerRequest('newuser@test.com')
      })

      expect(registerRequest).toHaveBeenCalledWith('newuser@test.com')
    })
  })

  describe('getProfile', () => {
    it('refreshes and caches the profile', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(getProfile).mockResolvedValue(profile)

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await result.current.getProfile()
      })

      await waitFor(() => expect(result.current.user).toEqual(profile))
    })

    it('clears auth state and rethrows when the profile fetch fails', async () => {
      vi.mocked(getToken).mockReturnValue(null)
      vi.mocked(refreshToken).mockRejectedValue(new Error('no cookie'))
      vi.mocked(getProfile).mockRejectedValue(new Error('Unauthorized'))

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      await act(async () => {
        await expect(result.current.getProfile()).rejects.toThrow('Unauthorized')
      })

      expect(removeToken).toHaveBeenCalled()
    })
  })
})
