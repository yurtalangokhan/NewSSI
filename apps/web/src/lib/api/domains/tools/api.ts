import { parseResponseModel } from "@/lib/api/responseModel";
import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";

/**
 * Tools domain client
 * Uses apiRequest for all HTTP operations
 */
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

import type {
  MCPServer,
  MCPServerCreateRequest,
  MCPServerUpdateRequest,
  MCPServersResponse,
  ToolSnapshot,
} from "@/lib/tools/interfaces";

// ============================================================================
// MCP Servers (admin)
// ============================================================================

async function requestAgentToolsJson<T>(path: string): Promise<T> {
  return apiRequest(path, {
    headers: { "X-Language": i18n.language },
  }).then(parseResponseModel<T>);
}

async function requestToolsJson<T>(path: string): Promise<T> {
  const res = await apiRequest(path);
  if (!res.ok) {
    throw new FetchError(
      `Tools API request failed (Status: ${res.status})`,
      res.status,
      res
    );
  }
  const result = await parseJsonResponse<T>(res);
  if (result === undefined) {
    throw new Error("Tools API request returned empty response");
  }
  return result;
}

export function fetchMcpServers(): Promise<MCPServersResponse> {
  return requestAgentToolsJson<MCPServersResponse>(
    toolsEndpoints.adminServers.browserPath
  );
}

export function fetchMcpServerAdminDetail(
  serverId: number | string
): Promise<MCPServer> {
  return requestAgentToolsJson<MCPServer>(
    toolsEndpoints.getMcpServerDetails(String(serverId)).browserPath
  );
}

/**
 * Get tool snapshots from DB for a server
 */
export function fetchMcpServerToolsSnapshots(
  serverId: number | string
): Promise<ToolSnapshot[]> {
  return requestAgentToolsJson<ToolSnapshot[]>(
    toolsEndpoints.getMcpServerTools(serverId).browserPath
  );
}

/**
 * Refresh tools from MCP server and sync to DB
 */

// ============================================================================
// Tool Status
// ============================================================================

export interface ToolStatusUpdateRequest {
  tool_ids: number[];
  enabled: boolean;
}

export interface ToolStatusUpdateResponse {
  updated_count: number;
  tool_ids: number[];
}

export async function updateToolsStatus(
  toolIds: number[],
  enabled: boolean
): Promise<ToolStatusUpdateResponse> {
  const res = await requestAgentPayload(
    toolsEndpoints.adminToolStatus.browserPath,
    {
      method: toolsEndpoints.adminToolStatus.method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tool_ids: toolIds,
        enabled,
      } as ToolStatusUpdateRequest),
    }
  );
  if (!res.ok) {
    const error = await parseApiErrorResponse(res);
    throw new FetchError(error.userMessage, res.status, error.raw, error);
  }
  return parseJsonResponse<ToolStatusUpdateResponse>(
    res
  ) as Promise<ToolStatusUpdateResponse>;
}

export async function updateToolStatus(
  toolId: number,
  enabled: boolean
): Promise<ToolStatusUpdateResponse> {
  return updateToolsStatus([toolId], enabled);
}

// ============================================================================
// OpenAPI Tools
// ============================================================================

export function fetchOpenApiTools(): Promise<ToolSnapshot[]> {
  return requestToolsJson<ToolSnapshot[]>(
    toolsEndpoints.openapiTools.browserPath
  );
}

// ============================================================================
// Built-in Tools
// ============================================================================

export interface BuiltInTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface BuiltInToolsResponse {
  tools: BuiltInTool[];
  error?: string;
}

export interface ToolExecuteResponse {
  result: unknown;
  error?: string;
}

/**
 * Get list of all available tools (built-in + dynamic) for the current user.
 * Used by useAvailableTools hook with language-keyed SWR caching.
 */
export async function fetchAvailableTools(): Promise<ToolSnapshot[]> {
  const currentLang = i18n.language || "en";
  const res = await apiRequest(toolsEndpoints.tool.browserPath, {
    headers: {
      "X-Language": currentLang,
      "Accept-Language": currentLang,
    },
  });
  if (!res.ok) {
    throw new FetchError(
      `Failed to fetch tools (${res.status})`,
      res.status,
      res
    );
  }
  const result = await parseJsonResponse<ToolSnapshot[]>(res);
  return result ?? [];
}

