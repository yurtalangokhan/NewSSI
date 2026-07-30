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

const DEFAULT_AUTH_ERROR_MSG =
  "An error occurred while fetching the data, related to the user's authentication status.";

const DEFAULT_ERROR_MSG = "An error occurred while fetching the data.";

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
  throw new RedirectError(DEFAULT_AUTH_ERROR_MSG, status, null);
}

async function handleAuthError(status: 401 | 403): Promise<never> {
  if (typeof window !== "undefined") {
    if (status === 401 && window.sessionStorage.getItem("logout_in_progress")) {
      await redirectToLogin(status);
    }

    navigateTo(`/error/${status}`);
  }
  throw new RedirectError(DEFAULT_AUTH_ERROR_MSG, status, null);
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
  const res = await authenticatedFetch(url);

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }

  if (!res.ok) {
    const error = new FetchError(DEFAULT_ERROR_MSG, res.status, payload);
    throw error;
  }

  return payload as T;
};
