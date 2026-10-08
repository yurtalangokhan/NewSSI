export interface ToolStatusUpdateRequest {
  tool_ids: number[];
  enabled: boolean;
}

export interface ToolStatusUpdateResponse {
  updated_count: number;
  tool_ids: number[];
}

export interface UpsertMCPServerResponse {
  server_id: number;
  server_name: string;
  server_url: string;
  auth_type: string;
  auth_performer: string;
  is_authenticated: boolean;
}

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
