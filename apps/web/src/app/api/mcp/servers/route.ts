import { NextRequest, NextResponse } from "next/server";
import { getInternalUrl, getToolsServiceUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";

const INTERNAL_URL = getInternalUrl();
const TOOLS_SERVICE_URL = getToolsServiceUrl();

// Non-admin MCP server list for the agent editor. Proxies to the agent-service
// admin endpoint (built-in tools server + configured external MCP servers). If
// that call fails (e.g. missing permission), fall back to the built-in server
// only so the editor still renders.
export async function GET(request: NextRequest) {
  const headers: HeadersInit = { ...getLanguageHeaders(request) };
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers["Cookie"] = cookie;
  if (authorization) headers["Authorization"] = authorization;

  try {
    const response = await fetch(
      buildServiceUrl(INTERNAL_URL, "agent", "/admin/mcp/servers").toString(),
      { cache: "no-store", headers }
    );
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data?.mcp_servers)) {
        return NextResponse.json(data);
      }
    }
  } catch {
    // fall through to the built-in-only fallback
  }

  return NextResponse.json({
    mcp_servers: [
      {
        id: 1,
        name: "tools-service",
        description: "Built-in tools from tools-service",
        server_url: TOOLS_SERVICE_URL,
        transport: "streamable_http",
      },
    ],
  });
}
