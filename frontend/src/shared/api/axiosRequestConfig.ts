/**
 * Per-request axios configuration extensions.
 *
 * The response interceptor owns a single error-surface policy (one surface per
 * context). It cannot see which UI surface displayed a request, so the opt-out
 * must be carried on the request itself — the caller knows the context.
 */

declare module 'axios' {
  export interface AxiosRequestConfig {
    /**
     * When true, the response interceptor never raises a toast for this request.
     * The caller is responsible for surfacing the failure on its own surface —
     * a persistent inline message for a main view, for example.
     *
     * It is deliberately per-request and not per-error-class: the interceptor
     * cannot infer the displaying surface from the error shape alone.
     */
    skipErrorToast?: boolean
  }
}

export {}
