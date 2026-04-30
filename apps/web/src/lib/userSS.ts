import { User } from "./types";
import { AuthType } from "./constants";
import { UrlBuilder, buildUrl } from "./utilsSS";

export interface AuthTypeMetadata {
  authType: AuthType;
  autoRedirect: boolean;
  requiresVerification: boolean;
  anonymousUserEnabled: boolean | null;
  passwordMinLength: number;
  hasUsers: boolean;
  oauthEnabled: boolean;
}

export const getAuthTypeMetadataSS = async (): Promise<AuthTypeMetadata> => {
  // Return default for development mode - skip backend call
  return {
    authType: AuthType.BASIC,
    autoRedirect: false,
    requiresVerification: false,
    anonymousUserEnabled: true,
    passwordMinLength: 8,
    hasUsers: true,
    oauthEnabled: false,
  };
};

const getOIDCAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  const url = UrlBuilder.fromClientUrl("/api/auth/oidc/authorize");
  if (nextUrl) {
    url.addParam("next", nextUrl);
  }
  url.addParam("redirect", true);

  return url.toString();
};

const getGoogleOAuthUrlSS = async (nextUrl: string | null): Promise<string> => {
  const url = UrlBuilder.fromClientUrl("/api/auth/oauth/authorize");
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
  return await fetch(buildUrl("/auth/logout"), {
    method: "POST",
    headers: headers,
  });
};

const logoutSAMLSS = async (headers: Headers): Promise<Response> => {
  return await fetch(buildUrl("/auth/saml/logout"), {
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
  // Return default dev user for development mode - skip backend call
  return {
    id: "dev-user",
    email: "dev@local.dev",
    is_active: true,
    is_superuser: true,
    is_verified: true,
    role: "admin" as any,
    preferences: {
      chosen_assistants: null,
      visible_assistants: [],
      hidden_assistants: [],
      default_model: null,
      recent_assistants: [],
      auto_scroll: true,
      shortcut_enabled: true,
      temperature_override_enabled: false,
      theme_preference: null,
      chat_background: null,
      default_app_mode: "CHAT",
    },
    team_name: null,
    is_anonymous_user: false,
    password_configured: true,
  };
};

export const processCookies = (cookies: { getAll(): { name: string; value: string }[] }): string => {
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
