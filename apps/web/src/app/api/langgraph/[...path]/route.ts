import { NextRequest, NextResponse } from "next/server";
import { getCookieValue, refreshAuthCookies } from "@/lib/api/proxy";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

// LangGraph SDK proxy - maps SDK calls to agent-service endpoints
// SDK calls: /threads/search, /threads/{id}, /threads/{id}/state, etc.

async function proxyLangGraphRequest(
  request: NextRequest,
  method: "GET" | "POST" | "PATCH" | "DELETE"
) {
  const url = new URL(request.url);
  const path = url.pathname.replace("/api/langgraph", "");
  const targetUrl = new URL(`${INTERNAL_URL}${path}`);
  if (method === "GET") {
    targetUrl.search = url.search;
  }

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
    fetch(targetUrl.toString(), {
      method,
      body,
      headers: buildHeaders(cookieHeader, accessTokenOverride),
    });

  let response = await execute(requestCookie);
  const refreshed =
    response.status === 401 ? await refreshAuthCookies(requestCookie) : null;
  if (refreshed?.accessToken) {
    response = await execute(refreshed.cookieHeader, refreshed.accessToken);
  }

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
    for (const cookie of refreshed?.setCookies ?? []) {
      proxyResponse.headers.append("set-cookie", cookie);
    }
    return proxyResponse;
  }

  const proxyResponse = new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
  for (const cookie of refreshed?.setCookies ?? []) {
    proxyResponse.headers.append("set-cookie", cookie);
  }
  return proxyResponse;
}

export async function GET(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "GET");
  } catch (error) {
    console.error("LangGraph proxy GET error:", error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "POST");
  } catch (error) {
    console.error("LangGraph proxy POST error:", error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "PATCH");
  } catch (error) {
    console.error("LangGraph proxy PATCH error:", error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    return await proxyLangGraphRequest(request, "DELETE");
  } catch (error) {
    console.error("LangGraph proxy DELETE error:", error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}
