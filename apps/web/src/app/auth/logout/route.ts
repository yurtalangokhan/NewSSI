import { getAuthTypeMetadataSS, logoutSS } from "@/lib/userSS";
import { AuthType } from "@/lib/constants";
import { NextRequest, NextResponse } from "next/server";
import { getLoginPath } from "@/lib/auth/loginRoute";
import { getDomain } from "@/lib/redirectSS";
import { buildOidcLogoutUrl } from "@/lib/auth/oidcLogout";

const handleLogout = async (request: NextRequest) => {
  const authTypeMetadata = await getAuthTypeMetadataSS();
  const publicWebOrigin = getDomain(request).replace(/\/$/, "");
  const useSecureCookies = (() => {
    try {
      return new URL(publicWebOrigin).protocol === "https:";
    } catch {
      return request.nextUrl.protocol === "https:";
    }
  })();
  const requestedNextPath = request.nextUrl.searchParams.get("next");
  const nextPath = requestedNextPath || getLoginPath(authTypeMetadata);
  const postLogoutRedirectUri = new URL(nextPath, publicWebOrigin).toString();

  // Call backend logout — this terminates the Keycloak SSO session
  // server-side via backchannel logout using the refresh_token cookie.
  // The backend Set-Cookie response is discarded (server-to-server fetch)
  // so we clear cookies manually below.
  try {
    const logoutResponse = await logoutSS(
      authTypeMetadata.authType,
      request.headers,
      postLogoutRedirectUri
    );
    await logoutResponse?.arrayBuffer();
  } catch {
    // Backend logout is best-effort. Cookies are cleared regardless.
  }

  // Clear all auth cookies so the browser has no session state.
  const cookiesToDelete = [
    "fastapiusersauth",
    "session",
    "refresh_token",
    "id_token",
    "access_token",
  ];
  const clearAuthCookies = (response: NextResponse) => {
    cookiesToDelete.forEach((cookieName) => {
      response.cookies.set(cookieName, "", {
        path: "/",
        maxAge: 0,
        secure: useSecureCookies,
        httpOnly: true,
        sameSite: "lax",
      });
    });
  };

  // Always try OIDC front-channel logout so Keycloak clears browser SSO cookies.
  // Backchannel logout invalidates the server-side session but cannot remove
  // cookies owned by the Keycloak origin from the user's browser.
  if (authTypeMetadata.authType === AuthType.OIDC) {
    const logoutUrl = buildOidcLogoutUrl({
      authType: authTypeMetadata.authType,
      issuer: process.env.KEYCLOAK_ISSUER_URL,
      clientId: process.env.KEYCLOAK_CLIENT_ID || "agenticai-web",
      postLogoutRedirectUri,
      idTokenHint: request.cookies.get("id_token")?.value,
    });

    if (logoutUrl) {
      const redirectResponse = NextResponse.redirect(logoutUrl.toString(), 303);
      clearAuthCookies(redirectResponse);
      return redirectResponse;
    }
  }

  const redirectResponse = NextResponse.redirect(
    new URL(nextPath, publicWebOrigin),
    303
  );
  clearAuthCookies(redirectResponse);
  return redirectResponse;
};

export const POST = async (request: NextRequest) => {
  return handleLogout(request);
};

export const GET = async (request: NextRequest) => {
  return handleLogout(request);
};
