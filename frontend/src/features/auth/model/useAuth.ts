import { useCallback, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import type { AuthResponse, UserProfile } from '../../../shared/types/api.types'
import {
  login as apiLogin,
  registerRequest as apiRegisterRequest,
  getProfile as apiGetProfile,
  logout as apiLogout,
  logoutClient,
  refreshToken as apiRefreshToken,
} from '../api/authApi'
import { getToken, setToken, removeToken } from '../../../shared/auth/tokenStore'
import { useAuthToken } from '../../../shared/auth/tokenStore'
import {
  AUTH_IDENTITY_QUERY_KEY,
  registerIdentityLoader,
  useAuthIdentity,
} from '../../../shared/auth/identity'
import { registerLogoutHandler, logout as performLogout } from '../../../shared/auth/actions'

/**
 * Fetch the signed-in profile for the shared identity cache.
 *
 * With no access token, a silent refresh is attempted first so a reload with a
 * live refresh cookie restores the session. Any failure clears the token and
 * returns `null` — the single signed-in state for an anonymous visitor. The
 * failure message is carried on the error's `message`; there is one arm, not
 * two byte-identical ones.
 */
async function loadIdentity(): Promise<UserProfile | null> {
  const token = getToken()
  if (!token) {
    const refreshed = await apiRefreshToken()
    setToken(refreshed.access_token)
  }
  return apiGetProfile()
}

// Register once at module load. The shared layer reads identity through the
// registered loader; the auth feature never has to be imported by `shared/`.
registerIdentityLoader(async () => {
  try {
    return await loadIdentity()
  } catch (error) {
    removeToken()
    throw error
  }
})

registerLogoutHandler(async () => {
  try {
    await apiLogout()
  } catch {
    // Ignore errors - user may already be logged out server-side
  }
  logoutClient()
})

export function useAuth() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { user, isLoading } = useAuthIdentity()
  const accessToken = useAuthToken()

  // Security: a forced password change (admin reset) must land on the change
  // form. The redirect watches the single cached identity, so it fires once per
  // identity state rather than once per mounted component.
  useEffect(() => {
    if (user?.force_password_change) {
      void navigate('/profile/change-password?force=true')
    }
  }, [user?.force_password_change, navigate])

  const setIdentity = useCallback(
    (profile: UserProfile | null) => {
      queryClient.setQueryData(AUTH_IDENTITY_QUERY_KEY, profile)
    },
    [queryClient],
  )

  const getProfile = useCallback(async () => {
    try {
      const profile = await apiGetProfile()
      setIdentity(profile)
    } catch (error) {
      removeToken()
      setIdentity(null)
      throw error
    }
  }, [setIdentity])

  const login = useCallback(
    async (email: string, password: string): Promise<AuthResponse> => {
      try {
        const response = await apiLogin(email, password)
        setToken(response.access_token)
        setIdentity(response.user)
        return response
      } catch (error) {
        removeToken()
        setIdentity(null)
        throw error
      }
    },
    [setIdentity],
  )

  const registerRequest = useCallback(async (email: string) => {
    await apiRegisterRequest(email)
  }, [])

  const logout = useCallback(async () => {
    await performLogout()
    setIdentity(null)
  }, [setIdentity])

  return {
    user,
    accessToken,
    isLoading,
    login,
    logout,
    registerRequest,
    getProfile,
  }
}
