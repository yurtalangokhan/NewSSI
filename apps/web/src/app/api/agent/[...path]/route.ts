import { NextRequest, NextResponse } from "next/server";
import { getCookieValue } from "@/lib/api/proxy";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getAgentServiceUrl } from "@/lib/env.server";

const AGENT_SERVICE_URL = getAgentServiceUrl();

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
    const targetUrl = buildServiceUrl(AGENT_SERVICE_URL, "agent", targetPath);

    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.append(key, value);
    });

    const requestCookie = request.headers.get("cookie") || "";
    const requestBody =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer();

    const buildHeaders = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ) => {
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("content-length");

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
      fetch(targetUrl, {
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
