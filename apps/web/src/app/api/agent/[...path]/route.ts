import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { NextRequest, NextResponse } from "next/server";
import { getCookieValue } from "@/lib/api/proxy";
import { backendRequest } from "@/lib/api/http/server";
import { stripTrustedContextHeaders } from "@/lib/api/proxySecurity";

const MAX_PROXY_BODY_BYTES = 200 * 1024 * 1024;

/**
 * Generic proxy to agent-service for all HTTP methods.
 * Maps /api/agent/<rest> through the domain endpoint to the configured service.
 */
async function proxyToAgentService(
  request: NextRequest,
  path: string[]
): Promise<NextResponse> {
  try {
    const declaredLength = request.headers.get("content-length");
    if (declaredLength && Number(declaredLength) > MAX_PROXY_BODY_BYTES) {
      return NextResponse.json({ error: "Payload too large" }, { status: 413 });
    }

    const url = new URL(request.url);
    const targetPath = path.join("/");

    const requestCookie = request.headers.get("cookie") || "";
    // Streamed, not buffered: request.body is a ReadableStream forwarded
    // straight through to agent-service.
    const requestBody =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : request.body;

    const buildHeaders = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ) => {
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("content-length");
      stripTrustedContextHeaders(headers);

      const accessToken =
        accessTokenOverride || getCookieValue(cookieHeader, "access_token");
      if (accessToken && !request.headers.get("authorization")) {
        headers.set("authorization", `Bearer ${accessToken}`);
      }
      if (cookieHeader) {
        headers.set("cookie", cookieHeader);
      }

      return headers;
    };

    const execute = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ) =>
      backendRequest({
        ...agentsEndpoints.agentProxyTarget(targetPath).backend,
        query: url.searchParams,
        method: request.method,
        headers: buildHeaders(cookieHeader, accessTokenOverride),
        body: requestBody,
        signal: request.signal,
        redirect: "manual",
        // @ts-ignore - Required by undici for stream request bodies in Node runtime.
        duplex: "half",
      });

    const response = await execute(requestCookie);

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
