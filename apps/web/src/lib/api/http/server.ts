/**
 * Server HTTP transport - the single request entry point for all server-side backend requests.
 *
 * This module consolidates the previous server transport functions into one
 * `backendRequest` function. All Next.js route handlers must use this transport
 * to call backend services.
 *
 * Architecture rules (enforced by S15):
 * - All backend origin resolution through the validated app settings
 * - Configured service base URL joined with the explicit domain endpoint
 * - Authorization, cookies, language, request ID, and idempotency forwarded
 * - No direct fetch calls from route handlers
 */

import {
  attachIdempotencyKey,
  getIncomingIdempotencyHeaders,
  isIdempotencyExcludedPath,
} from "@/lib/api/idempotency";
import type {
  BackendRequestOptions,
  BackendService,
  BackendTarget,
} from "@/lib/api/http/types";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { appSettings } from "@/lib/settings";

// ============================================================================
// Constants
// ============================================================================

const REQUEST_ID_HEADER = "X-Request-Id";
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// ============================================================================
// Helper functions
// ============================================================================

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

/**
 * Forward authorization and cookie headers from the incoming request.
 */
function forwardAuthHeaders(
  request: Request,
  headers: Headers,
  targetUrl: URL,
  withCredentials: boolean,
  deriveAuthorizationFromCookie: boolean,
  includeDebugAuthCookie: boolean
): void {
  const isRefreshRequest = targetUrl.pathname.endsWith("/auth/refresh");
  const authorization = request.headers.get("authorization");
  const requestCookie = request.headers.get("cookie") ?? "";
  if (authorization && !isRefreshRequest) {
    headers.set("Authorization", authorization);
  } else if (deriveAuthorizationFromCookie && !isRefreshRequest) {
    const accessToken = getCookieValue(requestCookie, "access_token");
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }
  }

  if (withCredentials) {
    let cookie = requestCookie;
    if (
      includeDebugAuthCookie &&
      appSettings.DEBUG_AUTH_COOKIE &&
      appSettings.NODE_ENV === "development" &&
      !cookie.split(/;\s*/).some((part) => part.startsWith("fastapiusersauth="))
    ) {
      const debugCookie = `fastapiusersauth=${appSettings.DEBUG_AUTH_COOKIE}`;
      cookie = cookie ? `${cookie}; ${debugCookie}` : debugCookie;
    }
    if (cookie) {
      headers.set("Cookie", cookie);
    }
  }
}

/**
 * Forward language headers from the incoming request.
 */
export function getLanguageHeaders(request: Request): Record<string, string> {
  const language = request.headers.get("x-language");
  if (language) {
    return { "X-Language": language };
  }
  const acceptedLanguage = request.headers.get("accept-language");
  return acceptedLanguage ? { "Accept-Language": acceptedLanguage } : {};
}

/**
 * Build the server request init by forwarding all necessary headers.
 */
function buildBackendRequestInit(
  request: Request,
  options: RequestInit,
  targetUrl: URL,
  withCredentials: boolean,
  forwardContentType: boolean,
  deriveAuthorizationFromCookie: boolean,
  includeDebugAuthCookie: boolean
): RequestInit {
  const headers = new Headers(options.headers);

  // Forward language
  Object.entries(getLanguageHeaders(request)).forEach(([key, value]) => {
    if (!headers.has(key)) headers.set(key, value);
  });

  // Forward idempotency
  const method = (options.method ?? request.method).toUpperCase();
  if (
    MUTATING_METHODS.has(method) &&
    !isIdempotencyExcludedPath(targetUrl.pathname)
  ) {
    Object.entries(getIncomingIdempotencyHeaders(request)).forEach(
      ([key, value]) => {
        if (!headers.has(key)) headers.set(key, value);
      }
    );
  }

  // Forward auth
  forwardAuthHeaders(
    request,
    headers,
    targetUrl,
    withCredentials,
    deriveAuthorizationFromCookie,
    includeDebugAuthCookie
  );

  // Forward request ID
  const requestId = request.headers.get(REQUEST_ID_HEADER.toLowerCase());
  if (requestId) {
    headers.set(REQUEST_ID_HEADER, requestId);
  }

  for (const headerName of [
    "accept",
    "origin",
    ...(forwardContentType ? ["content-type"] : []),
  ]) {
    const value = request.headers.get(headerName);
    if (value && !headers.has(headerName)) {
      headers.set(headerName, value);
    }
  }

  return { ...options, headers };
}

/**
 * Build a backend URL with query parameters.
 */
export function resolveBackendUrl(
  { service, path, baseUrl }: BackendTarget & { baseUrl?: string },
  query?: Record<string, string> | URLSearchParams
): URL {
  const base = baseUrl ?? getServiceBaseUrl(service);
  const url = buildServiceUrl(base, service, path);
  if (query instanceof URLSearchParams) {
    query.forEach((value, key) => url.searchParams.append(key, value));
  } else {
    Object.entries(query ?? {}).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
  }
  return url;
}

function getServiceBaseUrl(service: BackendService): string {
  switch (service) {
    case "agent":
      return appSettings.AGENT_SERVICE_URL;
    case "rag":
      return appSettings.RAG_SERVICE_URL;
    case "tools":
      return appSettings.TOOLS_SERVICE_URL;
    case "user":
      return appSettings.USER_SERVICE_URL;
  }
}

// ============================================================================
// Main backendRequest function
// ============================================================================

/**
 * The single server-side request function for calling backend services.
 *
 * @param options - BackendRequestOptions including service, path, and request
 * @returns The raw backend Response. Routes own response adaptation.
 *
 * Features:
 * - Centralized environment lookup through validated app settings
 * - Gateway-scoped service URL + explicit domain endpoint joining
 * - Header forwarding (auth, cookies, language, idempotency, request ID)
 * - Query parameter handling
 */
export async function backendRequest(
  options: BackendRequestOptions
): Promise<Response> {
  const {
    service,
    path,
    baseUrl,
    url: resolvedUrl,
    request,
    query,
    withCredentials = true,
    forwardContentType = true,
    deriveAuthorizationFromCookie = false,
    includeDebugAuthCookie = false,
    ...init
  } = options;

  const url = resolvedUrl
    ? new URL(resolvedUrl)
    : resolveBackendUrl({ baseUrl, service: service!, path: path! }, query);

  if (resolvedUrl) {
    if (query instanceof URLSearchParams) {
      query.forEach((value, key) => url.searchParams.append(key, value));
    } else {
      Object.entries(query ?? {}).forEach(([key, value]) => {
        url.searchParams.set(key, value);
      });
    }
  }

  const forwardedInit = request
    ? buildBackendRequestInit(
        request,
        init,
        url,
        withCredentials,
        forwardContentType,
        deriveAuthorizationFromCookie,
        includeDebugAuthCookie
      )
    : init;

  return fetch(url.toString(), attachIdempotencyKey(url, forwardedInit));
}

export type { BackendService, BackendRequestOptions } from "./types";
