import i18n from "@/i18n/config";

export class FetchError extends Error {
  status: number;
  info: any;
  constructor(message: string, status: number, info: any) {
    super(message);
    this.status = status;
    this.info = info;
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
let authRefreshFailed = false;
const AUTH_REFRESH_FAILED_KEY = "auth_refresh_failed";
export const AUTH_SESSION_REFRESHED_EVENT = "auth:session-refreshed";

function hasAuthRefreshFailed(): boolean {
  if (typeof window === "undefined") {
    return authRefreshFailed;
  }

  authRefreshFailed =
    window.sessionStorage.getItem(AUTH_REFRESH_FAILED_KEY) === "true";
  return authRefreshFailed;
}

function markAuthRefreshFailed() {
  authRefreshFailed = true;
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(AUTH_REFRESH_FAILED_KEY, "true");
  }
}

export function clearAuthRefreshFailed() {
  authRefreshFailed = false;
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem(AUTH_REFRESH_FAILED_KEY);
  }
}

async function tryRefreshToken(): Promise<RefreshTokenResult> {
  if (hasAuthRefreshFailed()) {
    return { ok: false, status: null };
  }

  if (!refreshTokenPromise) {
    refreshTokenPromise = (async () => {
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
        } else {
          markAuthRefreshFailed();
        }
        return { ok: res.ok, status: res.status };
      } catch {
        markAuthRefreshFailed();
        return { ok: false, status: null };
      } finally {
        refreshTokenPromise = null;
      }
    })();
  }

  return await refreshTokenPromise;
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
  const { redirectOnAuthError = true, ...fetchInit } = init ?? {};
  const execute = () =>
    fetch(input, {
      credentials: "include",
      ...fetchInit,
    });

  let res = await execute();

  if (!redirectOnAuthError && (res.status === 401 || res.status === 403)) {
    return res;
  }

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (!refreshed.ok) {
      console.error("[Auth] Session expired, redirecting to login");
      await redirectToLogin(401);
    }

    console.log("[Auth] Token refreshed successfully");
    res = await execute();

    if (res.status === 401) {
      console.error("[Auth] Unauthorized after token refresh");
      await redirectToLogin(401);
    }
  }

  if (res.status === 403) {
    console.error("[Auth] Access forbidden (403), redirecting to error page");
    await handleAuthError(403);
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

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }

  if (!res.ok) {
    const error = new FetchError(getDefaultErrorMsg(), res.status, payload);
    throw error;
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
export const languageKeyedFetcher = async <T>(
  [url]: readonly [string, string]
): Promise<T> => errorHandlingFetcher<T>(url);
