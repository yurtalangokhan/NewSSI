import { NextRequest, NextResponse } from "next/server";

// LANGCONNECT_URL is the canonical env var for the RAG service (see configs/.env)
const LANGCONNECT_URL =
  process.env.LANGCONNECT_URL ||
  process.env.RAG_SERVICE_URL ||
  "http://localhost:8083";

// Matches INTERNAL_SERVICE_TOKEN in legacy/langconnect/langconnect/auth.py
const INTERNAL_SERVICE_TOKEN =
  process.env.INTERNAL_SERVICE_TOKEN || "internal-service-key-2026";

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

    const hasBody =
      request.method !== "GET" && request.method !== "HEAD";

    // Forward all headers as-is so multipart boundary is preserved.
    // Do NOT override Content-Type here.
    const forwardedHeaders = new Headers(request.headers);
    // Remove host header to avoid upstream confusion
    forwardedHeaders.delete("host");
    // Authenticate as internal service so RAG auth passes regardless of VALID_API_KEYS
    forwardedHeaders.set("X-Internal-Service-Token", INTERNAL_SERVICE_TOKEN);

    const response = await fetch(targetUrl.toString(), {
      method: request.method,
      headers: forwardedHeaders,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...(hasBody ? { body: request.body, duplex: "half" } as any : {}),
    });

    // Return 204 with no body
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    // Stream the response body back with the original status/headers
    const responseHeaders = new Headers(response.headers);
    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
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
