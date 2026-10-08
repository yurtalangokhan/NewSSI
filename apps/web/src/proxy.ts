import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { refreshSessionForMiddlewareSS } from "@/lib/api/domains/session/server";
import { appSettings } from "@/lib/settings";

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};

/**
 * Generates a per-request CSP with a nonce so script-src no longer needs
 * 'unsafe-inline' (the temporary exception next.config.js carried until
 * this nonce pipeline existed — see Task 38). Every other directive here
 * matches what next.config.js used to set statically.
 */
function buildCsp(): { nonce: string; cspHeader: string } {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = appSettings.NODE_ENV === "development";

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${
      isDev ? " 'unsafe-eval'" : ""
    };
    style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
    img-src 'self' data: blob:;
    font-src 'self' https://fonts.gstatic.com data:;
    connect-src 'self';
    frame-ancestors 'none';
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    ${appSettings.NEXT_PUBLIC_CLOUD_ENABLED ? "upgrade-insecure-requests;" : ""}
  `
    .replace(/\s{2,}/g, " ")
    .trim();

  return { nonce, cspHeader };
}

/**
 * Paths that must never trigger a refresh: they are the way *out* of a
 * session. Refreshing here would resurrect cookies the logout flow is in the
 * middle of clearing, and would send the user in a loop.
 */
const REFRESH_EXEMPT_PREFIXES = ["/auth/logout", "/auth/error", "/error"];

/**
 * Refresh this many seconds before the access token actually expires, so a
 * page render that takes a moment doesn't start with a token that dies
 * mid-flight.
 */
const EXPIRY_SKEW_SECONDS = 30;

function decodeJwtExp(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) {
    return null;
  }

  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "="
    );
    const json = JSON.parse(
      typeof atob === "function"
        ? atob(padded)
        : Buffer.from(padded, "base64").toString("utf-8")
    ) as { exp?: unknown };
    return typeof json.exp === "number" ? json.exp : null;
  } catch {
    return null;
  }
}

function accessTokenIsUsable(accessToken: string | undefined): boolean {
  if (!accessToken) {
    return false;
  }

  const exp = decodeJwtExp(accessToken);
  if (exp === null) {
    // Opaque or unparseable token - assume the backend can still validate it
    // and let a 401 drive the client-side refresh instead.
    return true;
  }

  return exp - EXPIRY_SKEW_SECONDS > Date.now() / 1000;
}

function getSetCookieHeaders(headers: Headers): string[] {
  const getSetCookie = (headers as Headers & { getSetCookie?: () => string[] })
    .getSetCookie;
  if (typeof getSetCookie === "function") {
    return getSetCookie.call(headers);
  }

  const single = headers.get("set-cookie");
  return single ? [single] : [];
}

function readCookieFromSetCookie(
  setCookies: string[],
  name: string
): string | null {
  for (const cookie of setCookies) {
    const [pair] = cookie.split(";");
    if (!pair) {
      continue;
    }
    const separator = pair.indexOf("=");
    if (separator === -1) {
      continue;
    }
    if (pair.slice(0, separator).trim() === name) {
      return pair.slice(separator + 1).trim();
    }
  }
  return null;
}

/**
 * Rebuild the inbound Cookie header with the freshly issued auth cookies, so
 * the server components rendered for *this* request already see the new
 * session instead of re-running the request with the dead one.
 */
function mergeCookieHeader(
  original: string,
  updates: Record<string, string | null>
): string {
  const parts = original
    .split(/;\s*/)
    .filter(Boolean)
    .filter((part) => {
      const name = part.split("=")[0]?.trim();
      // Only drop a cookie we actually have a replacement for - Keycloak
      // omits `id_token` from some refresh responses, and dropping the
      // existing one there would silently break logout.
      return !(name && updates[name]);
    });

  Object.entries(updates).forEach(([name, value]) => {
    if (value) {
      parts.push(`${name}=${value}`);
    }
  });

  return parts.join("; ");
}

function isRefreshCandidate(request: NextRequest): boolean {
  if (request.method !== "GET") {
    return false;
  }

  // Prefetches are speculative; spending the (rotating) refresh token on one
  // is how a real navigation ends up with a token another request already
  // consumed.
  if (request.headers.get("next-router-prefetch") === "1") {
    return false;
  }

  const { pathname } = request.nextUrl;
  if (REFRESH_EXEMPT_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return false;
  }

  if (!request.cookies.has("refresh_token")) {
    return false;
  }

  return !accessTokenIsUsable(request.cookies.get("access_token")?.value);
}

/**
 * Renew the session on server-rendered navigations.
 *
 * Server components cannot set cookies during render, so without this the
 * only place a session was ever renewed was a client-side 401 retry. A plain
 * page reload after the access token expired therefore rendered as logged
 * out and bounced to the login screen even though the refresh token was still
 * perfectly valid - which is exactly what "the session doesn't continue after
 * a timeout" looks like to a user.
 */
export async function proxy(request: NextRequest) {
  const { nonce, cspHeader } = buildCsp();
  // Every branch below needs both the request-side x-nonce (so Server
  // Components can read it via headers() and apply it to app-authored
  // inline scripts) and the response-side CSP that actually enforces it.
  const nextWithCsp = (init?: Parameters<typeof NextResponse.next>[0]) => {
    const requestHeaders = new Headers(
      init?.request?.headers ?? request.headers
    );
    requestHeaders.set("x-nonce", nonce);
    const response = NextResponse.next({
      ...init,
      request: { ...init?.request, headers: requestHeaders },
    });
    response.headers.set("Content-Security-Policy", cspHeader);
    return response;
  };

  if (!isRefreshCandidate(request)) {
    return nextWithCsp();
  }

  const cookieHeader = request.headers.get("cookie") || "";
  let refreshResponse: Response;

  try {
    refreshResponse = await refreshSessionForMiddlewareSS(cookieHeader);
  } catch (error) {
    // The auth backend being unreachable is not a reason to log anyone out;
    // render with what we have and let the client retry.
    console.error("[proxy] auth refresh failed:", error);
    return nextWithCsp();
  }

  if (!refreshResponse.ok) {
    // A concurrent request may already have rotated the shared cookie jar.
    // Only a confirmed logout should emit destructive auth-cookie updates.
    return nextWithCsp();
  }

  const setCookies = getSetCookieHeaders(refreshResponse.headers);
  const refreshedAccessToken = readCookieFromSetCookie(
    setCookies,
    "access_token"
  );

  const response = nextWithCsp({
    request: {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        cookie: mergeCookieHeader(cookieHeader, {
          access_token: refreshedAccessToken,
          refresh_token: readCookieFromSetCookie(setCookies, "refresh_token"),
          id_token: readCookieFromSetCookie(setCookies, "id_token"),
        }),
      }),
    },
  });

  setCookies.forEach((cookie) => {
    response.headers.append("Set-Cookie", cookie);
  });

  return response;
}