/**
 * Get list of available tools from the built-in tools-service
 */
async function requestAgentPayload(
  ...args: Parameters<typeof apiRequest>
): Promise<Response> {
  return apiRequest(...args).then(agentServicePayloadResponse);
}

export async function fetchBuiltInTools(): Promise<BuiltInToolsResponse> {
  const currentLang = i18n.language || "en";
  const res = await requestAgentPayload(
    toolsEndpoints.listBuiltInTools.browserPath,
    {
      headers: {
        "X-Language": currentLang,
        "Accept-Language": currentLang,
      },
    }
  );
  if (!res.ok) {
    const err = await res.text();
    return { tools: [], error: err || "Failed to fetch built-in tools" };
  }
  return parseJsonResponse<BuiltInToolsResponse>(
    res
  ) as Promise<BuiltInToolsResponse>;
}

/**
 * Execute a tool on the built-in tools-service
 */
export async function executeBuiltInTool(
  toolName: string,
  arguments_: Record<string, unknown> = {}
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
    const res = await requestAgentPayload(
      toolsEndpoints.executeBuiltInTool(encodeURIComponent(mailConfigId))
        .browserPath,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) {
      const err = await res.text();
      return { result: null, error: err || "Failed to send email" };
    }
    const data = await res.json();
    return { result: data, error: data.success ? undefined : data.message };
  }

  const currentLang = i18n.language || "en";
  const res = await requestAgentPayload(
    toolsEndpoints.builtInToolExecute().browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Language": currentLang,
      },
      body: JSON.stringify({
        tool_name: toolName,
        arguments: arguments_,
      }),
    }
  );
  if (!res.ok) {
    const err = await res.text();
    return { result: null, error: err || "Failed to execute tool" };
  }
  return parseJsonResponse<ToolExecuteResponse>(
    res
  ) as Promise<ToolExecuteResponse>;
}

// ============================================================================
// OAuth
// ============================================================================

// ============================================================================
// MCP Servers (non-admin / agent editor)
// ============================================================================

export function fetchMcpServersForAgent(): Promise<MCPServersResponse> {
  return requestAgentToolsJson<MCPServersResponse>(
    toolsEndpoints.fetchMcpServersForAgent.browserPath
  );
}

// ============================================================================
// Code Interpreter
// ============================================================================

export interface CodeInterpreterHealth {
  healthy: boolean;
}

export interface CodeInterpreterStatus {
  enabled: boolean;
}

export function fetchCodeInterpreterHealth(): Promise<CodeInterpreterHealth> {
  return requestToolsJson<CodeInterpreterHealth>(
    toolsEndpoints.codeInterpreterHealth.browserPath
  );
}

export function fetchCodeInterpreterStatus(): Promise<CodeInterpreterStatus> {
  return requestToolsJson<CodeInterpreterStatus>(
    toolsEndpoints.codeInterpreter.browserPath
  );
}

import { MethodSpec, ApiResponse } from "@/lib/tools/interfaces";
import { getErrorMsg } from "@/lib/fetchUtils";

import { ToolUpdatePayload } from "@/lib/api/domains/tools/openapi-types";

export async function validateToolDefinition(toolData: {
  definition: Record<string, unknown>;
}): Promise<ApiResponse<MethodSpec[]>> {
  try {
    const response = await apiRequest(
      toolsEndpoints.validateToolDefinition.browserPath,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(toolData),
      }
    );

    if (!response.ok) {
      const errorDetail = (await getErrorMsg(response)) ?? "Unknown error";
      return { data: null, error: errorDetail };
    }

    const responseJson = await response.json();
    return { data: responseJson.methods, error: null };
  } catch (error) {
    console.error("Error validating tool:", error);
    return { data: null, error: "Unexpected error validating tool definition" };
  }
}

