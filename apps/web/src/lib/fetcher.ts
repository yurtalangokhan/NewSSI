import i18n from "@/i18n/config";

import { ParsedApiError, parseApiErrorResponse } from "@/lib/api/errors";
import {
  attachIdempotencyKey,
  refreshIdempotencyKey,
} from "@/lib/api/idempotency";

export class FetchError extends Error {
  status: number;
  info: any;
  code: string;
  userMessage: string;
  details: Record<string, unknown>;
  fieldErrors: ParsedApiError["fieldErrors"];
  requestId?: string;

  constructor(
    message: string,
    status: number,
    info: any,
    parsedError?: ParsedApiError
  ) {
    super(message);
    this.status = status;
    this.info = info;
    this.code = parsedError?.code ?? "request.invalid";
    this.userMessage = parsedError?.userMessage ?? message;
    this.details = parsedError?.details ?? {};
    this.fieldErrors = parsedError?.fieldErrors ?? [];
    this.requestId = parsedError?.requestId;
    Object.setPrototypeOf(this, FetchError.prototype);
  }
}

export class RedirectError extends FetchError {
  constructor(message: string, status: number, info: any) {
    super(message, status, info);
    Object.setPrototypeOf(this, RedirectError.prototype);
  }
}

function getDefaultAuthErrorMsg(): string {
  return i18n.t("common.fetchAuthError", {
    defaultValue:
      "An error occurred while fetching the data, related to the user's authentication status.",
  });
}

export function getDefaultErrorMsg(): string {
  return i18n.t("common.fetchError", {
    defaultValue: "An error occurred while fetching the data.",
  });
}

interface RefreshTokenResult {
  ok: boolean;
  status: number | null;
}

interface AuthTypeMetadata {
  externalKeycloak?: boolean;
  external_keycloak?: boolean;
}

interface AuthenticatedFetchOptions extends RequestInit {
  redirectOnAuthError?: boolean;
}

let refreshTokenPromise: Promise<RefreshTokenResult> | null = null;
let loginPathPromise: Promise<string> | null = null;
let authRefreshFailedUntil = 0;
const AUTH_REFRESH_FAILED_KEY = "auth_refresh_failed_until";
const AUTH_REFRESH_LOCK_KEY = "auth_refresh_lock";
export const AUTH_SESSION_REFRESHED_EVENT = "auth:session-refreshed";

/**
 * How long a failed refresh suppresses further attempts.
 *
 * This used to be a permanent, session-long flag. A single transient failure
 * - a backend blip, or losing a rotation race with another tab - therefore
 * disabled refresh for the rest of the tab's life, and every later 401 went
 * straight to the login screen. A short cooldown keeps the "don't hammer a
 * dead session" property without making one bad response terminal.
 */
const AUTH_REFRESH_COOLDOWN_MS = 15_000;

/**
 * How long another tab's in-flight refresh is trusted before we assume it
 * died and take the lock ourselves.
 */
const AUTH_REFRESH_LOCK_TTL_MS = 10_000;

function now(): number {
  return Date.now();
}

function readSessionNumber(key: string): number {
  if (typeof window === "undefined") {
    return 0;
  }
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
      // Storage unavailable (private mode, blocked cookies) - the in-memory
      // cooldown still applies for this tab.
    }
  }
}

export function clearAuthRefreshFailed() {
  authRefreshFailedUntil = 0;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(AUTH_REFRESH_FAILED_KEY);
    } catch {
      // Nothing to clear.
    }
  }
}

/**
 * Claim the cross-tab refresh lock.
 *
 * Keycloak rotates refresh tokens, so two tabs refreshing at once means one
 * of them presents a token the other already consumed and gets a 400 - which
 * previously logged that tab out even though the session was fine. Only the
 * lock holder calls the refresh endpoint; the others wait for the shared
 * cookie to be replaced and simply retry their request.
 */
function acquireRefreshLock(): boolean {
  if (typeof window === "undefined") {
    return true;
  }

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
    // Without storage we cannot coordinate; refreshing is still better than
    // not refreshing.
    return true;
  }
}

function releaseRefreshLock() {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(AUTH_REFRESH_LOCK_KEY);
  } catch {
    // Nothing to release.
  }
}

function refreshLockIsHeld(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    const heldSince = Number(
      window.localStorage.getItem(AUTH_REFRESH_LOCK_KEY)
    );
    return Boolean(heldSince) && now() - heldSince < AUTH_REFRESH_LOCK_TTL_MS;
  } catch {
    return false;
  }
}

