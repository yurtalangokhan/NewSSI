import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const USER_SERVICE_URL =
  process.env.USER_SERVICE_URL || "http://localhost:8090";
const REFRESH_TOKEN_EXPIRY_BUFFER_SECONDS = 30;

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};

function decodeJwtPayload(token: string): { exp?: number } | null {
  const [, payload] = token.split(".");
  if (!payload) {
    return null;
  }

  try {
    const normalizedPayload = payload
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(payload.length / 4) * 4, "=");
    return JSON.parse(atob(normalizedPayload)) as { exp?: number };
  } catch {
    return null;
  }
}

function shouldRefreshAccessToken(accessToken: string | undefined): boolean {
  if (!accessToken) {
    return true;
  }

  const payload = decodeJwtPayload(accessToken);
  if (!payload?.exp) {
    return true;
  }

  const expiresAt = payload.exp * 1000;
  const refreshBefore = REFRESH_TOKEN_EXPIRY_BUFFER_SECONDS * 1000;
  return Date.now() + refreshBefore >= expiresAt;
}

function getSetCookieHeaders(response: Response): string[] {
  const getSetCookie = (
    response.headers as Headers & {
      getSetCookie?: () => string[];
    }
  ).getSetCookie;

  if (getSetCookie) {
    return getSetCookie.call(response.headers);
  }

  const setCookie = response.headers.get("set-cookie");
  return setCookie ? [setCookie] : [];
}

function applySetCookieToRequestHeaders(
  requestHeaders: Headers,
  setCookieHeaders: string[]
) {
  const cookiePairs = new Map<string, string>();
  const currentCookieHeader = requestHeaders.get("cookie") || "";

  currentCookieHeader
    .split(/;\s*/)
    .filter(Boolean)
    .forEach((cookie) => {
      const separatorIndex = cookie.indexOf("=");
      if (separatorIndex === -1) {
        return;
      }
      cookiePairs.set(
        cookie.slice(0, separatorIndex),
        cookie.slice(separatorIndex + 1)
      );
    });

  setCookieHeaders.forEach((setCookie) => {
    const [cookiePair] = setCookie.split(";");
    if (!cookiePair) {
      return;
    }

    const separatorIndex = cookiePair.indexOf("=");
    if (separatorIndex === -1) {
      return;
    }

    const name = cookiePair.slice(0, separatorIndex);
    const value = cookiePair.slice(separatorIndex + 1);
    if (value) {
      cookiePairs.set(name, value);
    } else {
      cookiePairs.delete(name);
    }
  });

  requestHeaders.set(
    "cookie",
    Array.from(cookiePairs.entries())
      .map(([name, value]) => `${name}=${value}`)
      .join("; ")
  );
}

async function refreshAuthCookies(request: NextRequest) {
  const refreshToken = request.cookies.get("refresh_token")?.value;
  const accessToken = request.cookies.get("access_token")?.value;

  if (!refreshToken || !shouldRefreshAccessToken(accessToken)) {
    return null;
  }

  const response = await fetch(`${USER_SERVICE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: request.headers.get("cookie") || "",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    return null;
  }

  return getSetCookieHeaders(response);
}

export async function proxy(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  const refreshedCookies = await refreshAuthCookies(request);

  if (refreshedCookies?.length) {
    applySetCookieToRequestHeaders(requestHeaders, refreshedCookies);
  }

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  refreshedCookies?.forEach((cookie) => {
    response.headers.append("set-cookie", cookie);
  });

  return response;
}