export async function createCustomTool(toolData: {
  name: string;
  description?: string;
  definition: Record<string, unknown>;
  custom_headers: { key: string; value: string }[];
  passthrough_auth: boolean;
}): Promise<ApiResponse<ToolSnapshot>> {
  try {
    const response = await apiRequest(
      toolsEndpoints.createCustomTool.browserPath,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(toolData),
      }
    );

    if (!response.ok) {
      const errorDetail = (await getErrorMsg(response)) ?? "Unknown error";
      return { data: null, error: `Failed to create tool: ${errorDetail}` };
    }

    const tool: ToolSnapshot = await response.json();
    return { data: tool, error: null };
  } catch (error) {
    console.error("Error creating tool:", error);
    return { data: null, error: "Error creating tool" };
  }
}

export async function updateCustomTool(
  toolId: number,
  toolData: ToolUpdatePayload
): Promise<ApiResponse<ToolSnapshot>> {
  try {
    const response = await apiRequest(
      toolsEndpoints.updateCustomTool(toolId).browserPath,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(toolData),
      }
    );

    if (!response.ok) {
      const errorDetail = (await getErrorMsg(response)) ?? "Unknown error";
      return { data: null, error: `Failed to update tool: ${errorDetail}` };
    }

    const updatedTool: ToolSnapshot = await response.json();
    return { data: updatedTool, error: null };
  } catch (error) {
    console.error("Error updating tool:", error);
    return { data: null, error: "Error updating tool" };
  }
}

export async function deleteCustomTool(
  toolId: number
): Promise<ApiResponse<boolean>> {
  try {
    const response = await apiRequest(
      toolsEndpoints.updateCustomTool(toolId).browserPath,
      {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorDetail = (await getErrorMsg(response)) ?? "Unknown error";
      return { data: false, error: `Failed to delete tool: ${errorDetail}` };
    }

    return { data: true, error: null };
  } catch (error) {
    console.error("Error deleting tool:", error);
    return { data: false, error: "Error deleting tool" };
  }
}

export interface CodeInterpreterUpdateRequest {
  enabled: boolean;
}

export async function updateCodeInterpreter(
  request: CodeInterpreterUpdateRequest
): Promise<Response> {
  return apiRequest(toolsEndpoints.codeInterpreter.browserPath, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export function connectMcpOAuthResponse(payload: {
  server_id: string;
  oauth_client_id: string;
  oauth_client_secret: string;
  return_path: string;
  include_resource_param: boolean;
}): Promise<Response> {
  return requestAgentPayload(toolsEndpoints.mcpOauthConnect.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function completeMcpOAuthCallback(
  code: string,
  state: string
): Promise<Response> {
  return requestAgentPayload(
    toolsEndpoints.oauthCallback(code, state).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    }
  );
}

import {
  MCPServerStatus,
  MCPAuthenticationType,
  MCPAuthenticationPerformer,
} from "@/lib/tools/interfaces";

import {
  ToolExecuteResponse as McpToolExecuteResponse,
  UpsertMCPServerResponse,
  BuiltInToolsResponse as McpBuiltInToolsResponse,
} from "@/lib/api/domains/tools/mcp-types";
import i18n from "@/i18n/config";

export async function deleteMCPServer(serverId: number): Promise<void> {
  const response = await requestAgentPayload(
    toolsEndpoints.deleteMcpServer(serverId).browserPath,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to delete MCP server");
  }
}

/**
 * Unbind a provider's credentials and cached tools; the system admin's
 * registration stays, so the provider returns to the "Add MCP server" picker.
 */
export async function disconnectMCPServer(
  serverId: number | string
): Promise<void> {
  const response = await requestAgentPayload(
    toolsEndpoints.disconnectMcpServer(serverId).browserPath,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to disconnect MCP server");
  }
}

export async function refreshMCPServerTools(
  serverId: number,
  source: "mcp" | "db" = "mcp"
): Promise<ToolSnapshot[]> {
  const response = await requestAgentPayload(
    toolsEndpoints.refreshMcpServerTools(serverId, source).browserPath
  );
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to refresh tools");
  }

  return await response.json();
}

export async function executeMcpServerTool(
  serverId: number,
  toolName: string,
  args: Record<string, unknown> = {}
): Promise<McpToolExecuteResponse> {
  const response = await requestAgentPayload(
    toolsEndpoints.executeMcpServerTool(serverId, toolName).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arguments: args }),
    }
  );
  if (!response.ok) {
    const detail = await response.text();
    return { result: null, error: detail || "Failed to execute tool" };
  }
  return await response.json();
}

