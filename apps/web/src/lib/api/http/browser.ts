import { parseResponseModel } from "@/lib/api/responseModel";
/**
 * Browser HTTP transport - the single request entry point for all browser requests.
 *
 * This module consolidates the previous transport functions (requestJson, requestForm,
 * requestRaw, requestStream) into one `apiRequest` function. All browser requests
 * must use this transport - no direct fetch, no legacy fetcher aliases.
 *
 * Architecture rules (enforced by S15):
 * - No native fetch outside this transport and approved edge exceptions
 * - No legacy fetcher calls from domain code
 * - Mutations automatically receive idempotency keys
 * - GET/HEAD requests never receive mutation idempotency
 */

import { FetchError, RedirectError } from "@/lib/api/http/errors";
import {
  getClientAuthErrorMessage,
  getClientLanguage,
} from "@/i18n/languageState";
import { parseApiErrorResponse } from "@/lib/api/errors";
import {
  attachIdempotencyKey,
  isIdempotencyExcludedPath,
  refreshIdempotencyKey,
} from "@/lib/api/idempotency";
import type { ApiRequestOptions } from "@/lib/api/http/types";
import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";

// ============================================================================
// Constants (duplicated from idempotency.ts to avoid circular dependency)
// ============================================================================

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// ============================================================================
// Session refresh logic (copied from fetcher.ts to avoid circular dependency)
// ============================================================================

let refreshTokenPromise: Promise<{
  ok: boolean;
  status: number | null;
}> | null = null;
let loginPathPromise: Promise<string> | null = null;
let authRefreshFailedUntil = 0;
const AUTH_REFRESH_COOLDOWN_MS = 15_000;
const AUTH_REFRESH_FAILED_KEY = "auth_refresh_failed_until";
const AUTH_REFRESH_LOCK_KEY = "auth_refresh_lock";
const AUTH_REFRESH_LOCK_TTL_MS = 10_000;
export const AUTH_SESSION_REFRESHED_EVENT = "auth:session-refreshed";

function now(): number {
  return Date.now();
}

function readSessionNumber(key: string): number {
  if (typeof window === "undefined") return 0;
  try {
    return Number(window.sessionStorage.getItem(key)) || 0;
  } catch {
    return 0;
  }
}

function hasAuthRefreshFailed(): boolean {
  if (typeof window === "undefined") {
    return authRefreshFailedUntil > now();
  }
  authRefreshFailedUntil = readSessionNumber(AUTH_REFRESH_FAILED_KEY);
  return authRefreshFailedUntil > now();
}

function markAuthRefreshFailed() {
  authRefreshFailedUntil = now() + AUTH_REFRESH_COOLDOWN_MS;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(
        AUTH_REFRESH_FAILED_KEY,
        String(authRefreshFailedUntil)
      );
    } catch {
      // Storage unavailable
    }
  }
}

export function clearAuthRefreshFailed() {
  authRefreshFailedUntil = 0;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(AUTH_REFRESH_FAILED_KEY);
    } catch {
      // Storage unavailable.
    }
  }
}

function acquireRefreshLock(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const heldSince = Number(
      window.localStorage.getItem(AUTH_REFRESH_LOCK_KEY)
    );
    if (heldSince && now() - heldSince < AUTH_REFRESH_LOCK_TTL_MS) {
      return false;
    }
    window.localStorage.setItem(AUTH_REFRESH_LOCK_KEY, String(now()));
    return true;
  } catch {
    return true;
  }
}

function releaseRefreshLock() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(AUTH_REFRESH_LOCK_KEY);
  } catch {
    // Nothing to release
  }
}

function refreshLockIsHeld(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const heldSince = Number(
      window.localStorage.getItem(AUTH_REFRESH_LOCK_KEY)
    );
    return Boolean(heldSince) && now() - heldSince < AUTH_REFRESH_LOCK_TTL_MS;
  } catch {
    return false;
  }
}

