import { getDomain } from "@/lib/redirectSS";
import { buildUserServiceUrl } from "@/lib/utilsSS";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  // Wrapper around the FastAPI endpoint /auth/oidc/callback,
  // which adds back a redirect to the main app.
  const url = new URL(buildUserServiceUrl("/api/auth/oidc/callback"));
  url.search = request.nextUrl.search;
  const callbackBase = getDomain(request).replace(/\/$/, "");
  url.searchParams.set(
    "redirect_uri",
    `${callbackBase}/auth/oidc/callback`
  );
  const cookieHeader = request.headers.get("cookie") || "";

  // Set 'redirect' to 'manual' to prevent automatic redirection
  const response = await fetch(url.toString(), {
    redirect: "manual",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
  const setCookieHeaders =
    typeof (response.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie === "function"
      ? (response.headers as Headers & { getSetCookie: () => string[] }).getSetCookie()
      : (() => {
          const single = response.headers.get("set-cookie");
          return single ? [single] : [];
        })();

  if (response.status === 401) {
    let errorMessage = "OIDC callback failed";
    try {
      const errorBody = await response.json();
      if (errorBody?.detail) {
        errorMessage = String(errorBody.detail);
      }
    } catch {
      // Ignore parse failures and keep generic message.
    }

    const loginUrl = new URL("/auth/login", getDomain(request));
    loginUrl.searchParams.set("oidcError", errorMessage);
    return NextResponse.redirect(
      loginUrl
    );
  }

  if (setCookieHeaders.length === 0) {
    return NextResponse.redirect(new URL("/auth/error", getDomain(request)));
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
