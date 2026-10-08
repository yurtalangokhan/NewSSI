/**
 * Guards every internal-service proxy route shares.
 *
 * These proxies forward a browser request to a service that sits behind the
 * gateway, so two things must never travel with it: a client-supplied
 * trusted-context header (the internal services believe those), and a path
 * that escapes the prefix the proxy is scoped to.
 */

/** Headers a client must never be able to set on an internal call. */
const TRUSTED_CONTEXT_HEADER = "x-user-id";
const TRUSTED_CONTEXT_PREFIX = "x-internal-";

export function stripTrustedContextHeaders(headers: Headers): void {
  headers.delete(TRUSTED_CONTEXT_HEADER);
  for (const key of Array.from(headers.keys())) {
    if (key.toLowerCase().startsWith(TRUSTED_CONTEXT_PREFIX)) {
      headers.delete(key);
    }
  }
}

// Matches a traversal segment raw or percent-encoded, in either case, so
// "..", "%2e%2e" and "%2E%2e" are all caught. Encoded forms matter because
// the framework normalises only the decoded path.
const TRAVERSAL = /(^|[/\\])(\.|%2e){2}([/\\]|$)/i;

/**
 * Whether a proxied sub-path is safe to append to the internal base URL.
 *
 * A traversal segment would let a caller climb out of the prefix this proxy
 * is scoped to and reach the gateway's unauthenticated `/internal/*` surface.
 */
export function isSafeProxyPath(path: string): boolean {
  if (TRAVERSAL.test(path)) {
    return false;
  }
  let decoded = path;
  try {
    decoded = decodeURIComponent(path);
  } catch {
    // A malformed escape sequence is not something to forward either.
    return false;
  }
  return !TRAVERSAL.test(decoded);
}
