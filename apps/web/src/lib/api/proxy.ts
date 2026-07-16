import { NextRequest, NextResponse } from "next/server";
import { INTERNAL_URL, USER_SERVICE_URL } from "@/lib/constants";

const BACKEND_URL = INTERNAL_URL;
const AUTH_COOKIE_NAMES = [
  "fastapiusersauth",
  "session",
  "refresh_token",
  "id_token",
  "access_token",
];

function shouldUseSecureCookies(request: NextRequest): boolean {
  const publicWebOrigin = process.env.WEB_DOMAIN;
  if (publicWebOrigin) {
    try {
      return new URL(publicWebOrigin).protocol === "https:";
    } catch {
      // Fall back to the concrete request URL below.
    }
  }

  return request.nextUrl.protocol === "https:";
}

function clearAuthCookies(request: NextRequest, response: NextResponse) {
  const secure = shouldUseSecureCookies(request);
  AUTH_COOKIE_NAMES.forEach((cookieName) => {
    response.cookies.set(cookieName, "", {
      path: "/",
      maxAge: 0,
      secure,
      httpOnly: true,
      sameSite: "lax",
    });
  });
}

export function getCookieValue(
  cookieHeader: string,
  name: string
): string | null {
  for (const part of cookieHeader.split(/;\s*/)) {
    const [key, ...valueParts] = part.split("=");
    if (key === name) {
      return decodeURIComponent(valueParts.join("="));
    }
  }
  return null;
}

export interface AuthRefreshResult {
  accessToken: string | null;
  cookieHeader: string;
  setCookies: string[];
}

export async function refreshAuthCookies(
  cookieHeader: string
): Promise<AuthRefreshResult | null> {
  if (!getCookieValue(cookieHeader, "refresh_token")) {
    return null;
  }

  const response = await fetch(`${USER_SERVICE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: cookieHeader ? { Cookie: cookieHeader } : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    return null;
  }

  let accessToken: string | null = null;
  try {
    const payload = await response.clone().json();
    accessToken =
      typeof payload?.access_token === "string" ? payload.access_token : null;
  } catch {
    accessToken = null;
  }

  const setCookies = response.headers.getSetCookie();
  let refreshedCookieHeader = cookieHeader;
  for (const cookie of setCookies) {
    const nameValue = cookie.split(";", 1)[0];
    if (!nameValue) {
      continue;
    }
    const [name, ...valueParts] = nameValue.split("=");
    const value = valueParts.join("=");
    if (!name || !value) {
      continue;
    }
    const encoded = `${name}=${value}`;
    const parts = refreshedCookieHeader
      .split(/;\s*/)
      .filter((part) => part && !part.startsWith(`${name}=`));
    parts.push(encoded);
    refreshedCookieHeader = parts.join("; ");
    if (name === "access_token") {
      accessToken = decodeURIComponent(value);
    }
  }

  return {
    accessToken,
    cookieHeader: refreshedCookieHeader,
    setCookies,
  };
}

export interface ProxyOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  withCredentials?: boolean;
  backendUrl?: string;
  refreshOnUnauthorized?: boolean;
}

/**
 * Proxy a request to the backend API
 */
export async function proxyToBackend(
  request: NextRequest,
  pathname: string,
  options: ProxyOptions = {}
): Promise<NextResponse> {
  try {
    const {
      method = request.method,
      withCredentials = true,
      backendUrl = BACKEND_URL,
      refreshOnUnauthorized = true,
    } = options;

    // Build URL with query params
    const url = new URL(`${backendUrl}${pathname}`);
    if (request.nextUrl.search) {
      url.search = request.nextUrl.search;
    }

    const requestCookie = request.headers.get("cookie") || "";
    let body: BodyInit | undefined;
    if (["POST", "PUT", "PATCH"].includes(method)) {
      body = await request.arrayBuffer();
    }

    const buildHeaders = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ): HeadersInit => {
      const headers: HeadersInit = {
        "Content-Type":
          request.headers.get("content-type") || "application/json",
      };

      const authorization = request.headers.get("authorization");
      if (authorization && !accessTokenOverride) {
        headers["Authorization"] = authorization;
      } else {
        const cookieAccessToken =
          accessTokenOverride || getCookieValue(cookieHeader, "access_token");
        if (cookieAccessToken) {
          headers["Authorization"] = `Bearer ${cookieAccessToken}`;
        }
      }

      if (withCredentials) {
        let cookie = cookieHeader;
        if (
          process.env.DEBUG_AUTH_COOKIE &&
          process.env.NODE_ENV === "development" &&
          !cookie.split(/;\s*/).some((c) => c.startsWith("fastapiusersauth="))
        ) {
          const debugCookie = `fastapiusersauth=${process.env.DEBUG_AUTH_COOKIE}`;
          cookie = cookie ? `${cookie}; ${debugCookie}` : debugCookie;
        }
        if (cookie) {
          headers["Cookie"] = cookie;
        }
      }

      return headers;
    };

    const initialRefresh =
      pathname !== "/api/auth/refresh" &&
      !getCookieValue(requestCookie, "access_token") &&
      getCookieValue(requestCookie, "refresh_token")
        ? await refreshAuthCookies(requestCookie)
        : null;
    const initialCookieHeader = initialRefresh?.cookieHeader ?? requestCookie;
    const initialAccessToken = initialRefresh?.accessToken ?? null;

    let response = await fetch(url.toString(), {
      method,
      headers: buildHeaders(initialCookieHeader, initialAccessToken),
      body,
    });

    const refreshed =
      refreshOnUnauthorized && response.status === 401
        ? await refreshAuthCookies(initialCookieHeader)
        : null;
    if (refreshed?.accessToken) {
      response = await fetch(url.toString(), {
        method,
        headers: buildHeaders(refreshed.cookieHeader, refreshed.accessToken),
        body,
      });
    }

    const noContent = new Set([204, 205, 304]).has(response.status);
    const responseText = noContent ? "" : await response.text();
    const result = new NextResponse(noContent ? null : responseText, {
      status: response.status,
      statusText: response.statusText,
    });

    // Copy headers
    response.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "content-encoding") {
        result.headers.set(key, value);
      }
    });

    // Forward set-cookie headers
    response.headers.getSetCookie().forEach((cookie) => {
      result.headers.append("Set-Cookie", cookie);
    });
    initialRefresh?.setCookies.forEach((cookie) => {
      result.headers.append("Set-Cookie", cookie);
    });
    refreshed?.setCookies.forEach((cookie) => {
      result.headers.append("Set-Cookie", cookie);
    });

    if (
      pathname === "/api/auth/refresh" &&
      (response.status === 400 || response.status === 401)
    ) {
      clearAuthCookies(request, result);
    }

    return result;
  } catch (error) {
    console.error(`Proxy error for ${pathname}:`, error);
    return NextResponse.json(
      { error: "Backend service unavailable" },
      { status: 503 }
    );
  }
}
