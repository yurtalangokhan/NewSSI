/**
 * Copy every Set-Cookie from a backend response onto an outgoing one.
 *
 * `Headers.get("set-cookie")` folds a multi-valued Set-Cookie into a single
 * comma-joined string, and writing that back produces one malformed cookie —
 * so a backend issuing session + refresh cookies ended up with the browser
 * storing neither and the user silently failing to sign in. `getSetCookie()`
 * is the accessor that preserves them individually.
 */
export function forwardSetCookies(from: Headers, to: Headers): void {
  for (const cookie of from.getSetCookie()) {
    to.append("set-cookie", cookie);
  }
}
