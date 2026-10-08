import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { NextRequest, NextResponse } from "next/server";
import { backendRequest, resolveBackendUrl } from "@/lib/api/http/server";

import { getCookieValue, getLanguageHeaders } from "@/lib/api/proxy";

// Non-admin MCP server list for the agent editor. Proxies to the agent-service
// admin endpoint (built-in tools server + configured external MCP servers). If
// that call fails (e.g. missing permission), fall back to the built-in server
// only so the editor still renders.
export async function GET(request: NextRequest) {
  const headers: HeadersInit = { ...getLanguageHeaders(request) };
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers["Cookie"] = cookie;
  if (authorization) {
    headers["Authorization"] = authorization;
  } else {
    // agent-service is bearer-token only and never reads cookies, so
    // forwarding the raw Cookie header above is not enough on its own --
    // the access_token has to be lifted into an explicit Authorization
    // header or every call here gets a bare 401 and silently falls back
    // to the built-in-only response below.
    const accessToken = cookie && getCookieValue(cookie, "access_token");
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`;
    }
  }

  try {
    const response = await backendRequest({
      ...toolsEndpoints.adminServers.backend,
      cache: "no-store",
      headers,
    });
    if (response.ok) {
      // Pass the ResponseModel envelope on untouched: the client unwraps it.
      const envelope = await response.json();
      if (Array.isArray(envelope?.data?.mcp_servers)) {
        return NextResponse.json(envelope);
      }
    }
  } catch {
    // fall through to the built-in-only fallback
  }

  return NextResponse.json({
    statusCode: 200,
    message: null,
    data: {
      mcp_servers: [
        {
          id: 1,
          name: "tools-service",
          description: "Built-in tools from tools-service",
          server_url: resolveBackendUrl(toolsEndpoints.mcp.backend).toString(),
          transport: "streamable_http",
        },
      ],
    },
    error: null,
  });
}
