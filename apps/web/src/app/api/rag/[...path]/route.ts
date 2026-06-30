import { NextRequest, NextResponse } from "next/server";
import { getCookieValue, refreshAuthCookies } from "@/lib/api/proxy";

// LANGCONNECT_URL is the canonical env var for the RAG service (see configs/.env)
const LANGCONNECT_URL =
  process.env.LANGCONNECT_URL ||
  process.env.RAG_SERVICE_URL ||
  "http://localhost:8083";

/**
 * Proxy to LangConnect RAG service.
 * Handles all HTTP methods including multipart/form-data file uploads.
 *
 * Maps /api/rag/<rest> → <RAG_SERVICE_URL>/<rest>
 *
 * IMPORTANT: Do NOT override Content-Type for POST requests —
 * multipart/form-data requires the browser-set boundary to pass through.
 */
async function proxyToRagService(
  request: NextRequest,
  path: string[]
): Promise<NextResponse> {
  try {
    const url = new URL(request.url);
    const targetPath = path.join("/");
    const targetUrl = new URL(`${LANGCONNECT_URL}/${targetPath}`);

    // Forward query params
    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.append(key, value);
    });

    const requestCookie = request.headers.get("cookie") || "";
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const requestBody = hasBody ? await request.arrayBuffer() : undefined;

    const buildHeaders = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ) => {
      // Forward all headers as-is so multipart boundary is preserved.
      // Do NOT override Content-Type here.
      const forwardedHeaders = new Headers(request.headers);
      forwardedHeaders.delete("host");
      forwardedHeaders.delete("content-length");

      const accessToken =
        accessTokenOverride || getCookieValue(cookieHeader, "access_token");
      if (accessToken && !request.headers.get("authorization")) {
        forwardedHeaders.set("authorization", `Bearer ${accessToken}`);
      }
      if (cookieHeader) {
        forwardedHeaders.set("cookie", cookieHeader);
      }

      return forwardedHeaders;
    };

    const execute = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ) =>
      fetch(targetUrl.toString(), {
        method: request.method,
        headers: buildHeaders(cookieHeader, accessTokenOverride),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...(hasBody ? ({ body: requestBody, duplex: "half" } as any) : {}),
      });

    let response = await execute(requestCookie);
    const refreshed =
      response.status === 401 ? await refreshAuthCookies(requestCookie) : null;
    if (refreshed?.accessToken) {
      response = await execute(refreshed.cookieHeader, refreshed.accessToken);
    }

    // Return 204 with no body
    if (response.status === 204) {
      const proxyResponse = new NextResponse(null, { status: 204 });
      for (const cookie of refreshed?.setCookies ?? []) {
        proxyResponse.headers.append("set-cookie", cookie);
      }
      return proxyResponse;
    }

    // Stream the response body back with the original status/headers
    const responseHeaders = new Headers(response.headers);
    const proxyResponse = new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
    for (const cookie of refreshed?.setCookies ?? []) {
      proxyResponse.headers.append("set-cookie", cookie);
    }
    return proxyResponse;
  } catch (error) {
    console.error("RAG service proxy error:", error);
    return NextResponse.json(
      { error: "RAG service proxy error" },
      { status: 500 }
    );
  }
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path);
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path);
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path);
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path);
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path);
}
