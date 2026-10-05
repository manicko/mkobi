/**
 * Single accessor for the API base URL.
 *
 * `baseURL` is read from `VITE_API_URL` when set, otherwise it defaults to the
 * same-origin `/api/v1` path that the dev proxy and the production reverse
 * proxy both serve. One accessor keeps the value in exactly one place: the
 * axios instance, the environment validator and any future consumer all agree
 * by construction.
 */
const DEFAULT_API_BASE_URL = '/api/v1'

/** The environment variable that overrides the API base URL. */
export const API_URL_ENV_VAR = 'VITE_API_URL'

/**
 * Resolve the API base URL for this build.
 *
 * Returns the same-origin default when `VITE_API_URL` is unset or empty.
 */
export function getApiBaseUrl(): string {
  // Vite types `import.meta.env` values as `any`; read it as `unknown` first so
  // narrowing happens here rather than leaking an `any` into the return type.
  const configured: unknown = import.meta.env.VITE_API_URL
  if (typeof configured === 'string' && configured.length > 0) {
    return configured
  }
  return DEFAULT_API_BASE_URL
}

/**
 * Validates that `VITE_API_URL` is set in a production build.
 *
 * In development the value is optional because the same-origin default above
 * is served by the Vite proxy. In production the reverse proxy also serves it,
 * but an explicit value is required so a misconfigured deployment fails loudly
 * at startup rather than at the first request.
 */
export function validateEnv(): void {
  if (import.meta.env.DEV) {
    return
  }

  if (!import.meta.env.VITE_API_URL) {
    throw new Error(`Missing required environment variable: ${API_URL_ENV_VAR}`)
  }
}
