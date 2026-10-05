/**
 * Shared-side identity accessor.
 *
 * Layer rule: `shared/` must never import from `features/`. The auth feature
 * owns *how* identity is fetched; this module owns *where* it is read. The auth
 * feature registers a loader once at startup, and every `shared/` consumer —
 * the header, the route guards — reads the single cached identity through the
 * hook below. That keeps one identity source regardless of how many components
 * mount, and keeps the dependency arrow pointing shared ← features.
 */

import { useQuery } from '@tanstack/react-query'
import type { UserProfile } from '../types/api.types'

/** The one cache key under which the signed-in identity lives. */
export const AUTH_IDENTITY_QUERY_KEY = ['auth', 'identity'] as const

/** Loads the signed-in profile, or `null` when nobody is signed in. */
export type IdentityLoader = () => Promise<UserProfile | null>

let identityLoader: IdentityLoader | null = null

/**
 * Registers the loader the auth feature uses to fetch the profile.
 * Called once at app startup; the shared layer never imports the feature.
 */
export function registerIdentityLoader(loader: IdentityLoader): void {
  identityLoader = loader
}

/** Returns the registered loader, or `null` before registration. */
export function getIdentityLoader(): IdentityLoader | null {
  return identityLoader
}

/** The shape every shared consumer reads. */
export interface AuthIdentity {
  user: UserProfile | null
  isLoading: boolean
}

/**
 * Reads the single cached identity.
 *
 * React Query deduplicates concurrent consumers on the same key, so N mounted
 * components issue at most one profile fetch — identity no longer depends on
 * how many components called this hook.
 */
export function useAuthIdentity(): AuthIdentity {
  const { data, isLoading } = useQuery({
    queryKey: AUTH_IDENTITY_QUERY_KEY,
    queryFn: async (): Promise<UserProfile | null> => {
      const loader = getIdentityLoader()
      if (!loader) return null
      return loader()
    },
  })
  return { user: data ?? null, isLoading }
}
