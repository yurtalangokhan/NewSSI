import { userServicePayloadResponse } from "@/lib/api/userServiceResponse";
import type { ApiRequestOptions } from "@/lib/api/http/types";
import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import {
  FetchError,
  parseApiErrorResponse,
  throwParsedApiError,
} from "@/lib/api/http/errors";
import { User } from "@/lib/types";

// ============================================================================
// Session operations (auth required)
// ============================================================================

/**
 * Fetch current user, throwing a FetchError on non-OK responses.
 * Used by SWR hooks that rely on thrown errors for error state.
 */
export async function fetchCurrentUserWithError(): Promise<User> {
  const res = await requestSessionResponse(
    sessionEndpoints.getCurrentUser.browserPath
  );
  if (!res.ok) {
    const parsedError = await parseApiErrorResponse(res);
    throw new FetchError(
      parsedError.userMessage,
      res.status,
      parsedError.raw,
      parsedError
    );
  }
  return (await parseJsonResponse<User>(res)) as User;
}

/**
 * Fetch current user returning raw Response for advanced callers.
 * Use this when you need to check response status codes.
 */

/**
 * Fetch current user returning null on non-OK responses.
 * Use for non-critical user data where absence is acceptable.
 */
export async function fetchCurrentUserOrNull(): Promise<User | null> {
  const res = await requestSessionResponse(
    sessionEndpoints.getCurrentUser.browserPath,
    {
      redirectOnAuthError: false,
    }
  );
  if (!res.ok) {
    return null;
  }
  return res.json() as Promise<User>;
}

// ============================================================================
// Public auth operations (no auth required)
// ============================================================================

/**
 * Standard username/password login.
 * Posts form-encoded data to /api/auth/login
 */
export function basicLogin(
  username: string,
  password: string
): Promise<Response> {
  const params = new URLSearchParams([
    ["username", username],
    ["password", password],
  ]);

  return requestSessionResponse(sessionEndpoints.login.browserPath, {
    method: sessionEndpoints.login.method,
    auth: "public",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
  });
}

/**
 * External Keycloak login.
 * Posts form-encoded data to /api/auth/external/login
 */
export function externalKeycloakLogin(
  username: string,
  password: string
): Promise<Response> {
  const params = new URLSearchParams([
    ["username", username],
    ["password", password],
  ]);

  return requestSessionResponse(sessionEndpoints.externalLogin.browserPath, {
    method: sessionEndpoints.externalLogin.method,
    auth: "public",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
  });
}

export function requestExternalLoginRedirect(): Promise<Response> {
  return requestSessionResponse(sessionEndpoints.externalLogin.browserPath, {
    method: sessionEndpoints.externalLogin.method,
    auth: "public",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams().toString(),
  });
}

/**
 * User registration/signup.
 * Posts JSON data to /api/auth/register.
 * Uses public auth since registration doesn't require an existing session.
 */
export function basicSignup(
  email: string,
  password: string,
  firstName: string,
  lastName: string,
  referralSource?: string,
  captchaToken?: string,
  username?: string
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Add captcha token to headers if provided
  if (captchaToken) {
    headers["X-Captcha-Token"] = captchaToken;
  }

  const body: Record<string, string> = {
    email,
    username: username || email,
    password,
    first_name: firstName,
    last_name: lastName,
  };
  if (referralSource) {
    body.referral_source = referralSource;
  }
  if (captchaToken) {
    body.captcha_token = captchaToken;
  }

  return requestSessionResponse(sessionEndpoints.register.browserPath, {
    method: sessionEndpoints.register.method,
    auth: "public",
    headers,
    body: JSON.stringify(body),
  });
}

// ============================================================================
// Auth type
// ============================================================================

