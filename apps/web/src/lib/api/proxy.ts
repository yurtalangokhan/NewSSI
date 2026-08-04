import { NextRequest, NextResponse } from "next/server";
import { INTERNAL_URL, USER_SERVICE_URL } from "@/lib/constants";
import { BackendService, buildServiceUrl } from "@/lib/api/gatewayRouting";

const BACKEND_URL = INTERNAL_URL;
const AUTH_COOKIE_NAMES = [
  "fastapiusersauth",
  "session",
  "refresh_token",
  "id_token",
  "access_token",
];
const EXCLUDED_PROXY_RESPONSE_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "set-cookie",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function getSetCookieHeaders(headers: Headers): string[] {
  const getSetCookie = (
    headers as Headers & { getSetCookie?: () => string[] }
  ).getSetCookie;
  if (typeof getSetCookie === "function") {
    return getSetCookie.call(headers);
  }

  const single = headers.get("set-cookie");
  return single ? [single] : [];
}

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

export interface ProxyOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  withCredentials?: boolean;
  backendUrl?: string;
  backendService?: BackendService;
  queryParams?: Record<string, string>;
}

function inferBackendService(backendUrl: string): BackendService {
  try {
    const parsed = new URL(backendUrl);
    if (
      backendUrl === USER_SERVICE_URL ||
      parsed.hostname.includes("user-service") ||
      parsed.pathname.startsWith("/user-service")
    ) {
      return "user";
    }
  } catch {
    if (backendUrl === USER_SERVICE_URL) {
      return "user";
    }
  }

  return "agent";
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
      backendService = inferBackendService(backendUrl),
      queryParams,
    } = options;

    // Build URL with query params
    const url = buildServiceUrl(backendUrl, backendService, pathname);
    if (request.nextUrl.search) {
      url.search = request.nextUrl.search;
    }
    Object.entries(queryParams ?? {}).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });

    const requestCookie = request.headers.get("cookie") || "";
    const isAuthRefreshRequest =
      pathname === "/api/auth/refresh" || pathname === "/api/v1/auth/refresh";
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
      if (authorization && !accessTokenOverride && !isAuthRefreshRequest) {
        headers["Authorization"] = authorization;
      } else {
        const cookieAccessToken =
          accessTokenOverride ||
          (isAuthRefreshRequest
            ? null
            : getCookieValue(cookieHeader, "access_token"));
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

    const response = await fetch(url.toString(), {
      method,
      headers: buildHeaders(requestCookie),
      body,
    });

    const noContent = new Set([204, 205, 304]).has(response.status);
    const responseHeaders = new Headers();

    response.headers.forEach((value, key) => {
      if (!EXCLUDED_PROXY_RESPONSE_HEADERS.has(key.toLowerCase())) {
        responseHeaders.set(key, value);
      }
    });

    const result = new NextResponse(noContent ? null : response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });

    getSetCookieHeaders(response.headers).forEach((cookie) => {
      result.headers.append("Set-Cookie", cookie);
    });

    if (
      isAuthRefreshRequest &&
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
