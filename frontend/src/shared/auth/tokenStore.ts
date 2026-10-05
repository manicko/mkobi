import { z } from 'zod'
import { useSyncExternalStore } from 'react'

// JWT payload schema for runtime validation
// Access tokens contain user_id; refresh tokens contain sub
// exp is optional to handle tokens without expiration claim
const JWTPayloadSchema = z.object({
  sub: z.string().optional(),
  exp: z.number().optional(),
  user_id: z.string().optional(),
  role: z.string().optional(),
})

// JWT payload interface matching backend token structure
// Using string types for role to match Zod validation at runtime
export interface JWTPayload {
  sub?: string
  exp?: number
  user_id?: string
  role?: string
}

/**
 * Parse and validate JWT payload with runtime type checking.
 * Throws explicit error for malformed tokens instead of returning undefined.
 */
export function parseJWTPayload(token: string): JWTPayload {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) {
      throw new Error('Invalid JWT structure: token must have 3 parts')
    }

    const payloadJson = atob(parts[1])
    // Unknown type for JSON.parse result, validated by Zod schema below
    const rawPayload: unknown = JSON.parse(payloadJson)
    const result = JWTPayloadSchema.safeParse(rawPayload)

    if (!result.success) {
      throw new Error(`Invalid JWT payload: ${result.error.message}`)
    }

    return result.data
  } catch (error) {
    // Re-throw with cause to preserve the original error context
    throw new Error('Failed to parse JWT payload', { cause: error })
  }
}

// Token storage with memory-first approach for security
//
// Production behavior (USE_MEMORY_STORAGE = true):
//   Tokens are held only in a module-level JS variable (memoryToken).
//   They are never written to disk or browser storage, which means:
//   - Tokens survive page in-memory (same JS context) but are lost on full page reload/navigation.
//   - Tokens are NOT vulnerable to XSS-based exfiltration via localStorage/sessionStorage.
//   - This is the most secure option for storing JWTs in a SPA.
//
// Development behavior (USE_MEMORY_STORAGE = false):
//   Tokens fall back to sessionStorage so that they persist across hot-reloads
//   and page refreshes during local development. This is a convenience trade-off:
//   - sessionStorage is accessible to any JS running on the page (XSS risk).
//   - sessionStorage is cleared when the tab is closed.
//   - This mode MUST NEVER be used in production builds.

let memoryToken: string | null = null
const TOKEN_KEY = 'access_token'

// Check if we're in a browser environment
const isBrowser = typeof window !== 'undefined'

// When true (production build), tokens are stored in memory only.
// When false (development), sessionStorage is used as a convenience fallback.
const USE_MEMORY_STORAGE = import.meta.env.PROD

// Subscriber list for reactive token updates
type TokenListener = (token: string | null) => void
const tokenListeners: Set<TokenListener> = new Set()

/**
 * Get the current token value for notifications.
 * Returns the correct token based on storage mode.
 */
function getCurrentToken(): string | null {
  if (USE_MEMORY_STORAGE) {
    return memoryToken
  }
  // Fallback to sessionStorage for development
  return isBrowser ? sessionStorage.getItem(TOKEN_KEY) : null
}

/**
 * Subscribe to token changes. Returns an unsubscribe function.
 * Used by useSyncExternalStore to enable reactive token access in React hooks.
 * In development mode, also listens to storage events for cross-tab updates.
 */
export function subscribeToken(listener: TokenListener): () => void {
  tokenListeners.add(listener)

  // In development mode, also listen for storage events (cross-tab sync)
  const storageHandler = () => {
    listener(getCurrentToken())
  }
  if (!USE_MEMORY_STORAGE && isBrowser) {
    window.addEventListener('storage', storageHandler)
  }

  return () => {
    tokenListeners.delete(listener)
    if (!USE_MEMORY_STORAGE && isBrowser) {
      window.removeEventListener('storage', storageHandler)
    }
  }
}

/**
 * Get current token snapshot for useSyncExternalStore.
 */
export function getSnapshot(): string | null {
  if (USE_MEMORY_STORAGE) {
    return memoryToken
  }
  // Fallback to sessionStorage for development
  return isBrowser ? sessionStorage.getItem(TOKEN_KEY) : null
}

/**
 * Server snapshot for useSyncExternalStore (used during SSR).
 */
export function getServerSnapshot(): string | null {
  return null
}

export function getToken(): string | null {
  if (USE_MEMORY_STORAGE) {
    return memoryToken
  }
  // Fallback to sessionStorage for development
  return isBrowser ? sessionStorage.getItem(TOKEN_KEY) : null
}

export function setToken(token: string): void {
  if (USE_MEMORY_STORAGE) {
    memoryToken = token
  } else {
    // Use sessionStorage for development
    if (isBrowser) {
      sessionStorage.setItem(TOKEN_KEY, token)
    }
  }
  // Notify all listeners of the token change
  const currentToken = getCurrentToken()
  tokenListeners.forEach((listener) => listener(currentToken))
}

export function removeToken(): void {
  memoryToken = null
  if (isBrowser) {
    sessionStorage.removeItem(TOKEN_KEY)
  }
  // Notify all listeners of the token change
  tokenListeners.forEach((listener) => listener(null))
}

// Token expiration check (if JWT has expiration)
export function isTokenExpired(token: string): boolean {
  try {
    const payload = parseJWTPayload(token)
    if (!payload.exp) return false

    const expirationTime = payload.exp * 1000 // Convert to milliseconds
    return Date.now() >= expirationTime
  } catch {
    // If we can't parse the token, assume it's invalid
    return true
  }
}

export function getTokenWithExpirationCheck(): string | null {
  const token = getToken()
  if (!token) return null

  if (isTokenExpired(token)) {
    removeToken()
    return null
  }

  return token
}

/**
 * Reactive hook to access the current auth token.
 * Uses useSyncExternalStore to notify React when the token changes (login/logout).
 * This ensures TanStack Query hooks can re-evaluate their `enabled` state reactively.
 */
export function useAuthToken(): string | null {
  return useSyncExternalStore(subscribeToken, getSnapshot, getServerSnapshot)
}