export async function createMCPServer(
  data: MCPServerCreateRequest
): Promise<MCPServer> {
  const response = await requestAgentPayload(
    toolsEndpoints.adminServer.browserPath,
    {
      method: toolsEndpoints.adminServer.method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to create MCP server");
  }

  return await response.json();
}

export interface MCPServerValidationResult {
  /** The URL answered as an MCP server (whether or not it needs auth). */
  valid: boolean;
  /** The URL answered with a 401/403 challenge: a real MCP resource still to be authenticated. */
  auth_required: boolean;
  /** Tools discovered during a successful handshake. */
  tool_count: number;
}

/**
 * Probe a URL as MCP without persisting it. Backs the admin "Verify" action so
 * a non-MCP link is caught before it is registered.
 */
export async function validateMCPServer(data: {
  server_url: string;
}): Promise<MCPServerValidationResult> {
  const response = await requestAgentPayload(
    toolsEndpoints.validateMcpServer.browserPath,
    {
      method: toolsEndpoints.validateMcpServer.method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to validate MCP server");
  }

  return await response.json();
}

export async function updateMCPServer(
  serverId: number,
  data: MCPServerUpdateRequest
): Promise<MCPServer> {
  const response = await requestAgentPayload(
    toolsEndpoints.updateMcpServer(serverId).browserPath,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to update MCP server");
  }

  return await response.json();
}

export async function updateMCPServerStatus(
  serverId: number,
  status: MCPServerStatus
): Promise<void> {
  const response = await requestAgentPayload(
    toolsEndpoints.updateMcpServerStatus(serverId, status).browserPath,
    {
      method: "PATCH",
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || "Failed to update MCP server status");
  }
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
  auth_template?: {
    headers: Record<string, string>;
    required_fields: string[];
  };
  admin_credentials?: Record<string, string>;
  existing_server_id?: number;
}): Promise<ApiResponse<UpsertMCPServerResponse>> {
  try {
    const response = await requestAgentPayload(
      toolsEndpoints.adminServersCreate.browserPath,
      {
        method: toolsEndpoints.adminServersCreate.method,
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(serverData),
      }
    );

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

/**
 * Bind credentials to a provider a system admin already registered.
 *
 * Unlike `upsertMCPServer`, this never carries name/url: enterprise admins may
 * only authenticate an existing catalog entry, so the backend rejects any URL
 * on this path.
 */
export async function connectMCPServer(
  serverId: number | string,
  serverData: {
    transport: string;
    auth_type: MCPAuthenticationType;
    auth_performer: MCPAuthenticationPerformer;
    api_token?: string;
    auth_template?: {
      headers: Record<string, string>;
      required_fields: string[];
    };
    admin_credentials?: Record<string, string>;
    oauth_client_id?: string;
    oauth_client_secret?: string;
  }
): Promise<ApiResponse<UpsertMCPServerResponse>> {
  const endpoint = toolsEndpoints.connectMcpServer(serverId);
  try {
    const response = await requestAgentPayload(endpoint.browserPath, {
      method: endpoint.method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(serverData),
    });

    if (!response.ok) {
      const errorDetail = (await getErrorMsg(response)) ?? "Unknown error";
      return {
        data: null,
        error: `Failed to connect MCP server: ${errorDetail}`,
      };
    }

    const result: UpsertMCPServerResponse = await response.json();
    return { data: result, error: null };
  } catch (error) {
    console.error("Error connecting MCP server:", error);
    return { data: null, error: `Error connecting MCP server: ${error}` };
  }
}

export async function getBuiltInTools(
  language?: string
): Promise<McpBuiltInToolsResponse> {
  const currentLang = language || i18n.language || "en";
  const response = await requestAgentPayload(
    toolsEndpoints.listBuiltInTools.browserPath,
    {
      headers: {
        "X-Language": currentLang,
        "Accept-Language": currentLang,
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    return { tools: [], error: errorText || "Failed to fetch built-in tools" };
  }

  return await response.json();
}
