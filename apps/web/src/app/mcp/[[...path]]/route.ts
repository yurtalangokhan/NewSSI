import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";

import { NextRequest, NextResponse } from "next/server";
import { backendRequest } from "@/lib/api/http/server";
import { stripTrustedContextHeaders } from "@/lib/api/proxySecurity";
import { appSettings } from "@/lib/settings";

type RouteContext = {
  params?: Promise<{
    path?: string[];
  }>;
};

const proxyHandler = async (
  request: NextRequest,
  context: RouteContext
): Promise<Response> => {
  if (!isProxyEnabled()) {
    return NextResponse.json(
      {
        message:
          "This MCP proxy is only available in development mode. In production, something else (e.g. nginx) should handle this.",
      },
      { status: 404 }
    );
  }

  try {
    const resolvedParams = context.params ? await context.params : undefined;
    const headers = buildForwardHeaders(request.headers);

    // Use the same public tools service as other web requests, forwarding auth.
    const response = await backendRequest({
      ...toolsEndpoints.mcpProxy(resolvedParams?.path).backend,
      query: request.nextUrl.searchParams,
      method: request.method,
      headers,
      signal: request.signal,
      // @ts-ignore - Required by undici for stream request bodies in Node runtime.
      duplex: "half",
      ...(supportsRequestBody(request) && request.body
        ? { body: request.body }
        : {}),
    });
    return response;
  } catch (error: unknown) {
    console.error("MCP Proxy error:", error);
    return NextResponse.json(
      {
        message: "MCP Proxy error",
        error:
          error instanceof Error ? error.message : "An unknown error occurred",
      },
      { status: 500 }
    );
  }
};

const isProxyEnabled = (): boolean => {
  if (appSettings.OVERRIDE_API_PRODUCTION) {
    return true;
  }
  return appSettings.NODE_ENV === "development";
};

const buildForwardHeaders = (requestHeaders: Headers): Headers => {
  const headers = new Headers(requestHeaders);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");
  stripTrustedContextHeaders(headers);
  return headers;
};

const supportsRequestBody = (request: NextRequest): boolean => {
  const method = request.method.toUpperCase();
  return method !== "GET" && method !== "HEAD";
};

type Handler = (
  request: NextRequest,
  context: RouteContext
) => Promise<Response>;

const handler: Handler = proxyHandler;

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const HEAD = handler;
export const OPTIONS = handler;
