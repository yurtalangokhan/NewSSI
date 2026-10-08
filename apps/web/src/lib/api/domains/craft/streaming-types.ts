export type SharingScope = "private" | "public_org" | "public_global";

export const SessionErrorCode = {
  RATE_LIMIT_EXCEEDED: "RATE_LIMIT_EXCEEDED",
} as const;

export type SessionErrorCode =
  (typeof SessionErrorCode)[keyof typeof SessionErrorCode];

export type LimitType = "weekly" | "total";

export interface UsageLimits {
  /** Whether the user has reached their limit */
  isLimited: boolean;
  /** Type of limit period: "weekly" for paid, "total" for free */
  limitType: LimitType;
  /** Number of messages used in current period */
  messagesUsed: number;
  /** Maximum messages allowed in the period */
  limit: number;
  /** For weekly limits: timestamp when the limit resets (null for total limits) */
  resetTimestamp: Date | null;
}

export interface ApiUsageLimitsResponse {
  is_limited: boolean;
  limit_type: LimitType;
  messages_used: number;
  limit: number;
  reset_timestamp: string | null;
}

export type ArtifactType =
  | "nextjs_app"
  | "web_app" // Backend sends this
  | "pptx"
  | "xlsx"
  | "docx"
  | "markdown"
  | "chart"
  | "csv"
  | "image";

