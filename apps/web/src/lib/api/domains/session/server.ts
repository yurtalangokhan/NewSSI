import { parseResponseModel } from "@/lib/api/responseModel";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";
import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";

import { backendRequest } from "@/lib/api/http/server";
import type { User } from "@/lib/types";
import { AuthType } from "@/lib/constants";
import { getServerRequestHeaders } from "@/lib/api/server-context";
import { cookies as getCookies } from "next/headers";
import type { AuthTypeMetadata } from "@/lib/api/domains/session/types";

import type { BackendTarget } from "@/lib/api/http/types";
import { appSettings } from "@/lib/settings";

async function fetchUserServiceSS(
  target: BackendTarget,
  options: RequestInit = {}
): Promise<Response> {
  return backendRequest({
    ...target,
    credentials: "include",
    cache: "no-store",
    ...options,
    headers: await getServerRequestHeaders(options.headers),
  });
}

export function refreshSessionForMiddlewareSS(
  cookieHeader: string
): Promise<Response> {
  return backendRequest({
    ...sessionEndpoints.refresh.backend,
    method: "POST",
    headers: {
      Cookie: cookieHeader,
      "Content-Type": "application/json",
    },
  });
}

function buildRelativeUrl(
  path: string,
  params: Record<string, string | boolean | null | undefined>
): string {
  const url = new URL(path, "http://server-relative-url");
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  });
  return `${url.pathname}${url.search}`;
}

export const getAuthTypeMetadataSS = async (): Promise<AuthTypeMetadata> => {
  try {
    const response = await fetchUserServiceSS(
      sessionEndpoints.authType.backend
    );
    if (!response.ok) {
      throw new Error(`Failed auth/type fetch: ${response.status}`);
    }
    return await parseResponseModel<AuthTypeMetadata>(response);
  } catch {
    return {
      // Preserve configured auth mode when backend /auth/type is temporarily unavailable.
      authType: appSettings.SERVER_SIDE_ONLY__AUTH_TYPE,
      autoRedirect: false,
      requiresVerification: false,
      anonymousUserEnabled: true,
      hasUsers: true,
      oauthEnabled: false,
      // Keycloak has no disabled mode; the service does not run without it.
      keycloakEnabled: true,
      externalKeycloak: false,
      external_keycloak: false,
    };
  }
};

export function fetchAuthTypeResponseSS(): Promise<Response> {
  return fetchUserServiceSS(sessionEndpoints.authType.backend);
}

const getOIDCAuthUrlSS = async (
  nextUrl: string | null,
  idpHint?: string | null,
  options?: { prompt?: string }
): Promise<string> => {
  return buildRelativeUrl(sessionEndpoints.authorizeOidc.browserPath, {
    next: nextUrl,
    kc_idp_hint: idpHint,
    prompt: options?.prompt,
    redirect: true,
  });
};

const getGoogleOAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  return buildRelativeUrl(sessionEndpoints.oauthAuthorize.browserPath, {
    next: nextUrl,
    redirect: true,
  });
};

const getSAMLAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  const path = buildRelativeUrl(sessionEndpoints.samlAuthorize.backend.path, {
    next: nextUrl,
  });

  const res = await backendRequest({
    service: sessionEndpoints.samlAuthorize.backend.service,
    path,
  });
  if (!res.ok) {
    throw new Error("Failed to fetch data");
  }

  const data: { authorization_url: string } = await res.json();
  return data.authorization_url;
};

export const getAuthUrlSS = async (
  authType: AuthType,
  nextUrl: string | null,
  idpHint?: string | null,
  options?: { prompt?: string }
): Promise<string> => {
  // Returns the auth url for the given auth type

  switch (authType) {
    case AuthType.BASIC:
      return "";
    case AuthType.GOOGLE_OAUTH: {
      return await getGoogleOAuthUrlSS(nextUrl);
    }
    case AuthType.CLOUD: {
      return await getGoogleOAuthUrlSS(nextUrl);
    }
    case AuthType.SAML: {
      return await getSAMLAuthUrlSS(nextUrl);
    }
    case AuthType.OIDC: {
      return await getOIDCAuthUrlSS(nextUrl, idpHint, options);
    }
  }
};

