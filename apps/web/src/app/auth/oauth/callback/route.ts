import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { getDomain } from "@/lib/navigation/redirect.server";

import { backendRequest } from "@/lib/api/http/server";
import { forwardSetCookies } from "@/lib/auth/forwardSetCookies";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  // Wrapper around the FastAPI endpoint /api/auth/oauth/callback,
  // which adds back a redirect to the main app.
  const cookieHeader = request.headers.get("cookie") || "";

  // Set 'redirect' to 'manual' to prevent automatic redirection
  const response = await backendRequest({
    ...sessionEndpoints.oauthCallback.backend,
    query: request.nextUrl.searchParams,
    redirect: "manual",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
  const setCookieHeader = response.headers.get("set-cookie");

  if (response.status === 401) {
    return NextResponse.redirect(
      new URL("/auth/create-account", getDomain(request))
    );
  }

  if (!setCookieHeader) {
    return NextResponse.redirect(new URL("/auth/error", getDomain(request)));
  }

  // Get the redirect URL from the backend's 'Location' header, or default to '/'
  const redirectUrl = response.headers.get("location") || "/";

  const redirectResponse = NextResponse.redirect(
    new URL(redirectUrl, getDomain(request))
  );

  forwardSetCookies(response.headers, redirectResponse.headers);
  return redirectResponse;
};
