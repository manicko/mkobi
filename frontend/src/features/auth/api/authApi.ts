import { axiosInstance } from '../../../shared/api/axiosInstance'
import type { AuthResponse, Token, UserProfile, RegistrationResponse, SuccessResponse } from '../../../shared/types/api.types'
import { removeToken } from '../../../shared/auth/tokenStore'
import { registerRefreshHandler } from '../../../shared/api/refreshHandler'

export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await axiosInstance.post<AuthResponse>('/auth/login', { email, password })
  return response.data
}

export async function refreshToken(): Promise<Token> {
  const response = await axiosInstance.post<Token>('/auth/refresh')
  return response.data
}

export async function registerRequest(email: string): Promise<RegistrationResponse> {
  const response = await axiosInstance.post<RegistrationResponse>('/auth/register-request', { email })
  return response.data
}

export async function getProfile(): Promise<UserProfile> {
  const response = await axiosInstance.get<UserProfile>('/auth/me')
  return response.data
}

export async function logout(): Promise<SuccessResponse> {
  const response = await axiosInstance.post<SuccessResponse>('/auth/logout')
  return response.data
}

export function logoutClient(): void {
  removeToken()
}

// Register the refresh handler to break circular dependency
// This must happen after refreshToken is defined
registerRefreshHandler(refreshToken)