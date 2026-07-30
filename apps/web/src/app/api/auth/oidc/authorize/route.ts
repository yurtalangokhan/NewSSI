import { buildPublicUserAuthUrl } from "@/lib/api/publicUserAuthUrl";
import { getDomain } from "@/lib/redirectSS";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  const target = buildPublicUserAuthUrl("/oidc/authorize");
  const callbackBase = getDomain(request).replace(/\/$/, "");
  const dynamicRedirectUri = `${callbackBase}/auth/oidc/callback`;

  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.set(key, value);
  });

  if (!target.searchParams.has("redirect_uri")) {
    target.searchParams.set("redirect_uri", dynamicRedirectUri);
  }

  const cookieHeader = (await cookies())
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");

  const response = await fetch(target.toString(), {
    method: "GET",
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    redirect: "manual",
  });

  if (response.status >= 300 && response.status < 400) {
    const location = response.headers.get("location");
    if (location) {
      return NextResponse.redirect(location, { status: response.status });
    }
  }

  // Some backends return JSON with authorization URL instead of redirecting directly.
  if (response.ok) {
    try {
      const payload = await response.json();
      const authorizationUrl =
        payload?.authorization_url || payload?.authorize_url;
      const shouldRedirect =
        request.nextUrl.searchParams.get("redirect") === "true";

      if (shouldRedirect && authorizationUrl) {
        return NextResponse.redirect(authorizationUrl, { status: 307 });
      }

      return NextResponse.json(payload, { status: response.status });
    } catch {
      // Fall through to raw response body handling.
    }
  }

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
    },
  });
};
