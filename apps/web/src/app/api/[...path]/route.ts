import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/api/routeBackendUrl";

/*
 * Catch-all API proxy that routes requests directly to the appropriate
 * backend service based on URL prefix, bypassing the Kong API gateway.
 *
 * Kong is only used for auth routes and internal endpoints.  All other
 * /api/ traffic is forwarded directly to the target microservice, which
 * validates the JWT itself via JWKS / userinfo fallback.  This avoids
 * hard dependencies on Kong's static JWT plugin configuration (which
 * only accepts tokens from the internal Keycloak issuer).
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
    process.env.NODE_ENV !== "development" &&
    process.env.OVERRIDE_API_PRODUCTION !== "true"
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
    if (
      process.env.DEBUG_AUTH_COOKIE &&
      process.env.NODE_ENV === "development"
    ) {
      const existingCookies = headers.get("cookie") || "";
      const debugCookie = `fastapiusersauth=${process.env.DEBUG_AUTH_COOKIE}`;
      headers.set(
        "cookie",
        existingCookies ? `${existingCookies}; ${debugCookie}` : debugCookie
      );
    }

    const response = await fetch(backendUrl, {
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
