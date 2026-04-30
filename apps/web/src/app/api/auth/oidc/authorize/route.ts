import { buildUrl } from "@/lib/utilsSS";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  const target = new URL(buildUrl("/auth/oidc/authorize"));
  const dynamicRedirectUri = `${request.nextUrl.origin}/auth/oidc/callback`;

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

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
    },
  });
};
