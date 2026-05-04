import { NextRequest, NextResponse } from "next/server";

const AGENT_SERVICE_URL =
  process.env.AGENT_SERVICE_URL ||
  process.env.INTERNAL_URL ||
  "http://localhost:8123";

/**
 * Generic proxy to agent-service for all HTTP methods.
 * Maps /api/agent/<rest> → <AGENT_SERVICE_URL>/<rest>
 */
async function proxyToAgentService(
  request: NextRequest,
  path: string[]
): Promise<NextResponse> {
  try {
    const url = new URL(request.url);
    const targetPath = path.join("/");
    const targetUrl = new URL(`${AGENT_SERVICE_URL}/${targetPath}`);

    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.append(key, value);
    });

    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("content-length");

    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : request.body,
      signal: request.signal,
      redirect: "manual",
      // @ts-ignore - Required by undici for stream request bodies in Node runtime.
      duplex: "half",
    });

    const setCookies =
      // @ts-ignore - undici provides getSetCookie in Node runtime.
      response.headers.getSetCookie?.() ??
      (response.headers.get("set-cookie")
        ? [response.headers.get("set-cookie")]
        : []);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("set-cookie");

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
  } catch (error) {
    console.error("Agent service proxy error:", error);
    return NextResponse.json(
      { error: "Agent service proxy error" },
      { status: 500 }
    );
  }
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}
