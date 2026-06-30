import { NextRequest, NextResponse } from "next/server";
import { getCookieValue, refreshAuthCookies } from "@/lib/api/proxy";

const LANGCONNECT_URL = process.env.LANGCONNECT_URL || "http://localhost:8083";

export async function GET(request: NextRequest) {
  try {
    const requestCookie = request.headers.get("cookie") || "";
    const buildHeaders = (
      cookieHeader: string,
      accessTokenOverride?: string | null
    ) => {
      const forwardedHeaders = new Headers(request.headers);
      forwardedHeaders.delete("host");

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
      fetch(`${LANGCONNECT_URL}/datasources/knowledge-selector`, {
        headers: buildHeaders(cookieHeader, accessTokenOverride),
      });

    let response = await execute(requestCookie);
    const refreshed =
      response.status === 401 ? await refreshAuthCookies(requestCookie) : null;
    if (refreshed?.accessToken) {
      response = await execute(refreshed.cookieHeader, refreshed.accessToken);
    }

    const data = await response.json();
    const proxyResponse = NextResponse.json(data, { status: response.status });
    for (const cookie of refreshed?.setCookies ?? []) {
      proxyResponse.headers.append("set-cookie", cookie);
    }
    return proxyResponse;
  } catch (error) {
    return NextResponse.json(
      { document_processing: [], knowledge_graph: [] },
      { status: 500 }
    );
  }
}
