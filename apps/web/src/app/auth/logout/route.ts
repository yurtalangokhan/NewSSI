import { getAuthTypeMetadataSS, logoutSS } from "@/lib/userSS";
import { AuthType } from "@/lib/constants";
import { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const handleLogout = async (request: NextRequest) => {
  // Directs the logout request to the appropriate FastAPI endpoint.
  // Needed since env variables don't work well on the client-side
  const authTypeMetadata = await getAuthTypeMetadataSS();
  const response = await logoutSS(authTypeMetadata.authType, request.headers);

  if (response && !response.ok) {
    return new Response(response.body, { status: response?.status });
  }

  // Always clear the auth cookie on logout. This is critical for the JWT
  // auth backend where destroy_token is a no-op (stateless), but is also
  // the correct thing to do for Redis/Postgres backends — the server-side
  // Set-Cookie from FastAPI never reaches the browser since logoutSS is a
  // server-to-server fetch.
  const cookiesToDelete = ["fastapiusersauth", "session", "refresh_token", "id_token"];
  const cookieOptions = {
    path: "/",
    secure: process.env.NODE_ENV === "production",
    httpOnly: true,
    sameSite: "lax" as const,
  };

  const headers = new Headers();

  cookiesToDelete.forEach((cookieName) => {
    headers.append(
      "Set-Cookie",
      `${cookieName}=; Max-Age=0; ${Object.entries(cookieOptions)
        .map(([key, value]) => `${key}=${value}`)
        .join("; ")}`
    );
  });

  if (authTypeMetadata.authType === AuthType.OIDC) {
    const issuer = process.env.KEYCLOAK_ISSUER_URL?.replace(/\/$/, "");
    const clientId = process.env.KEYCLOAK_CLIENT_ID || "agenticai-web";
    const idTokenHint = request.cookies.get("id_token")?.value;

    if (issuer) {
      const webDomain = process.env.WEB_DOMAIN?.replace(/\/$/, "");
      const postLogoutRedirectUri = `${webDomain || request.nextUrl.origin}/auth/login`;
      const logoutUrl = new URL(`${issuer}/protocol/openid-connect/logout`);
      logoutUrl.searchParams.set("client_id", clientId);
      logoutUrl.searchParams.set(
        "post_logout_redirect_uri",
        postLogoutRedirectUri
      );
      if (idTokenHint) {
        logoutUrl.searchParams.set("id_token_hint", idTokenHint);
      }

      const redirectResponse = NextResponse.redirect(logoutUrl.toString(), 307);
      headers.forEach((value, key) => {
        redirectResponse.headers.append(key, value);
      });
      return redirectResponse;
    }
  }

  return new Response(null, {
    status: 204,
    headers: headers,
  });
};

export const POST = async (request: NextRequest) => {
  return handleLogout(request);
};

export const GET = async (request: NextRequest) => {
  return handleLogout(request);
};