export async function fetchAuthTypeForSWR<T>(): Promise<T> {
  const response = await requestSessionResponse(
    sessionEndpoints.authType.browserPath,
    {
      headers: { "X-Language": i18n.language },
    }
  );
  if (!response.ok) {
    const parsedError = await parseApiErrorResponse(response);
    throw new FetchError(
      parsedError.userMessage,
      response.status,
      parsedError.raw,
      parsedError
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    return {} as T;
  }
}

// ============================================================================
// Password reset
// ============================================================================

export async function forgotPassword(email: string): Promise<void> {
  const response = await apiRequest(
    sessionEndpoints.forgotPassword.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    const errorMessage =
      error?.detail || "An error occurred during password reset.";
    throw new Error(errorMessage);
  }
}

export async function resetPassword(
  token: string,
  password: string
): Promise<void> {
  const response = await apiRequest(
    sessionEndpoints.resetPassword.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    if (error?.detail?.code === "RESET_PASSWORD_INVALID_PASSWORD") {
      throw new Error(error.detail.reason || "Invalid password");
    }
    const errorMessage =
      error?.detail || "An error occurred during password reset.";
    throw new Error(errorMessage);
  }
}

// ============================================================================
// Email verification
// ============================================================================

export async function requestVerifyToken(email: string): Promise<Response> {
  return apiRequest(sessionEndpoints.requestVerifyToken.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export async function verifyEmail(token: string): Promise<Response> {
  return apiRequest(sessionEndpoints.verifyEmail.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
}

export function loginAnonymousTenantUser(pathValue: string): Promise<Response> {
  return apiRequest(
    sessionEndpoints.loginAnonymousTenantUser(pathValue).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
    }
  );
}

export function impersonateTenantUser(
  headers: { "Content-Type": string; Authorization: string },
  payload: { email: string }
): Promise<Response> {
  return apiRequest(sessionEndpoints.impersonateTenantUser.browserPath, {
    method: "POST",
    headers: headers,
    body: JSON.stringify(payload),
    credentials: "same-origin",
  });
}

export function verifyCurrentSession(): Promise<Response> {
  return requestSessionResponse(sessionEndpoints.getCurrentUser.browserPath, {
    redirectOnAuthError: false,
  });
}

export function refreshEnterpriseSession(
  payload: Record<string, unknown>
): Promise<Response> {
  return apiRequest(sessionEndpoints.refreshEnterpriseSession.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

import type { PersonalAccessToken } from "@/lib/api/domains/session/types";
import i18n from "@/i18n/config";
export async function fetchPersonalAccessTokens(): Promise<
  PersonalAccessToken[]
> {
  const response = await requestSessionResponse(
    sessionEndpoints.listPersonalAccessTokens.browserPath,
    {
      redirectOnAuthError: false,
    }
  );
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) return [];
    await throwParsedApiError(response, "Failed to fetch access tokens");
  }
  const data = (await response.json()) as
    | PersonalAccessToken[]
    | { api_keys?: PersonalAccessToken[] };
  return Array.isArray(data) ? data : data.api_keys ?? [];
}
export function createPersonalAccessTokenResponse(payload: {
  name: string;
  expiration_days: number | null;
}): Promise<Response> {
  return requestSessionResponse(
    sessionEndpoints.createPersonalAccessToken.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      redirectOnAuthError: false,
      body: JSON.stringify(payload),
    }
  );
}

export function deletePersonalAccessTokenResponse(
  patId: number
): Promise<Response> {
  return requestSessionResponse(
    sessionEndpoints.deletePersonalAccessToken(patId).browserPath,
    {
      method: "DELETE",
      redirectOnAuthError: false,
    }
  );
}

export function changeAccountPassword(payload: {
  old_password: string;
  new_password: string;
}): Promise<Response> {
  return requestSessionResponse(
    sessionEndpoints.changeAccountPassword.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      redirectOnAuthError: false,
      body: JSON.stringify(payload),
    }
  );
}

export function checkUserIsNoAuthUser(userId: string): boolean {
  return userId === "__no_auth_user__";
}

export async function logout(nextPath?: string): Promise<Response> {
  const logoutUrl = new URL("/auth/logout", window.location.origin);
  if (nextPath) logoutUrl.searchParams.set("next", nextPath);
  window.sessionStorage.setItem("logout_in_progress", "true");
  window.location.assign(logoutUrl.toString());
  return new Response(null, { status: 204 });
}

export async function refreshToken(
  customRefreshUrl: string
): Promise<null | Record<string, unknown>> {
  try {
    console.debug("Sending request to custom refresh URL");
    const url = customRefreshUrl.startsWith("http")
      ? new URL(customRefreshUrl)
      : new URL(customRefreshUrl, window.location.origin);
    url.searchParams.append("info", "json");
    url.searchParams.append("access_token_refresh_interval", "3600");
    const response = await apiRequest(url.toString(), { auth: "public" });
    if (!response.ok) {
      console.error(`Failed to refresh token: ${await response.text()}`);
      return null;
    }
    return response.json() as Promise<Record<string, unknown>>;
  } catch (error) {
    console.error("Error refreshing token:", error);
    throw error;
  }
}

async function requestSessionResponse(
  path: string,
  options: ApiRequestOptions = {}
): Promise<Response> {
  return userServicePayloadResponse(await apiRequest(path, options));
}
