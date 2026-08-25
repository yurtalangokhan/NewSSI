/**
 * Service layer for MCP (Model Context Protocol) related API calls
 */

import {
  MCPServer,
  MCPServerCreateRequest,
  MCPServerUpdateRequest,
  MCPServerStatus,
  ApiResponse,
  ToolSnapshot,
  MCPAuthenticationType,
  MCPAuthenticationPerformer,
} from "@/lib/tools/interfaces";
import i18n from "@/i18n/config";
import { getErrorMsg } from "@/lib/fetchUtils";
import { authenticatedFetch } from "@/lib/fetcher";
import {
  createIdempotencyKey,
  withIdempotencyKey,
} from "@/lib/api/idempotency";
export interface ToolStatusUpdateRequest {
  tool_ids: number[];
  enabled: boolean;
}

export interface ToolStatusUpdateResponse {
  updated_count: number;
  tool_ids: number[];
}

/**
 * Delete an MCP server
 */
export async function deleteMCPServer(serverId: number): Promise<void> {
  const response = await fetch(`/api/admin/mcp/server/${serverId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to delete MCP server");
  }
}

/**
 * This performs actual discovery from the MCP server and syncs to DB
 */
export async function refreshMCPServerTools(
  serverId: number
): Promise<ToolSnapshot[]> {
  // Discovers tools from MCP server, upserts to DB, and returns ToolSnapshot format
  const response = await fetch(
    `/api/admin/mcp/server/${serverId}/tools/snapshots?source=mcp`
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to refresh tools");
  }

  return await response.json();
}

/**
 * Update status (enable/disable) for one or more tools
 */
export async function updateToolsStatus(
  toolIds: number[],
  enabled: boolean
): Promise<ToolStatusUpdateResponse> {
  const response = await fetch("/api/admin/tool/status", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tool_ids: toolIds,
      enabled: enabled,
    } as ToolStatusUpdateRequest),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to update tool status");
  }

  return await response.json();
}

/**
 * Update status for a single tool
 */
export async function updateToolStatus(
  toolId: number,
  enabled: boolean
): Promise<ToolStatusUpdateResponse> {
  return updateToolsStatus([toolId], enabled);
}

/**
 * Disable all tools for a specific MCP server
 */
export async function disableAllServerTools(
  toolIds: number[]
): Promise<ToolStatusUpdateResponse> {
  return updateToolsStatus(toolIds, false);
}

/**
 * Create a new MCP server with basic information
 */
export async function createMCPServer(
  data: MCPServerCreateRequest
): Promise<MCPServer> {
  const response = await fetch("/api/admin/mcp/server", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to create MCP server");
  }

  return await response.json();
}

/**
 * Update an existing MCP server
 */
export async function updateMCPServer(
  serverId: number,
  data: MCPServerUpdateRequest
): Promise<MCPServer> {
  const response = await fetch(`/api/admin/mcp/server/${serverId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to update MCP server");
  }

  return await response.json();
}

/**
 * Update the status of an MCP server
 */
export async function updateMCPServerStatus(
  serverId: number,
  status: MCPServerStatus
): Promise<void> {
  const response = await fetch(
    `/api/admin/mcp/server/${serverId}/status?status=${status}`,
    {
      method: "PATCH",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to update MCP server status");
  }
}

interface UpsertMCPServerResponse {
  server_id: number;
  server_name: string;
  server_url: string;
  auth_type: string;
  auth_performer: string;
  is_authenticated: boolean;
}

export async function upsertMCPServer(serverData: {
  name: string;
  description?: string;
  server_url: string;
  transport: string;
  auth_type: MCPAuthenticationType;
  auth_performer: MCPAuthenticationPerformer;
  api_token?: string;
  oauth_client_id?: string;
  oauth_client_secret?: string;
  auth_template?: any;
  admin_credentials?: Record<string, string>;
  existing_server_id?: number;
}): Promise<ApiResponse<UpsertMCPServerResponse>> {
  try {
    const response = await fetch("/api/admin/mcp/servers/create", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(serverData),
    });

    if (!response.ok) {
      const errorDetail = (await getErrorMsg(response)) ?? "Unknown error";
      return {
        data: null,
        error: `Failed to create MCP server: ${errorDetail}`,
      };
    }

    const result: UpsertMCPServerResponse = await response.json();
    return { data: result, error: null };
  } catch (error) {
    console.error("Error creating MCP server:", error);
    return { data: null, error: `Error creating MCP server: ${error}` };
  }
}

export interface BuiltInTool {
  name: string;
  description: string;
  input_schema: Record<string, any>;
}

export interface BuiltInToolsResponse {
  tools: BuiltInTool[];
  error?: string;
}

export interface ToolExecuteResponse {
  result: any;
  error?: string;
}

/**
 * Get list of available tools from the built-in tools-service
 */
export async function getBuiltInTools(): Promise<BuiltInToolsResponse> {
  const currentLang = i18n.language || "en";
  const response = await fetch("/api/proxy/mcp/tools-builtin", {
    headers: {
      "X-Language": currentLang,
      "Accept-Language": currentLang,
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    return { tools: [], error: errorText || "Failed to fetch built-in tools" };
  }

  return await response.json();
}

/**
 * Execute a tool on the built-in tools-service
 */
export async function executeBuiltInTool(
  toolName: string,
  arguments_: Record<string, any> = {}
): Promise<ToolExecuteResponse> {
  if (toolName === "send_email") {
    const mailConfigId = String(arguments_.mail_config_id || "").trim();
    if (!mailConfigId) {
      return { result: null, error: "Mail config is required for send_email" };
    }
    const { mail_config_id: _mailConfigId, ...payload } = arguments_;
    const normalizeRecipients = (value: unknown) => {
      if (Array.isArray(value)) return value;
      if (typeof value === "string") {
        return value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
      }
      return [];
    };
    payload.to = normalizeRecipients(payload.to);
    payload.cc = normalizeRecipients(payload.cc);
    payload.bcc = normalizeRecipients(payload.bcc);
    const response = await authenticatedFetch(
      `/api/mail-configs/${encodeURIComponent(mailConfigId)}/send`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return { result: null, error: errorText || "Failed to send email" };
    }

    const data = await response.json();
    return { result: data, error: data.success ? undefined : data.message };
  }

  const currentLang = i18n.language || "en";
  const response = await fetch("/api/proxy/mcp/execute", {
    method: "POST",
    headers: withIdempotencyKey(
      {
        "Content-Type": "application/json",
        "X-Language": currentLang,
      },
      createIdempotencyKey()
    ),
    body: JSON.stringify({
      tool_name: toolName,
      arguments: arguments_,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    return { result: null, error: errorText || "Failed to execute tool" };
  }

  return await response.json();
}