/** Wait for whichever tab holds the lock to finish its refresh. */
async function waitForRefreshLock(): Promise<void> {
  const deadline = now() + AUTH_REFRESH_LOCK_TTL_MS;
  while (refreshLockIsHeld() && now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

async function performRefresh(): Promise<RefreshTokenResult> {
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    if (res.ok) {
      clearAuthRefreshFailed();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_SESSION_REFRESHED_EVENT));
      }
    } else if (res.status === 400 || res.status === 401) {
      // Only a rejected refresh should start the cooldown; a 5xx or a proxy
      // hiccup must not lock the session out of retrying.
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
): Promise<RefreshTokenResult> {
  if (!options.ignoreCooldown && hasAuthRefreshFailed()) {
    return { ok: false, status: null };
  }

  if (!refreshTokenPromise) {
    refreshTokenPromise = (async () => {
      try {
        if (!acquireRefreshLock()) {
          // Another tab is refreshing the shared cookie right now. Wait it
          // out and let the caller retry rather than racing it into a
          // rotation failure.
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

/**
 * Renew the session ahead of expiry, bypassing the failure cooldown.
 *
 * Used by the app shell's expiry timer, which fires on a schedule rather
 * than in response to a 401 and should not be gated by an earlier failure.
 */
export async function refreshSessionProactively(): Promise<boolean> {
  const result = await tryRefreshToken({ ignoreCooldown: true });
  return result.ok;
}

async function getLoginPath(): Promise<string> {
  if (!loginPathPromise) {
    loginPathPromise = (async () => {
      try {
        const res = await fetch("/api/auth/type", {
          credentials: "include",
          cache: "no-store",
        });

        if (!res.ok) {
          return "/auth/login";
        }

        const authTypeMetadata = (await res.json()) as AuthTypeMetadata;
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
    // jsdom cannot perform full browser navigation during tests.
  }
}

async function redirectToLogin(status: 401 | 403): Promise<never> {
  if (typeof window !== "undefined") {
    navigateTo(await getSessionExpiredRedirectUrl());
  }
  throw new RedirectError(getDefaultAuthErrorMsg(), status, null);
}

async function handleAuthError(status: 401 | 403): Promise<never> {
  if (typeof window !== "undefined") {
    if (status === 401 && window.sessionStorage.getItem("logout_in_progress")) {
      await redirectToLogin(status);
    }

    navigateTo(`/error/${status}`);
  }
  throw new RedirectError(getDefaultAuthErrorMsg(), status, null);
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init?: AuthenticatedFetchOptions
): Promise<Response> {
  const { redirectOnAuthError = true, ...requestInit } = init ?? {};
  let fetchInit = attachIdempotencyKey(input, requestInit);
  const execute = () =>
    fetch(input, {
      credentials: "include",
      ...fetchInit,
    });

  let res = await execute();

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();

    if (refreshed.ok) {
      console.log("[Auth] Token refreshed successfully");
    }

    fetchInit = refreshIdempotencyKey(fetchInit);
    res = await execute();

    if (res.status === 401) {
      console.error(
        refreshed.ok
          ? "[Auth] Unauthorized after token refresh"
          : "[Auth] Session expired, redirecting to login"
      );
      await redirectToLogin(401);
    }

    if (!refreshed.ok && res.ok) {
      // A concurrent refresh can rotate the cookies while this request receives
      // a stale-token failure. A successful retry proves the cookie jar now
      // contains a valid session, so release the refresh-failure cooldown.
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
    return res;
  }

  return res;
}

export const errorHandlingFetcher = async <T>(url: string): Promise<T> => {
  // Send the app's currently selected language (not just the browser's
  // Accept-Language, which reflects OS/browser settings and often doesn't
  // match an explicit in-app language choice) so backend-translated content
  // — e.g. a tool's localized name/description — matches the UI.
  const res = await authenticatedFetch(url, {
    headers: { "X-Language": i18n.language },
  });

  if (!res.ok) {
    const parsedError = await parseApiErrorResponse(res);
    const error = new FetchError(
      parsedError.userMessage,
      res.status,
      parsedError.raw,
      parsedError
    );
    throw error;
  }

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }

  return payload as T;
};

/**
 * SWR-key-aware variant of `errorHandlingFetcher` for hooks whose response
 * is backend-translated (tool/agent names, descriptions, etc.).
 *
 * `errorHandlingFetcher` already sends the current `X-Language` on every
 * call, but a plain string SWR key (`useSWR(url, errorHandlingFetcher)`)
 * doesn't change when the app's language changes, so SWR has no reason to
 * refetch — the UI keeps showing content in the previous language until
 * something else happens to trigger a revalidation. Keying on
 * `[url, language]` instead (this fetcher's expected key shape) makes a
 * language switch look like a key change, which SWR does refetch on.
 */
export const languageKeyedFetcher = async <T>([url]: readonly [
  string,
  string,
]): Promise<T> => errorHandlingFetcher<T>(url);
