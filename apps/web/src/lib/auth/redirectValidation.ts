/**
 * Validates a redirect URL to prevent Open Redirect vulnerabilities.
 * Only allows internal paths (relative URLs starting with /).
 *
 * @param url - The URL to validate (typically from query params like ?next=...)
 * @returns The validated URL if safe, otherwise null
 *
 * Security: Rejects:
 * - External URLs (https://evil.com)
 * - Protocol-relative URLs (//evil.com)
 * - JavaScript URLs (javascript:alert(1))
 * - Data URLs (data:text/html,...)
 * - Absolute URLs with protocols
 */
export function validateInternalRedirect(
  url: string | null | undefined
): string | null {
  if (!url) {
    return null;
  }

  // Trim whitespace
  const trimmedUrl = url.trim();

  // Must start with / (internal path)
  if (!trimmedUrl.startsWith("/")) {
    return null;
  }

  // Reject protocol-relative URLs (//evil.com)
  if (trimmedUrl.startsWith("//")) {
    return null;
  }

  // Reject URLs with protocol schemes in the path (before query/hash)
  //
  // Regex breakdown: /^[^?#]*:/
  //   ^        - Start of string
  //   [^?#]*   - Match any characters EXCEPT ? and # (zero or more times)
  //              This matches everything before the query string or hash
  //   :        - Match a literal colon
  //
  // This rejects: /javascript:alert(1), /http://evil.com, /data:text/html
  // But allows:   /chat?time=12:30:00, /admin#section:1
  //               (colons after ? or # are safe)
  if (trimmedUrl.match(/^[^?#]*:/)) {
    return null;
  }

  // Additional safety: check for backslash sequences that could bypass validation
  if (trimmedUrl.includes("\\")) {
    return null;
  }

  // A percent-encoded backslash (%5C / %5c). The caller's own decode
  // (e.g. URLSearchParams.get()) already turns a normally-encoded value
  // into a literal backslash, caught above; a value that still contains
  // "%5c" here has itself been decoded once already and encoded backslash
  // survived that -- i.e. it was double-encoded -- which is exactly the
  // shape a double-decode host-confusion bypass depends on.
  if (/%5c/i.test(trimmedUrl)) {
    return null;
  }

  return trimmedUrl;
}
