/**
 * Shared, typed user-facing error vocabulary.
 *
 * Feature modules express the context of a failed request; this module is the
 * single place those contexts are named. That keeps a code, a surface, and a
 * sentence in one vocabulary instead of every feature inventing its own string.
 */

import { ErrorCode } from '../types/enums'
import type { PartialErrorMessages } from './errorMessages'

/** The single English sentence for an expired session. Never duplicated. */
export const SESSION_EXPIRED_MESSAGE = 'Session expired. Please login again.'

/** The persistent, inline message shown by the main dashboard view. */
export const DASHBOARD_LOAD_FAILED_MESSAGE = 'Failed to load dashboard. Please try again.'

/** The persistent, inline message shown when aggregated chart data fails. */
export const CHART_DATA_LOAD_FAILED_MESSAGE = 'Failed to load chart data.'

/**
 * Maps an error code to the feature that owns its wording.
 *
 * The response interceptor consults this registry once, so a code resolves to a
 * feature message without the interceptor (or the caller) hardcoding a string.
 * Feature modules register their own maps at startup via
 * {@link registerFeatureErrorMessages}; the registry never imports a feature.
 */
type ErrorMessageRegistry = Partial<Record<ErrorCode, string>>

const featureErrorMessages = new Map<string, PartialErrorMessages>()

/**
 * Registers a feature's error-code map under a stable key.
 *
 * Idempotent: re-registering the same key replaces the previous map.
 */
export function registerFeatureErrorMessages(key: string, messages: PartialErrorMessages): void {
  featureErrorMessages.set(key, messages)
}

/**
 * Resolves an error code to its message using every registered feature map.
 *
 * Later registrations win when two features declare the same code. Returns
 * `undefined` when no feature claims the code, letting the caller fall back to
 * the shared vocabulary.
 */
export function getFeatureErrorMessage(code: ErrorCode): string | undefined {
  let resolved: string | undefined
  for (const messages of featureErrorMessages.values()) {
    const message = messages[code]
    if (message !== undefined) {
      resolved = message
    }
  }
  return resolved
}

/**
 * The registry type is exported for tests that want to assert the resolution
 * order without reaching into module state.
 */
export type { ErrorMessageRegistry }
