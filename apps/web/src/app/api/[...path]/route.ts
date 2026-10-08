import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/api/routeBackendUrl";
import { backendRequest } from "@/lib/api/http/server";
import { deriveBackendAuthHeaders } from "@/lib/api/proxy";
import { stripTrustedContextHeaders } from "@/lib/api/proxySecurity";
import { appSettings } from "@/lib/settings";

/*
 * Compatibility catch-all that resolves a domain-owned backend target and
 * forwards it through the configured gateway.
 *
 * Service endpoints that already OWN a dedicated Next.js route handler
 * (e.g. /api/agent/*, /api/rag/*, /api/auth/*) are NOT caught here.
 */

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

export async function HEAD(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

export async function OPTIONS(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  const params = await props.params;
  return handleRequest(request, params.path);
}

async function handleRequest(request: NextRequest, path: string[]) {
  if (
    appSettings.NODE_ENV !== "development" &&
    !appSettings.OVERRIDE_API_PRODUCTION
  ) {
    return NextResponse.json(
      {
        message:
          "This API is only available in development mode. In production, something else (e.g. nginx) should handle this.",
      },
      { status: 404 }
    );
  }

  try {
    const backendUrl = getBackendUrl(path);

    const urlParams = new URLSearchParams(request.url.split("?")[1]);
    urlParams.forEach((value, key) => {
      backendUrl.searchParams.append(key, value);
    });

    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("content-length");
    stripTrustedContextHeaders(headers);
    // The default fallback below routes to agent-service, which is
    // bearer-token only and never reads cookies -- a request that only
    // carries the browser's access_token cookie (the normal case; the
    // browser's own fetch never sets an explicit Authorization header)
    // would otherwise get a bare 401 here even though the session is
    // perfectly valid.
    const { Authorization } = deriveBackendAuthHeaders(request);
    if (Authorization) {
      headers.set("Authorization", Authorization);
    }
    if (
      appSettings.DEBUG_AUTH_COOKIE &&
      appSettings.NODE_ENV === "development"
    ) {
      const existingCookies = headers.get("cookie") || "";
      const debugCookie = `fastapiusersauth=${appSettings.DEBUG_AUTH_COOKIE}`;
      headers.set(
        "cookie",
        existingCookies ? `${existingCookies}; ${debugCookie}` : debugCookie
      );
    }

    const response = await backendRequest({
      url: backendUrl,
      method: request.method,
      headers: headers,
      body: request.body,
      signal: request.signal,
      redirect: "manual",
      // @ts-ignore
      duplex: "half",
    });

    const setCookies =
      // @ts-ignore - undici provides getSetCookie in Node.
      response.headers.getSetCookie?.() ??
      (response.headers.get("set-cookie")
        ? [response.headers.get("set-cookie")]
        : []);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("set-cookie");

    if (
      response.headers.get("Transfer-Encoding") === "chunked" ||
      response.headers.get("Content-Type")?.includes("stream")
    ) {
      const { readable, writable } = new TransformStream();
      response.body?.pipeTo(writable);

      const proxyResponse = new NextResponse(readable, {
        status: response.status,
        headers: responseHeaders,
      });
      for (const cookie of setCookies) {
        if (cookie) {
          proxyResponse.headers.append("set-cookie", cookie);
        }
      }
      return proxyResponse;
    } else {
      const proxyResponse = new NextResponse(response.body, {
        status: response.status,
        headers: responseHeaders,
      });
      for (const cookie of setCookies) {
        if (cookie) {
          proxyResponse.headers.append("set-cookie", cookie);
        }
      }
      return proxyResponse;
    }
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
