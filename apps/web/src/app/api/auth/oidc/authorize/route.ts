import { unwrapResponseModel } from "@/lib/api/responseModel";
import type { ResponseModel } from "@/lib/api/responseModel";
import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";

import { backendRequest } from "@/lib/api/http/server";
import { getDomain } from "@/lib/navigation/redirect.server";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  const query = new URLSearchParams();
  const callbackBase = getDomain(request).replace(/\/$/, "");
  const dynamicRedirectUri = `${callbackBase}/auth/oidc/callback`;

  request.nextUrl.searchParams.forEach((value, key) => {
    query.set(key, value);
  });

  if (!query.has("redirect_uri")) {
    query.set("redirect_uri", dynamicRedirectUri);
  }

  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  const response = await backendRequest({
    ...sessionEndpoints.authorizeOidc.backend,
    query,
    method: "GET",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    redirect: "manual",
  });
  const setCookies =
    typeof (response.headers as Headers & { getSetCookie?: () => string[] })
      .getSetCookie === "function"
      ? (
          response.headers as Headers & { getSetCookie: () => string[] }
        ).getSetCookie()
      : response.headers.get("set-cookie")
        ? [response.headers.get("set-cookie")!]
        : [];
  const withCookies = (result: NextResponse) => {
    setCookies.forEach((cookie) => result.headers.append("set-cookie", cookie));
    return result;
  };

  if (response.status >= 300 && response.status < 400) {
    const location = response.headers.get("location");
    if (location) {
      return withCookies(
        NextResponse.redirect(location, { status: response.status })
      );
    }
  }

  // Some backends return JSON with authorization URL instead of redirecting directly.
  if (response.ok) {
    try {
      const payload = await response.clone().json();
      const data = unwrapResponseModel(
        payload as ResponseModel<{
          authorization_url?: string;
          authorize_url?: string;
        }>
      );
      const authorizationUrl = data?.authorization_url || data?.authorize_url;
      const shouldRedirect =
        request.nextUrl.searchParams.get("redirect") === "true";

      if (shouldRedirect && authorizationUrl) {
        return withCookies(
          NextResponse.redirect(authorizationUrl, { status: 307 })
        );
      }

      return withCookies(
        NextResponse.json(payload, { status: response.status })
      );
    } catch {
      // Fall through to raw response body handling.
    }
  }

  const body = await response.text();
  return withCookies(
    new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type":
          response.headers.get("content-type") || "application/json",
      },
    })
  );
};
