export interface CreateSessionRequest {
  task: string;
  available_sources?: string[];
}

export interface CreateSessionResponse {
  session_id: string;
}

export interface ArtifactInfo {
  artifact_type: "webapp" | "file" | "markdown" | "image";
  path: string;
  filename: string;
  mime_type?: string;
}

// =============================================================================
// ACP Event Types (from Agent Client Protocol)
// =============================================================================

/** Text or image content from the agent */
export interface AgentMessageChunkEvent {
  sessionUpdate: "agent_message_chunk";
  content: Array<{
    type: "text" | "image";
    text?: string;
    image?: string;
    mimeType?: string;
  }>;
}

/** Agent's internal reasoning/thinking */
export interface AgentThoughtChunkEvent {
  sessionUpdate: "agent_thought_chunk";
  thought: string;
}

/** Tool invocation started */
export interface ToolCallStartEvent {
  sessionUpdate: "tool_call";
  toolCallId: string;
  toolName: string;
  toolInput?: Record<string, unknown>;
}

/** Tool execution progress/result */
export interface ToolCallProgressEvent {
  sessionUpdate: "tool_call_update";
  toolCallId: string;
  content?: Array<{
    type: "text" | "image";
    text?: string;
    image?: string;
    mimeType?: string;
  }>;
  error?: string;
  isComplete?: boolean;
}

/** Agent's execution plan */
export interface AgentPlanUpdateEvent {
  sessionUpdate: "plan";
  plan: Array<{
    id: string;
    description: string;
    status: "pending" | "in_progress" | "completed" | "failed";
  }>;
}

/** Agent mode change */
export interface CurrentModeUpdateEvent {
  sessionUpdate: "current_mode_update";
  mode: string;
}

/** Agent finished processing prompt */
export interface PromptResponseEvent {
  stopReason?: string;
  usage?: {
    inputTokens?: number;
    outputTokens?: number;
  };
}

/** ACP error event */
export interface ACPErrorEvent {
  code: number;
  message: string;
}

/** File write event (custom Atlas extension) */
export interface FileWriteEvent {
  path: string;
  size_bytes?: number;
  operation?: "create" | "update" | "delete";
}

// =============================================================================
// Legacy Event Types (kept for backwards compatibility)
// =============================================================================

export interface OutputEvent {
  stream: "stdout" | "stderr";
  data: string;
}

export interface StatusEvent {
  status: "running" | "completed" | "failed";
  message?: string;
}

export interface ArtifactEvent {
  artifact_type: string;
  path: string;
  filename: string;
}

export interface ErrorEvent {
  message: string;
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

// =============================================================================
// Union Types
// =============================================================================

/** All possible ACP events from the agent */
export type ACPEvent =
  | { type: "agent_message_chunk"; data: AgentMessageChunkEvent }
  | { type: "agent_thought_chunk"; data: AgentThoughtChunkEvent }
  | { type: "tool_call"; data: ToolCallStartEvent }
  | { type: "tool_call_update"; data: ToolCallProgressEvent }
  | { type: "plan"; data: AgentPlanUpdateEvent }
  | { type: "current_mode_update"; data: CurrentModeUpdateEvent }
  | { type: "prompt_response"; data: PromptResponseEvent }
  | { type: "error"; data: ACPErrorEvent }
  | { type: "status"; data: StatusEvent }
  | { type: "artifact"; data: ArtifactEvent }
  | { type: "file_write"; data: FileWriteEvent };

/** Legacy BuildEvent type - alias for ACPEvent */
export type BuildEvent = ACPEvent;

/**
 * Send a message to the build session using the new messages API endpoint.
 * This endpoint streams SSE events with message-prefixed packet types.
 */
/**
 * Map message API packet types to BuildEvent types.
 * Uses direct ACP event names from the backend, plus custom Atlas packet types.
 */
function mapMessagePacketToEventType(packetType: string): string | null {
  const mapping: Record<string, string> = {
    // Direct ACP event types
    agent_message_chunk: "agent_message_chunk",
    agent_thought_chunk: "agent_thought_chunk",
    tool_call_start: "tool_call",
    tool_call_progress: "tool_call_update",
    agent_plan_update: "plan",
    current_mode_update: "current_mode_update",
    prompt_response: "prompt_response",
    error: "error",
    // Custom Atlas packet types (extensions to ACP)
    artifact_created: "artifact",
    file_write: "file_write",
  };
  return mapping[packetType] || null;
}
