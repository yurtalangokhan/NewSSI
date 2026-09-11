import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

interface BuiltInTool {
  name?: string;
  description?: string;
}

interface McpServerSummary {
  id: number;
  status?: string;
}

// Tools from connected external MCP servers, tagged with their mcp_server_id so
// the agent editor can group them per server. Failures degrade to an empty list
// (built-in tools still render).
async function fetchExternalMcpTools(
  headers: HeadersInit
): Promise<Record<string, unknown>[]> {
  try {
    const serversRes = await fetch(
      buildServiceUrl(INTERNAL_URL, "agent", "/admin/mcp/servers").toString(),
      { cache: "no-store", headers }
    );
    if (!serversRes.ok) return [];
    const serversData = await serversRes.json();
    const servers: McpServerSummary[] = Array.isArray(serversData?.mcp_servers)
      ? serversData.mcp_servers
      : [];

    const externalConnected = servers.filter(
      (s) => s.id !== 1 && (s.status ?? "CONNECTED") === "CONNECTED"
    );

    const perServer = await Promise.all(
      externalConnected.map(async (server) => {
        try {
          const toolsUrl = buildServiceUrl(
            INTERNAL_URL,
            "agent",
            `/admin/mcp/server/${server.id}/tools/snapshots`
          );
          toolsUrl.searchParams.set("source", "db");
          const res = await fetch(toolsUrl.toString(), {
            cache: "no-store",
            headers,
          });
          if (!res.ok) return [];
          const snapshots = await res.json();
          return Array.isArray(snapshots) ? snapshots : [];
        } catch {
          return [];
        }
      })
    );
    return perServer.flat();
  } catch {
    return [];
  }
}

export async function GET(request: NextRequest) {
  try {
    const headers: HeadersInit = { ...getLanguageHeaders(request) };
    const cookie = request.headers.get("cookie");
    const authorization = request.headers.get("authorization");
    if (cookie) headers["Cookie"] = cookie;
    if (authorization) headers["Authorization"] = authorization;

    const [builtInRes, externalTools] = await Promise.all([
      fetch(
        buildServiceUrl(INTERNAL_URL, "agent", "/mcp/tools-builtin").toString(),
        { cache: "no-store", headers }
      ),
      fetchExternalMcpTools(headers),
    ]);

    const builtInData = builtInRes.ok ? await builtInRes.json() : { tools: [] };
    const builtIn: BuiltInTool[] = Array.isArray(builtInData?.tools)
      ? builtInData.tools
      : [];

    const builtInSnapshots = builtIn.map((tool, index) => ({
      id: index + 1,
      name: tool.name || "",
      display_name: (tool.name || "").replace(/[_-]/g, " "),
      description: tool.description || "",
      definition: null,
      custom_headers: [],
      in_code_tool_id: tool.name || null,
      passthrough_auth: false,
      oauth_config_id: null,
      oauth_config_name: null,
      mcp_server_id: null,
      user_id: null,
      enabled: true,
      chat_selectable: true,
      agent_creation_selectable: true,
      default_enabled: false,
    }));

    return NextResponse.json([...builtInSnapshots, ...externalTools]);
  } catch {
    return NextResponse.json([]);
  }
}
