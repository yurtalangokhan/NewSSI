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

let refreshTokenPromise: Promise<RefreshTokenResult> | null = null;

async function tryRefreshToken(): Promise<RefreshTokenResult> {
  if (!refreshTokenPromise) {
    refreshTokenPromise = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST",
          credentials: "include",
        });
        return { ok: res.ok, status: res.status };
      } catch {
        return { ok: false, status: null };
      } finally {
        refreshTokenPromise = null;
      }
    })();
  }

  return await refreshTokenPromise;
}

export function getLoginRedirectUrl(): string {
  if (typeof window === "undefined") {
    return "/auth/login";
  }

  const nextUrl = `${window.location.pathname}${window.location.search}`;
  return nextUrl === "/auth/login"
    ? "/auth/login"
    : `/auth/login?next=${encodeURIComponent(nextUrl)}`;
}

function navigateTo(url: string) {
  try {
    window.location.href = url;
  } catch {
    // jsdom cannot perform full browser navigation during tests.
  }
}

function redirectToLogin(status: 401 | 403): never {
  if (typeof window !== "undefined") {
    navigateTo(getLoginRedirectUrl());
  }
  throw new RedirectError(DEFAULT_AUTH_ERROR_MSG, status, null);
}

function handleAuthError(status: 401 | 403): never {
  if (typeof window !== "undefined") {
    if (status === 401 && window.sessionStorage.getItem("logout_in_progress")) {
      redirectToLogin(status);
    }

    navigateTo(`/error/${status}`);
  }
  throw new RedirectError(DEFAULT_AUTH_ERROR_MSG, status, null);
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const execute = () =>
    fetch(input, {
      credentials: "include",
      ...init,
    });

  let res = await execute();

  if (res.status === 401) {
    const refreshed = await tryRefreshToken();
    if (!refreshed.ok) {
      if (refreshed.status === 401) {
        console.error("[Auth] Session expired, redirecting to login");
        redirectToLogin(401);
      }

      console.error(
        "[Auth] No refresh token available, redirecting to error page"
      );
      handleAuthError(401);
    }

    console.log("[Auth] Token refreshed successfully");
    res = await execute();

    if (res.status === 401) {
      console.error("[Auth] Unauthorized after token refresh");
      handleAuthError(401);
    }
  }

  if (res.status === 403) {
    console.error("[Auth] Access forbidden (403), redirecting to error page");
    handleAuthError(403);
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