async function waitForRefreshLock(): Promise<void> {
  const deadline = now() + AUTH_REFRESH_LOCK_TTL_MS;
  while (refreshLockIsHeld() && now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

async function performRefresh(): Promise<{
  ok: boolean;
  status: number | null;
}> {
  try {
    const res = await fetch(sessionEndpoints.refresh.browserPath, {
      method: "POST",
      credentials: "include",
    });
    if (res.ok) {
      await parseResponseModel<unknown>(res);
      clearAuthRefreshFailed();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_SESSION_REFRESHED_EVENT));
      }
    } else if (res.status === 400 || res.status === 401) {
      markAuthRefreshFailed();
    }
    return { ok: res.ok, status: res.status };
  } catch {
    markAuthRefreshFailed();
    return { ok: false, status: null };
  } finally {
    releaseRefreshLock();
  }
}

async function tryRefreshToken(
  options: { ignoreCooldown?: boolean } = {}
): Promise<{ ok: boolean; status: number | null }> {
  if (!options.ignoreCooldown && hasAuthRefreshFailed()) {
    return { ok: false, status: null };
  }

  if (!refreshTokenPromise) {
    refreshTokenPromise = (async () => {
      try {
        if (!acquireRefreshLock()) {
          await waitForRefreshLock();
          clearAuthRefreshFailed();
          return { ok: true, status: null };
        }
        return await performRefresh();
      } finally {
        refreshTokenPromise = null;
      }
    })();
  }

  return await refreshTokenPromise;
}

export async function refreshSessionProactively(): Promise<boolean> {
  const result = await tryRefreshToken({ ignoreCooldown: true });
  return result.ok;
}

async function getLoginPath(): Promise<string> {
  if (!loginPathPromise) {
    loginPathPromise = (async () => {
      try {
        const res = await fetch(sessionEndpoints.authType.browserPath, {
          credentials: "include",
          cache: "no-store",
        });

        if (!res.ok) return "/auth/login";

        const authTypeMetadata = await parseResponseModel<{
          externalKeycloak?: boolean;
          external_keycloak?: boolean;
        }>(res);
        return authTypeMetadata.externalKeycloak ||
          authTypeMetadata.external_keycloak
          ? "/auth/ee/login"
          : "/auth/login";
      } catch {
        return "/auth/login";
      } finally {
        loginPathPromise = null;
      }
    })();
  }
  return await loginPathPromise;
}

export async function getLoginRedirectUrl(): Promise<string> {
  const loginPath = await getLoginPath();

  if (typeof window === "undefined") {
    return loginPath;
  }

  const nextUrl = `${window.location.pathname}${window.location.search}`;
  return window.location.pathname === loginPath
    ? nextUrl
    : `${loginPath}?next=${encodeURIComponent(nextUrl)}`;
}

export async function getSessionExpiredRedirectUrl(): Promise<string> {
  const loginRedirectUrl = await getLoginRedirectUrl();

  if (typeof window === "undefined") {
    return loginRedirectUrl;
  }

  const targetUrl = new URL(loginRedirectUrl, window.location.origin);
  if (
    window.location.pathname === targetUrl.pathname &&
    window.location.search === targetUrl.search
  ) {
    return loginRedirectUrl;
  }

  return `/auth/logout?next=${encodeURIComponent(loginRedirectUrl)}`;
}

function navigateTo(url: string) {
  if (typeof window === "undefined") return;
  const targetUrl = new URL(url, window.location.origin);
  if (
    window.location.pathname === targetUrl.pathname &&
    window.location.search === targetUrl.search
  ) {
    return;
  }
  try {
    window.location.href = targetUrl.toString();
  } catch {
    // jsdom cannot navigate during tests
  }
}

async function redirectToLogin(status: 401 | 403): Promise<never> {
  if (typeof window !== "undefined") {
    navigateTo(await getSessionExpiredRedirectUrl());
  }
  throw new RedirectError(getClientAuthErrorMessage(), status, null);
}

async function handleAuthError(status: 401 | 403): Promise<never> {
  if (typeof window !== "undefined") {
    if (status === 401 && window.sessionStorage.getItem("logout_in_progress")) {
      await redirectToLogin(status);
    }
    navigateTo(`/error/${status}`);
  }
  throw new RedirectError(getClientAuthErrorMessage(), status, null);
}

// ============================================================================
// Idempotency helpers
// ============================================================================

function addLanguageHeader(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers);
  headers.set("X-Language", getClientLanguage());
  return { ...init, headers };
}

