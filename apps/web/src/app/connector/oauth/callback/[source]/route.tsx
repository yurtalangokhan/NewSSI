import { backendRequest } from "@/lib/api/http/server";
import { NextRequest, NextResponse } from "next/server";
import { appSettings } from "@/lib/settings";

// TODO: deprecate this and just go directly to the backend via /api/...
// For some reason Egnyte doesn't work when using /api, so leaving this as is for now
// If we do try and remove this, make sure we test the Egnyte connector oauth flow
export async function GET(request: NextRequest) {
  try {
    const response = await backendRequest({
      service: "agent",
      path: request.nextUrl.pathname,
      query: request.nextUrl.searchParams,
      request,
      method: "GET",
      signal: request.signal,
    });

    const responseData = await response.json();
    if (responseData.redirect_url) {
      return NextResponse.redirect(responseData.redirect_url);
    }

    return new NextResponse(JSON.stringify(responseData), {
      status: response.status,
      headers: response.headers,
    });
  } catch (error: unknown) {
    console.error("Proxy error:", error);
    return NextResponse.json(
      {
        message: "Proxy error",
        error:
          error instanceof Error ? error.message : "An unknown error occurred",
      },
      { status: 500 }
    );
  }
}
