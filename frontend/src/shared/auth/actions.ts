/**
 * Shared-side auth action accessor.
 *
 * Mirrors `identity.ts`: the auth feature registers a logout implementation
 * once at startup, and `shared/` consumers invoke it without importing the
 * feature. The arrow stays shared ← features.
 */

/** Signs the current user out and clears the cached identity. */
export type LogoutHandler = () => Promise<void>

let logoutHandler: LogoutHandler | null = null

/** Registers the logout implementation the auth feature provides. */
export function registerLogoutHandler(handler: LogoutHandler): void {
  logoutHandler = handler
}

/** Returns the registered logout handler, or `null` before registration. */
export function getLogoutHandler(): LogoutHandler | null {
  return logoutHandler
}

/** Invokes the registered logout handler; a no-op before registration. */
export async function logout(): Promise<void> {
  const handler = getLogoutHandler()
  if (handler) {
    await handler()
  }
}
