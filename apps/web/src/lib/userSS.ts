import { User } from "./types";
import { AuthType, SERVER_SIDE_ONLY__AUTH_TYPE } from "./constants";
import { UrlBuilder, buildUserServiceUrl, fetchUserServiceSS } from "./utilsSS";
import { cookies as getCookies } from "next/headers";

export interface AuthTypeMetadata {
  authType: AuthType;
  autoRedirect: boolean;
  requiresVerification: boolean;
  anonymousUserEnabled: boolean | null;
  hasUsers: boolean;
  oauthEnabled: boolean;
  externalKeycloak: boolean;
  external_keycloak?: boolean;
}

export const getAuthTypeMetadataSS = async (): Promise<AuthTypeMetadata> => {
  try {
    const response = await fetchUserServiceSS("/api/auth/type");
    if (!response.ok) {
      throw new Error(`Failed auth/type fetch: ${response.status}`);
    }
    return (await response.json()) as AuthTypeMetadata;
  } catch {
    return {
      // Preserve configured auth mode when backend /auth/type is temporarily unavailable.
      authType: SERVER_SIDE_ONLY__AUTH_TYPE,
      autoRedirect: false,
      requiresVerification: false,
      anonymousUserEnabled: true,
      hasUsers: true,
      oauthEnabled: false,
      externalKeycloak: false,
      external_keycloak: false,
    };
  }
};

const getOIDCAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  const url = new UrlBuilder("/api/auth/oidc/authorize");
  if (nextUrl) {
    url.addParam("next", nextUrl);
  }
  url.addParam("redirect", true);

  return url.toString();
};

const getGoogleOAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  const url = new UrlBuilder("/api/auth/oauth/authorize");
  if (nextUrl) {
    url.addParam("next", nextUrl);
  }
  url.addParam("redirect", true);

  return url.toString();
};

const getSAMLAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  const url = UrlBuilder.fromInternalUrl("/auth/saml/authorize");
  if (nextUrl) {
    url.addParam("next", nextUrl);
  }

  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error("Failed to fetch data");
  }

  const data: { authorization_url: string } = await res.json();
  return data.authorization_url;
};

export const getAuthUrlSS = async (
  authType: AuthType,
  nextUrl: string | null
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
      return await getOIDCAuthUrlSS(nextUrl);
    }
  }
};

const logoutStandardSS = async (headers: Headers): Promise<Response> => {
  return await fetch(buildUserServiceUrl("/api/auth/logout"), {
    method: "POST",
    headers: headers,
  });
};

const logoutSAMLSS = async (headers: Headers): Promise<Response> => {
  return await fetch(buildUserServiceUrl("/api/auth/saml/logout"), {
    method: "POST",
    headers: headers,
  });
};

export const logoutSS = async (
  authType: AuthType,
  headers: Headers
): Promise<Response | null> => {
  switch (authType) {
    case AuthType.SAML: {
      return await logoutSAMLSS(headers);
    }
    default: {
      return await logoutStandardSS(headers);
    }
  }
};

export const getCurrentUserSS = async (): Promise<User | null> => {
  try {
    // Avoid noisy backend 401 calls when there is clearly no authenticated session.
    if (!(await hasAuthSessionCookieSS())) {
      return null;
    }

    const response = await fetchUserServiceSS("/api/auth/me");
    if (response.status === 401) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`Failed /me fetch: ${response.status}`);
    }
    return (await response.json()) as User;
  } catch {
    return null;
  }
};

export const hasAuthSessionCookieSS = async (): Promise<boolean> => {
  const cookieStore = await getCookies();
  return (
    cookieStore.has("fastapiusersauth") ||
    cookieStore.has("access_token") ||
    cookieStore.has("refresh_token") ||
    cookieStore.has("session") ||
    cookieStore.has("id_token")
  );
};

export const processCookies = (cookies: {
  getAll(): { name: string; value: string }[];
}): string => {
  let cookieString = cookies
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");

  // Inject debug auth cookie for local development against remote backend (only if not already present)
  if (process.env.DEBUG_AUTH_COOKIE && process.env.NODE_ENV === "development") {
    const hasAuthCookie = cookieString
      .split(/;\s*/)
      .some((c) => c.startsWith("fastapiusersauth="));
    if (!hasAuthCookie) {
      const debugCookie = `fastapiusersauth=${process.env.DEBUG_AUTH_COOKIE}`;
      cookieString = cookieString
        ? `${cookieString}; ${debugCookie}`
        : debugCookie;
    }
  }

  return cookieString;
};