function shouldAddIdempotencyKey(method: string, path: string): boolean {
  if (!MUTATING_METHODS.has(method.toUpperCase())) {
    return false;
  }
  if (isIdempotencyExcludedPath(path)) {
    return false;
  }
  return true;
}

function attachMutationIdempotency(
  input: RequestInfo | URL,
  init: RequestInit
): RequestInit {
  const method = (init.method ?? "GET").toUpperCase();
  if (!shouldAddIdempotencyKey(method, getPath(input))) {
    return init;
  }
  return attachIdempotencyKey(input, init);
}

function getPath(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    try {
      return new URL(input, "http://localhost").pathname;
    } catch {
      return input;
    }
  }
  if (input instanceof URL) {
    return input.pathname;
  }
  return input.url;
}

// ============================================================================
// Core apiRequest function
// ============================================================================

/**
 * The single browser request function for all domain API calls.
 *
 * @param input - RequestInfo (URL string or Request object)
 * @param options - Request options including auth policy.
 * @returns The raw Response; domain APIs own response parsing.
 *
 * Features:
 * - Session refresh on 401 with lock coordination across tabs
 * - Automatic idempotency keys for POST/PUT/PATCH/DELETE
 * - Language header for i18n
 * - Credentials for session auth
 * - Response parsing (JSON, raw, stream)
 */
export async function apiRequest(
  input: RequestInfo | URL,
  options: ApiRequestOptions = {}
): Promise<Response> {
  const { auth = "session", redirectOnAuthError = true, ...init } = options;

  // Add language header
  let preparedInit = addLanguageHeader(init);

  // Public and refresh requests skip session recovery but keep common request
  // policy, including mutation idempotency where the endpoint is eligible.
  if (auth === "public" || auth === "refresh") {
    const res = await fetch(input, {
      credentials: "include",
      ...attachMutationIdempotency(input, preparedInit),
    });
    return res;
  }

  // Session auth - use authenticated fetch with retry and idempotency
  let fetchInit = attachMutationIdempotency(input, preparedInit);

  const executeFetch = () =>
    fetch(input, {
      credentials: "include",
      ...fetchInit,
    });

  let res = await executeFetch();

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (refreshed.ok) {
      console.log("[Auth] Token refreshed successfully");
    } else if (!redirectOnAuthError) {
      return res;
    }

    // Retry even after a rejected refresh: another tab may have rotated the
    // shared cookie while this request was in flight.
    fetchInit = refreshIdempotencyKey(fetchInit);
    res = await executeFetch();

    if (res.status === 401) {
      console.error(
        refreshed.ok
          ? "[Auth] Unauthorized after token refresh"
          : "[Auth] Session expired, redirecting to login"
      );
      await redirectToLogin(401);
    }

    if (!refreshed.ok && res.ok) {
      clearAuthRefreshFailed();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_SESSION_REFRESHED_EVENT));
      }
    }
  }

  if (res.status === 403) {
    if (redirectOnAuthError) {
      console.error("[Auth] Access forbidden (403), redirecting to error page");
      await handleAuthError(403);
    }
  }

  return res;
}

/**
 * Parse a JSON response, handling 204 No Content.
 */
export async function parseJsonResponse<T>(
  res: Response
): Promise<T | undefined> {
  if (res.status === 204) {
    return undefined;
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    // Some endpoints return 200 with text/plain or no content type
    // Try to parse anyway
    const text = await res.text();
    if (text) {
      try {
        return JSON.parse(text) as T;
      } catch {
        // Not JSON
      }
    }
    return undefined;
  }

  return res.json() as Promise<T>;
}

/**
 * Parse an error response into FetchError.
 */
export async function parseErrorResponse(
  res: Response,
  url?: string
): Promise<FetchError> {
  const parsedError = await parseApiErrorResponse(res);
  return new FetchError(
    parsedError.userMessage ?? "An error occurred",
    res.status,
    parsedError.raw,
    parsedError
  );
}

// ============================================================================
// Re-exports for convenience
// ============================================================================

export { FetchError, RedirectError } from "@/lib/api/http/errors";
export type { ApiRequestOptions, ResponseMode, AuthPolicy } from "./types";