export interface Artifact {
  id: string;
  session_id: string;
  type: ArtifactType;
  name: string;
  path: string;
  preview_url?: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface BuildMessage {
  id: string;
  type: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  /** Structured ACP event data (tool calls, thinking, plans) */
  message_metadata?: Record<string, any> | null;
  /** Tool calls associated with this message (for agent messages) */
  toolCalls?: ToolCall[];
}

export type ToolCallStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled";

export interface ToolCall {
  /** Unique ID for this tool call */
  id: string;
  /** Tool kind/category (e.g., "edit", "execute", "other") */
  kind: string;
  /** Tool name (e.g., "write", "bash", "ls") */
  name: string;
  /** Human-readable title */
  title: string;
  /** Current status */
  status: ToolCallStatus;
  /** Tool input parameters */
  input?: Record<string, unknown>;
  /** Raw input from ACP (complete command/parameters) */
  raw_input?: Record<string, any> | null;
  /** Raw output from ACP (complete result) */
  raw_output?: Record<string, any> | null;
  /** Content block from ACP (description text) */
  content?: any | null;
  /** Result content (when completed) */
  result?: string;
  /** Error message (when failed) */
  error?: string;
  /** When the tool call started */
  startedAt: Date;
  /** When the tool call finished */
  finishedAt?: Date;
}

export type SessionStatus =
  | "idle"
  | "creating"
  | "running"
  | "active"
  | "failed";

export interface Session {
  id: string | null;
  status: SessionStatus;
  artifacts: Artifact[];
  messages: BuildMessage[];
  error: string | null;
  webappUrl: string | null;
}

export interface SessionHistoryItem {
  id: string;
  title: string;
  createdAt: Date;
}

export interface ApiSandboxResponse {
  id: string;
  status:
    | "provisioning"
    | "running"
    | "idle"
    | "sleeping"
    | "terminated"
    | "failed"
    | "restoring"; // Frontend-only: set during snapshot restore
  container_id: string | null;
  created_at: string;
  last_heartbeat: string | null;
  nextjs_port: number | null;
}

export interface ApiSessionResponse {
  id: string;
  user_id: string | null;
  name: string | null;
  status: "active" | "idle" | "archived";
  created_at: string;
  last_activity_at: string;
  sandbox: ApiSandboxResponse | null;
  artifacts: ApiArtifactResponse[];
  sharing_scope: SharingScope;
}

export interface ApiDetailedSessionResponse extends ApiSessionResponse {
  session_loaded_in_sandbox: boolean;
}

export interface ApiMessageResponse {
  id: string;
  session_id: string;
  type: "user" | "assistant";
  content: string;
  message_metadata?: Record<string, any> | null;
  created_at: string;
}

export interface ApiArtifactResponse {
  id: string;
  session_id: string;
  type: ArtifactType;
  path: string;
  name: string;
  created_at: string;
  updated_at: string;
  preview_url?: string | null;
}

export interface ApiWebappInfoResponse {
  has_webapp: boolean;
  webapp_url: string | null;
  status: string;
  ready: boolean;
  sharing_scope: SharingScope;
}

export interface FileSystemEntry {
  name: string;
  path: string;
  is_directory: boolean;
  size: number | null;
  mime_type: string | null;
}

export interface DirectoryListing {
  path: string;
  entries: FileSystemEntry[];
}

export interface StepStartPacket {
  type: "step_start";
  step_id: string;
  step_name?: string;
  timestamp: string;
}

export interface StepDeltaPacket {
  type: "step_delta";
  step_id: string;
  content: string;
  timestamp: string;
}

export interface StepEndPacket {
  type: "step_end";
  step_id: string;
  status: "completed" | "failed" | "cancelled";
  timestamp: string;
}

export interface ToolStartPacket {
  type: "tool_start";
  tool_call_id: string;
  tool_name: string;
  tool_input: Record<string, any>;
  title?: string;
  timestamp: string;
}

export interface ToolProgressPacket {
  type: "tool_progress";
  tool_call_id: string;
  tool_name: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "cancelled";
  progress?: number;
  message?: string;
  timestamp: string;
}

export interface ToolEndPacket {
  type: "tool_end";
  tool_call_id: string;
  tool_name: string;
  status: "success" | "error" | "cancelled";
  result?: string | Record<string, any>;
  error?: string;
  timestamp: string;
}

export interface OutputStartPacket {
  type: "output_start";
  timestamp: string;
}

export interface OutputDeltaPacket {
  type: "output_delta";
  content: string;
  timestamp: string;
}

export interface OutputEndPacket {
  type: "output_end";
  timestamp: string;
}

export interface PlanEntry {
  id: string;
  description: string;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  priority?: number;
}

export interface PlanPacket {
  type: "plan";
  plan?: string;
  entries?: PlanEntry[];
  timestamp: string;
}

export interface ModeUpdatePacket {
  type: "mode_update";
  mode: string;
  description?: string;
  timestamp: string;
}

export interface DonePacket {
  type: "done";
  summary: string;
  stop_reason?:
    | "end_turn"
    | "max_tokens"
    | "max_turn_requests"
    | "refusal"
    | "cancelled";
  usage?: Record<string, any>;
  timestamp: string;
}

export interface ErrorPacket {
  type: "error";
  message: string;
  code?: number;
  details?: Record<string, any>;
  timestamp: string;
}

export interface FileWritePacket {
  type: "file_write";
  path: string;
  size_bytes?: number;
  operation: "create" | "update" | "delete";
  timestamp: string;
}

export type BackendArtifactType =
  | "web_app"
  | "markdown"
  | "image"
  | "csv"
  | "excel"
  | "pptx"
  | "docx"
  | "pdf"
  | "code"
  | "other";

export interface ArtifactCreatedPacket {
  type: "artifact_created";
  artifact: {
    id: string;
    type: BackendArtifactType;
    name: string;
    path: string;
    preview_url?: string;
    download_url?: string;
    mime_type?: string;
    size_bytes?: number;
  };
  timestamp: string;
}

export interface PermissionRequestPacket {
  type: "permission_request";
  request_id: string;
  operation: string;
  description: string;
  auto_approve: boolean;
  timestamp: string;
}

export interface PermissionResponsePacket {
  type: "permission_response";
  request_id: string;
  approved: boolean;
  reason?: string;
  timestamp: string;
}

export interface TextContentBlock {
  type: "text";
  text: string;
}

export interface ImageContentBlock {
  type: "image";
  data: string;
  mimeType: string;
}

export type ContentBlock =
  | TextContentBlock
  | ImageContentBlock
  | Record<string, any>;

export interface ACPBaseEvent {
  field_meta?: Record<string, any> | null; // _meta field for extensibility
  timestamp: string;
}

export interface AgentMessageChunkPacket extends ACPBaseEvent {
  type: "agent_message_chunk";
  content: ContentBlock;
  session_update?: string;
}

export interface AgentThoughtChunkPacket extends ACPBaseEvent {
  type: "agent_thought_chunk";
  content: ContentBlock;
  session_update?: string;
}

export interface ToolCallStartPacket extends ACPBaseEvent {
  type: "tool_call_start";
  tool_call_id: string;
  kind: string | null;
  title: string | null;
  content: ContentBlock | null;
  locations: string[] | null;
  raw_input: Record<string, any> | null;
  raw_output: Record<string, any> | null;
  status: string | null;
  session_update?: string;
}

export interface ToolCallProgressPacket extends ACPBaseEvent {
  type: "tool_call_progress";
  tool_call_id: string;
  kind: string | null;
  title: string | null;
  content: ContentBlock | null;
  locations: string[] | null;
  raw_input: Record<string, any> | null;
  raw_output: Record<string, any> | null;
  status: string | null;
  session_update?: string;
}

export interface AgentPlanUpdatePacket extends ACPBaseEvent {
  type: "agent_plan_update";
  entries: Array<{
    id: string;
    description: string;
    status: string;
    priority: string | number | null;
  }> | null;
  session_update?: string;
}

export interface CurrentModeUpdatePacket extends ACPBaseEvent {
  type: "current_mode_update";
  current_mode_id: string | null;
  session_update?: string;
}

export interface PromptResponsePacket extends ACPBaseEvent {
  type: "prompt_response";
  stop_reason: string | null;
}

export interface ACPErrorPacket {
  type: "error";
  code: string | null;
  message: string;
  data: Record<string, any> | null;
  timestamp: string;
}

export type StreamPacket =
  // Raw ACP packets with ALL fields
  | AgentMessageChunkPacket
  | AgentThoughtChunkPacket
  | ToolCallStartPacket
  | ToolCallProgressPacket
  | AgentPlanUpdatePacket
  | CurrentModeUpdatePacket
  | PromptResponsePacket
  | ACPErrorPacket
  // Custom Atlas packets
  | StepStartPacket
  | StepDeltaPacket
  | StepEndPacket
  | ToolStartPacket
  | ToolProgressPacket
  | ToolEndPacket
  | OutputStartPacket
  | OutputDeltaPacket
  | OutputEndPacket
  | PlanPacket
  | ModeUpdatePacket
  | DonePacket
  | ErrorPacket
  | FileWritePacket
  | ArtifactCreatedPacket
  | PermissionRequestPacket
  | PermissionResponsePacket
  | { type: string; timestamp?: string };
