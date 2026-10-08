import { NextRequest, NextResponse } from "next/server";
import type { BackendService, BackendTarget } from "@/lib/api/http/types";
import {
  backendRequest,
  getCookieValue,
  getLanguageHeaders,
} from "@/lib/api/http/server";
import { getRequestLanguage } from "@/i18n/locales";
import { tServer } from "@/i18n/server";
import { ApiRequestError } from "@/lib/api/errors";
import type { ResponseModel } from "@/lib/api/responseModel";
import { appSettings } from "@/lib/settings";

export { getCookieValue, getLanguageHeaders };

export function deriveBackendAuthHeaders(request: Request): {
  Cookie?: string;
  Authorization?: string;
} {
  const headers: { Cookie?: string; Authorization?: string } = {};
  const cookie = request.headers.get("cookie");
  if (cookie) headers.Cookie = cookie;

  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.Authorization = authorization;
    return headers;
  }

  const accessToken = cookie && getCookieValue(cookie, "access_token");
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

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
const MAX_PROXY_BODY_BYTES = 200 * 1024 * 1024;

function getSetCookieHeaders(headers: Headers): string[] {
  const getSetCookie = (headers as Headers & { getSetCookie?: () => string[] })
    .getSetCookie;
  if (typeof getSetCookie === "function") {
    return getSetCookie.call(headers);
  }

  const single = headers.get("set-cookie");
  return single ? [single] : [];
}

export interface ProxyOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  withCredentials?: boolean;
  backendUrl?: string;
  backendService?: BackendService;
  queryParams?: Record<string, string>;
}

/**
 * Legacy callers pass auth operations as string targets shaped
 * `/auth/api/v1/<operation>`; the canonical user-service endpoint for the same
 * operation is `/api/v1/auth/<operation>`.
 */
const LEGACY_AUTH_PATH = /^\/auth\/api\/v1(\/.*)?$/;

function canonicalAuthTarget(path: string): BackendTarget | undefined {
  const match = LEGACY_AUTH_PATH.exec(path);
  if (!match) return undefined;
  return { service: "user", path: `/api/v1/auth${match[1] ?? ""}` };
}

function proxyErrorResponse(
  request: Request,
  statusCode: number,
  code: string,
  translationKey: string
): NextResponse {
  const locale = getRequestLanguage(request);
  const message = tServer(translationKey, { lng: locale });
  const requestId = request.headers.get("x-request-id");
  const body: ResponseModel<null> = {
    statusCode,
    message,
    data: null,
    error: { code, message, ...(requestId ? { request_id: requestId } : {}) },
  };
  return NextResponse.json(body, {
    status: statusCode,
    headers: { "Content-Language": locale },
  });
}

/**
 * Proxy a request to the backend API
 */
export async function proxyToBackend(
  request: NextRequest,
  target: string | BackendTarget,
  options: ProxyOptions = {}
): Promise<NextResponse> {
  const pathname = typeof target === "string" ? target : target.path;
  try {
    const declaredLength = request.headers.get("content-length");
    if (declaredLength && Number(declaredLength) > MAX_PROXY_BODY_BYTES) {
      return proxyErrorResponse(
        request,
        413,
        "request.payload_too_large",
        "common.apiErrors.payloadTooLarge"
      );
    }

    const method = options.method ?? request.method;
    const withCredentials = options.withCredentials ?? true;
    // Auth traffic always goes through the Gateway so the session cookies are
    // set on the gateway origin, so these paths ignore the per-service URL
    // settings and resolve against GATEWAY_URL.
    const authTarget =
      typeof target === "string" ? canonicalAuthTarget(target) : undefined;
    const backendService =
      authTarget?.service ??
      options.backendService ??
      (typeof target === "string" ? undefined : target.service) ??
      "agent";
    const targetPath = authTarget?.path ?? pathname;
    const targetBaseUrl =
      options.backendUrl ?? (authTarget ? appSettings.GATEWAY_URL : undefined);
    const query = new URLSearchParams(request.nextUrl.searchParams);
    Object.entries(options.queryParams ?? {}).forEach(([key, value]) => {
      query.set(key, value);
    });

    let body: BodyInit | undefined;
    if (["POST", "PUT", "PATCH"].includes(method)) {
      body = request.body ?? undefined;
    }

    const response = await backendRequest({
      service: backendService,
      path: targetPath,
      ...(targetBaseUrl ? { baseUrl: targetBaseUrl } : {}),
      request,
      query,
      method,
      headers: {
        "Content-Type":
          request.headers.get("content-type") || "application/json",
      },
      body,
      duplex: body ? "half" : undefined,
      withCredentials,
      deriveAuthorizationFromCookie: true,
      includeDebugAuthCookie: true,
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

    return result;
  } catch (error) {
    if (
      request.signal.aborted ||
      ((error instanceof Error || error instanceof DOMException) &&
        error.name === "AbortError")
    ) {
      throw error;
    }
    console.error(`Proxy error for ${pathname}:`, error);
    const timedOut =
      (error instanceof ApiRequestError && error.status === 504) ||
      ((error instanceof Error || error instanceof DOMException) &&
        error.name === "TimeoutError");
    return proxyErrorResponse(
      request,
      timedOut ? 504 : 503,
      timedOut ? "dependency.timeout" : "dependency.unavailable",
      timedOut ? "common.apiErrors.timeout" : "common.apiErrors.unavailable"
    );
  }
}
