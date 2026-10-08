// ============================================================================
// Tools domain - endpoint descriptors and path builders
// Tools domain owns: built-in tools, server tools, MCP servers, MCP OAuth,
// OpenAPI tools, snapshots, status, execution, playground operations
// ============================================================================

// ============================================================================
// Path constants
// ============================================================================

// Code interpreter endpoints

// ============================================================================
// Endpoint descriptors
// ============================================================================

// ============================================================================
// Path builder functions
// ============================================================================

import { MCPServerStatus } from "@/lib/tools/interfaces";

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const toolsEndpoints = {
  deleteMcpServer: (serverId: string | number) =>
    ({
      method: "DELETE",
      browserPath: `/api/admin/mcp/server/${serverId}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/server/${serverId}`,
      },
    }) as const,
  getMcpServer: (serverId: string | number) =>
    ({
      method: "GET",
      browserPath: `/api/admin/mcp/server/${serverId}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/server/${serverId}`,
      },
    }) as const,
  updateMcpServer: (serverId: string | number) =>
    ({
      method: "PATCH",
      browserPath: `/api/admin/mcp/server/${serverId}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/server/${serverId}`,
      },
    }) as const,
  updateMcpServerStatus: (
    serverId: string | number,
    status?: MCPServerStatus
  ) =>
    ({
      method: "PATCH",
      browserPath: `/api/admin/mcp/server/${serverId}/status${
        status === undefined ? "" : `?status=${status}`
      }`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/server/${serverId}/status`,
      },
    }) as const,
  getMcpServerSnapshots: (
    serverId: string | number,
    source: "db" | "mcp" = "db"
  ) =>
    ({
      method: "GET",
      browserPath: `/api/admin/mcp/server/${encodeURIComponent(
        String(serverId)
      )}/tools/snapshots?source=${source}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/server/${serverId}/tools/snapshots`,
      },
    }) as const,
  // Tools last synced from a server: a database read behind `mcp_tool:read`,
  // unlike `getMcpServerSnapshots`, which discovers live and needs `sync`.
  getMcpServerTools: (serverId: string | number) =>
    ({
      method: "GET",
      browserPath: `/api/admin/mcp/servers/${encodeURIComponent(
        String(serverId)
      )}/tools`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/servers/${serverId}/tools`,
      },
    }) as const,
  refreshMcpServerTools: (serverId: number, source: "mcp" | "db") =>
    ({
      method: "GET",
      browserPath: `/api/admin/mcp/server/${serverId}/tools/snapshots?source=${source}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/server/${serverId}/tools/snapshots`,
      },
    }) as const,
  getMcpServerDetails: (serverId: string) =>
    ({
      method: "GET",
      browserPath: `/api/admin/mcp/servers/${encodeURIComponent(serverId)}`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/servers/${serverId}`,
      },
    }) as const,
  oauthCallback: (code?: string, state?: string) =>
    ({
      method: "POST",
      browserPath: `/api/mcp/oauth/callback?code=${encodeURIComponent(
        code ?? ""
      )}&state=${encodeURIComponent(state ?? "")}`,
      backend: { service: "agent", path: "/api/v1/mcp/oauth/callback" },
    }) as const,
  listBuiltInTools: {
    method: "GET",
    browserPath: "/api/proxy/mcp/tools-builtin",
    backend: { service: "agent", path: "/api/v1/proxy/mcp/tools-builtin" },
  },
  adminServer: {
    method: "POST",
    browserPath: "/api/admin/mcp/server",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server" },
  },
  validateMcpServer: {
    method: "POST",
    browserPath: "/api/admin/mcp/server/validate",
    backend: { service: "agent", path: "/api/v1/admin/mcp/server/validate" },
  },
  adminServers: {
    method: "GET",
    browserPath: "/api/admin/mcp/servers",
    backend: { service: "agent", path: "/api/v1/admin/mcp/servers" },
  },
  adminServersCreate: {
    method: "POST",
    browserPath: "/api/admin/mcp/servers/create",
    backend: { service: "agent", path: "/api/v1/admin/mcp/servers/create" },
  },
  disconnectMcpServer: (serverId: string | number) =>
    ({
      method: "DELETE",
      browserPath: `/api/admin/mcp/servers/${encodeURIComponent(
        String(serverId)
      )}/connect`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/servers/${encodeURIComponent(
          String(serverId)
        )}/connect`,
      },
    }) as const,
  connectMcpServer: (serverId: string | number) =>
    ({
      method: "POST",
      browserPath: `/api/admin/mcp/servers/${encodeURIComponent(
        String(serverId)
      )}/connect`,
      backend: {
        service: "agent",
        path: `/api/v1/admin/mcp/servers/${encodeURIComponent(
          String(serverId)
        )}/connect`,
      },
    }) as const,
  adminToolStatus: {
    method: "PATCH",
    browserPath: "/api/admin/tool/status",
    backend: { service: "agent", path: "/api/v1/admin/tool/status" },
  },
  openapiTools: { browserPath: "/api/tool/openapi" },
  tool: { browserPath: "/api/tool" },
  codeInterpreterHealth: { browserPath: "/api/admin/code-interpreter/health" },
  codeInterpreter: { browserPath: "/api/admin/code-interpreter" },
  mcpOauthConnect: { browserPath: "/api/admin/mcp/oauth/connect" },
  mcp: { backend: { service: "tools", path: "/mcp" } },
  mcpProxy: (
    segments: string[] = []
  ): { backend: import("@/lib/api/http/types").BackendTarget } => ({
    backend: {
      service: "tools" as const,
      path: `/mcp${segments
        .filter(Boolean)
        .map((segment) => `/${encodeURIComponent(segment)}`)
        .join("")}`,
    },
  }),
  builtInToolExecute: (): { browserPath: string } => {
    return { browserPath: "/api/proxy/mcp/execute" };
  },
  validateToolDefinition: { browserPath: "/api/admin/tool/custom/validate" },
  createCustomTool: { browserPath: "/api/admin/tool/custom" },
  updateCustomTool: (toolId: number): { browserPath: string } => {
    return { browserPath: `/api/admin/tool/custom/${toolId}` };
  },
  executeMcpServerTool: (
    serverId: number,
    toolName: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/admin/mcp/server/${serverId}/tools/${encodeURIComponent(
        toolName
      )}/execute`,
    };
  },
  executeBuiltInTool: (value0: string): { browserPath: string } => {
    return { browserPath: `/api/mail-configs/${value0}/send` };
  },
  fetchMcpServersForAgent: { browserPath: "/api/mcp/servers" },
  mcpStoredSnapshotsKey: (serverId: number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/mcp/servers/${serverId}/tools`,
    };
  },
} as const;