const logoutStandardSS = async (
  headers: Headers,
  postLogoutRedirectUri?: string
): Promise<Response> => {
  const query = new URLSearchParams();
  if (postLogoutRedirectUri) {
    query.set("post_logout_redirect_uri", postLogoutRedirectUri);
  }
  return await backendRequest({
    ...sessionEndpoints.logout.backend,
    query,
    method: "POST",
    headers: headers,
  });
};

const logoutSAMLSS = async (headers: Headers): Promise<Response> => {
  return await backendRequest({
    ...sessionEndpoints.samlLogout.backend,
    method: "POST",
    headers: headers,
  });
};

export const logoutSS = async (
  authType: AuthType,
  headers: Headers,
  postLogoutRedirectUri?: string
): Promise<Response | null> => {
  switch (authType) {
    case AuthType.SAML: {
      return await logoutSAMLSS(headers);
    }
    default: {
      return await logoutStandardSS(headers, postLogoutRedirectUri);
    }
  }
};

async function refreshSessionSS(): Promise<string | null> {
  try {
    if (!(await hasRefreshTokenCookieSS())) {
      return null;
    }
    const refreshResponse = await fetchUserServiceSS(
      sessionEndpoints.refresh.backend,
      { method: "POST" }
    );
    if (!refreshResponse.ok) {
      return null;
    }
    const data = await parseResponseModel<{ access_token?: string }>(
      refreshResponse
    );
    return data?.access_token || null;
  } catch {
    return null;
  }
}

export const getCurrentUserSS = async (): Promise<User | null> => {
  try {
    // Avoid noisy backend 401 calls when there is clearly no authenticated session.
    if (!(await hasAuthSessionCookieSS())) {
      return null;
    }

    let response = await fetchUserServiceSS(
      sessionEndpoints.getCurrentUser.backend
    );
    if (response.status === 401 && (await hasRefreshTokenCookieSS())) {
      const refreshedAccessToken = await refreshSessionSS();
      if (refreshedAccessToken) {
        response = await fetchUserServiceSS(
          sessionEndpoints.getCurrentUser.backend,
          {
            headers: {
              Authorization: `Bearer ${refreshedAccessToken}`,
            },
          }
        );
      }
    }

    if (response.status === 401) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`Failed /me fetch: ${response.status}`);
    }
    return await parseResponseModel<User>(response);
  } catch {
    return null;
  }
};

interface CurrentUserAccess {
  permissions: string[];
  // Backend-resolved admin-tier role status. Admin page access is separately
  // governed by explicit :view permissions from the route registry.
  isAdmin: boolean;
}

export const getCurrentUserAccessSS = async (): Promise<CurrentUserAccess> => {
  try {
    if (!(await hasAuthSessionCookieSS())) {
      return { permissions: [], isAdmin: false };
    }

    let response = await fetchUserServiceSS(
      accessEndpoints.getCurrentUserPermissions.backend
    );
    if (response.status === 401 && (await hasRefreshTokenCookieSS())) {
      const refreshedAccessToken = await refreshSessionSS();
      if (refreshedAccessToken) {
        response = await fetchUserServiceSS(
          accessEndpoints.getCurrentUserPermissions.backend,
          {
            headers: {
              Authorization: `Bearer ${refreshedAccessToken}`,
            },
          }
        );
      }
    }

    if (!response.ok) {
      return { permissions: [], isAdmin: false };
    }
    const payload = await parseResponseModel<{
      permissions?: string[];
      is_admin?: boolean;
    }>(response);
    return {
      permissions: payload.permissions ?? [],
      isAdmin: payload.is_admin ?? false,
    };
  } catch {
    return { permissions: [], isAdmin: false };
  }
};

const hasAuthSessionCookieSS = async (): Promise<boolean> => {
  const cookieStore = await getCookies();
  return (
    cookieStore.has("fastapiusersauth") ||
    cookieStore.has("access_token") ||
    cookieStore.has("refresh_token") ||
    cookieStore.has("session") ||
    cookieStore.has("id_token")
  );
};

const hasRefreshTokenCookieSS = async (): Promise<boolean> => {
  const cookieStore = await getCookies();
  return cookieStore.has("refresh_token");
};
