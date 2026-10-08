import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { NextRequest, NextResponse } from "next/server";
import { errorResponseFromException } from "@/lib/api/errorResponse";
import { throwTransportError } from "@/lib/api/errors";
import { getCookieValue } from "@/lib/api/proxy";
import { backendRequest } from "@/lib/api/http/server";
import { stripTrustedContextHeaders } from "@/lib/api/proxySecurity";

// LangGraph SDK proxy - maps SDK calls to agent-service endpoints
// SDK calls: /threads/search, /threads/{id}, /threads/{id}/state, etc.

async function proxyLangGraphRequest(
  request: NextRequest,
  method: "GET" | "POST" | "PATCH" | "DELETE"
) {
  const url = new URL(request.url);
  const path = url.pathname.replace("/api/langgraph", "");

  const requestCookie = request.headers.get("cookie") || "";
  const body =
    method === "GET" || method === "DELETE" ? undefined : await request.text();

  const buildHeaders = (
    cookieHeader: string,
    accessTokenOverride?: string | null
  ) => {
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("content-length");
    stripTrustedContextHeaders(headers);
    headers.set(
      "Content-Type",
      request.headers.get("content-type") || "application/json"
    );

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

  const execute = (cookieHeader: string, accessTokenOverride?: string | null) =>
    backendRequest({
      ...agentsEndpoints.agentProxyTarget(path).backend,
      query: method === "GET" ? url.searchParams : undefined,
      method,
      body,
      headers: buildHeaders(cookieHeader, accessTokenOverride),
    }).catch((error: unknown) => throwTransportError(error, request));

  const response = await execute(requestCookie);

  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("set-cookie");

  if (response.headers.get("content-type")?.includes("text/event-stream")) {
    const proxyResponse = new NextResponse(response.body, {
      status: response.status,
      headers: {
        ...Object.fromEntries(responseHeaders.entries()),
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
    return proxyResponse;
  }

  const proxyResponse = new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
  return proxyResponse;
}

export async function GET(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "GET");
  } catch (error) {
    console.error("LangGraph proxy GET error:", error);
    return errorResponseFromException(error, request);
  }
}

export async function POST(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "POST");
  } catch (error) {
    console.error("LangGraph proxy POST error:", error);
    return errorResponseFromException(error, request);
  }
}

export async function PATCH(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "PATCH");
  } catch (error) {
    console.error("LangGraph proxy PATCH error:", error);
    return errorResponseFromException(error, request);
  }
}

export async function DELETE(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "DELETE");
  } catch (error) {
    console.error("LangGraph proxy DELETE error:", error);
    return errorResponseFromException(error, request);
  }
}
