import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { parseResponseModel } from "@/lib/api/responseModel";

import { getCookieValue, getLanguageHeaders } from "@/lib/api/proxy";
import { NextRequest, NextResponse } from "next/server";

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
    const serversRes = await backendRequest({
      ...toolsEndpoints.adminServers.backend,
      cache: "no-store",
      headers,
    });
    if (!serversRes.ok) return [];
    const serversData = await parseResponseModel<{
      mcp_servers?: McpServerSummary[];
    }>(serversRes);
    const servers: McpServerSummary[] = Array.isArray(serversData?.mcp_servers)
      ? serversData.mcp_servers
      : [];

    const externalConnected = servers.filter(
      (s) => s.id !== 1 && (s.status ?? "CONNECTED") === "CONNECTED"
    );

    const perServer = await Promise.all(
      externalConnected.map(async (server) => {
        try {
          const res = await backendRequest({
            ...toolsEndpoints.getMcpServerTools(server.id).backend,
            cache: "no-store",
            headers,
          });
          if (!res.ok) {
            console.warn(
              `Could not read tools of MCP server ${server.id} (${res.status})`
            );
            return [];
          }
          const snapshots = await parseResponseModel<unknown>(res);
          return Array.isArray(snapshots) ? snapshots : [];
        } catch (error) {
          console.warn(
            `Could not read tools of MCP server ${server.id}`,
            error
          );
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
    if (authorization) {
      headers["Authorization"] = authorization;
    } else {
      // agent-service is bearer-token only and never reads cookies, so
      // forwarding the raw Cookie header above is not enough on its own --
      // without this, every call below (built-in tools, the external
      // server list, and each server's tool snapshots) got a bare 401,
      // and fetchExternalMcpTools() swallows that silently.
      const accessToken = cookie && getCookieValue(cookie, "access_token");
      if (accessToken) {
        headers["Authorization"] = `Bearer ${accessToken}`;
      }
    }

    const [builtInRes, externalTools] = await Promise.all([
      backendRequest({
        ...toolsEndpoints.listBuiltInTools.backend,
        cache: "no-store",
        headers,
      }),
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
