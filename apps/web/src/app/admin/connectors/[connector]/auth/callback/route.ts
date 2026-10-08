import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";
import { getDomain } from "@/lib/navigation/redirect.server";
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  GMAIL_AUTH_IS_ADMIN_COOKIE_NAME,
  GOOGLE_DRIVE_AUTH_IS_ADMIN_COOKIE_NAME,
} from "@/lib/constants";
import {
  CRAFT_OAUTH_COOKIE_NAME,
  CRAFT_CONFIGURE_PATH,
} from "@/app/craft/v1/constants";
import { serializeServerCookies } from "@/lib/api/server-context";
import { backendRequest } from "@/lib/api/http/server";

export const GET = async (request: NextRequest) => {
  const requestCookies = await cookies();
  const connector = request.url.includes("gmail") ? "gmail" : "google-drive";
  const response = await backendRequest({
    ...integrationsEndpoints.connectorOAuthCallbackBackend(connector).backend,
    query: request.nextUrl.searchParams,
    headers: {
      cookie: serializeServerCookies(requestCookies),
    },
  });

  if (!response.ok) {
    return NextResponse.redirect(new URL("/auth/error", getDomain(request)));
  }

  // Check for build mode OAuth flag (redirects to build admin panel)
  const isBuildMode =
    requestCookies.get(CRAFT_OAUTH_COOKIE_NAME)?.value === "true";
  if (isBuildMode) {
    const redirectResponse = NextResponse.redirect(
      new URL(CRAFT_CONFIGURE_PATH, getDomain(request))
    );
    redirectResponse.cookies.delete(CRAFT_OAUTH_COOKIE_NAME);
    return redirectResponse;
  }

  const authCookieName =
    connector === "gmail"
      ? GMAIL_AUTH_IS_ADMIN_COOKIE_NAME
      : GOOGLE_DRIVE_AUTH_IS_ADMIN_COOKIE_NAME;

  if (requestCookies.get(authCookieName)?.value?.toLowerCase() === "true") {
    return NextResponse.redirect(
      new URL(`/admin/connectors/${connector}`, getDomain(request))
    );
  }

  return NextResponse.redirect(new URL("/user/connectors", getDomain(request)));
};
