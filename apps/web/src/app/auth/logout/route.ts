import { getAuthTypeMetadataSS, logoutSS } from "@/lib/userSS";
import { AuthType } from "@/lib/constants";
import { NextRequest, NextResponse } from "next/server";
import { getLoginPath } from "@/lib/auth/loginRoute";

const handleLogout = async (request: NextRequest) => {
  const authTypeMetadata = await getAuthTypeMetadataSS();
  let backendLogoutSucceeded = false;
  const publicWebOrigin =
    process.env.WEB_DOMAIN?.replace(/\/$/, "") || request.nextUrl.origin;

  // Call backend logout — this terminates the Keycloak SSO session
  // server-side via backchannel logout using the refresh_token cookie.
  // The backend Set-Cookie response is discarded (server-to-server fetch)
  // so we clear cookies manually below.
  try {
    await logoutSS(authTypeMetadata.authType, request.headers);
    backendLogoutSucceeded = true;
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
        secure: process.env.NODE_ENV === "production",
        httpOnly: true,
        sameSite: "lax",
      });
    });
  };

  const nextPath =
    request.nextUrl.searchParams.get("next") || getLoginPath(authTypeMetadata);

  // For OIDC, redirect to Keycloak's RP-initiated logout as a front-channel
  // courtesy step. The SSO session was already terminated server-side by the
  // backend, so this is a best-effort redirect to Keycloak's logout page.
  if (authTypeMetadata.authType === AuthType.OIDC && !backendLogoutSucceeded) {
    try {
      const issuer = process.env.KEYCLOAK_ISSUER_URL?.replace(/\/$/, "");
      const clientId = process.env.KEYCLOAK_CLIENT_ID || "agenticai-web";
      const idTokenHint = request.cookies.get("id_token")?.value;

      if (issuer) {
        const postLogoutRedirectUri = new URL(
          nextPath,
          publicWebOrigin
        ).toString();
        const logoutUrl = new URL(`${issuer}/protocol/openid-connect/logout`);
        logoutUrl.searchParams.set("client_id", clientId);
        logoutUrl.searchParams.set(
          "post_logout_redirect_uri",
          postLogoutRedirectUri
        );
        if (idTokenHint) {
          logoutUrl.searchParams.set("id_token_hint", idTokenHint);
        }

        const redirectResponse = NextResponse.redirect(
          logoutUrl.toString(),
          303
        );
        clearAuthCookies(redirectResponse);
        return redirectResponse;
      }
    } catch {
      // Fall through to basic redirect if OIDC logout construction fails
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
