import { getDomain } from "@/lib/redirectSS";
import { buildPublicUserAuthUrl } from "@/lib/api/publicUserAuthUrl";
import { getLoginPath } from "@/lib/auth/loginRoute";
import { getAuthTypeMetadataSS } from "@/lib/userSS";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  // Wrapper around the FastAPI endpoint /auth/oidc/callback,
  // which adds back a redirect to the main app.
  const url = buildPublicUserAuthUrl("/oidc/callback");
  url.search = request.nextUrl.search;
  const callbackBase = getDomain(request).replace(/\/$/, "");
  url.searchParams.set("redirect_uri", `${callbackBase}/auth/oidc/callback`);
  const cookieHeader = request.headers.get("cookie") || "";

  // Set 'redirect' to 'manual' to prevent automatic redirection
  const response = await fetch(url.toString(), {
    redirect: "manual",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
  const setCookieHeaders =
    typeof (response.headers as Headers & { getSetCookie?: () => string[] })
      .getSetCookie === "function"
      ? (
          response.headers as Headers & { getSetCookie: () => string[] }
        ).getSetCookie()
      : (() => {
          const single = response.headers.get("set-cookie");
          return single ? [single] : [];
        })();

  // Handle any non-success response
  if (!response.ok) {
    let errorMessage = `Authentication error (status ${response.status})`;
    try {
      const errorBody = await response.json();
      if (errorBody?.detail) {
        errorMessage = String(errorBody.detail);
      }
    } catch {
      // Ignore parse failures and keep generic message.
    }

    // For 401, redirect to login with error. For others, go to error page.
    if (response.status === 401) {
      const authTypeMetadata = await getAuthTypeMetadataSS();
      const loginUrl = new URL(
        getLoginPath(authTypeMetadata),
        getDomain(request)
      );
      loginUrl.searchParams.set("oidcError", errorMessage);
      return NextResponse.redirect(loginUrl);
    } else {
      const errorUrl = new URL("/auth/error", getDomain(request));
      errorUrl.searchParams.set("error", errorMessage);
      return NextResponse.redirect(errorUrl);
    }
  }

  if (setCookieHeaders.length === 0) {
    const errorUrl = new URL("/auth/error", getDomain(request));
    errorUrl.searchParams.set(
      "error",
      "No session cookies received from authentication service"
    );
    return NextResponse.redirect(errorUrl);
  }

  // Get the redirect URL from the backend's 'Location' header, or default to '/'
  const redirectUrl = response.headers.get("location") || "/";

  const redirectResponse = NextResponse.redirect(
    new URL(redirectUrl, getDomain(request))
  );

  for (const cookie of setCookieHeaders) {
    redirectResponse.headers.append("set-cookie", cookie);
  }
  return redirectResponse;
};
