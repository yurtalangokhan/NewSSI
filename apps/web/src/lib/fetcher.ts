export class FetchError extends Error {
  status: number;
  info: any;
  constructor(message: string, status: number, info: any) {
    super(message);
    this.status = status;
    this.info = info;
  }
}

export class RedirectError extends FetchError {
  constructor(message: string, status: number, info: any) {
    super(message, status, info);
  }
}

const DEFAULT_AUTH_ERROR_MSG =
  "An error occurred while fetching the data, related to the user's authentication status.";

const DEFAULT_ERROR_MSG = "An error occurred while fetching the data.";

async function tryRefreshToken(): Promise<boolean> {
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}

function handleAuthError(status: 401 | 403): never {
  if (typeof window !== "undefined") {
    window.location.href = "/auth/login";
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
    if (refreshed) {
      console.log("[Auth] Token refreshed successfully");
      res = await execute();
    }

    // If still 401 after refresh attempt, redirect to login
    if (res.status === 401) {
      console.error("[Auth] Refresh token expired, redirecting to login");
      handleAuthError(401);
    }
  }

  if (res.status === 403) {
    console.error("[Auth] Access forbidden (403), redirecting to login");
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
    const error = new FetchError(
      DEFAULT_ERROR_MSG,
      res.status,
      payload
    );
    throw error;
  }

  return payload as T;
};
