import {
  Filters,
  DocumentInfoPacket,
  StreamStopInfo,
} from "@/lib/search/interfaces";

import {
  BackendMessage,
  DocumentsResponse,
  FileDescriptor,
  FileChatDisplay,
  MessageResponseIDInfo,
  StreamingError,
  ToolCallMetadata,
  UserKnowledgeFilePacket,
} from "@/lib/api/domains/chat/types";

import { Packet } from "@/lib/api/domains/chat/streaming-types";
import type { DocumentContextRef } from "@/lib/api/domains/documents/types";
export type PacketType =
  | ToolCallMetadata
  | BackendMessage
  | DocumentInfoPacket
  | DocumentsResponse
  | FileChatDisplay
  | StreamingError
  | MessageResponseIDInfo
  | StreamStopInfo
  | UserKnowledgeFilePacket
  | Packet;

export type MessageOrigin =
  | "webapp"
  | "chrome_extension"
  | "api"
  | "slackbot"
  | "unknown";

export interface SendMessageParams {
  message: string;
  fileDescriptors?: FileDescriptor[];
  parentMessageId: number | null;
  chatSessionId: string;
  filters: Filters | null;
  signal?: AbortSignal;
  // Called when the stream enters or leaves a replay of the run's history.
  onReplayChange?: (replaying: boolean) => void;
  deepResearch?: boolean;
  enabledToolIds?: number[];
  // Single forced tool ID (new API uses singular, not array)
  forcedToolId?: number | null;
  // LLM override parameters
  modelProviderId?: string;
  modelProviderType?: string;
  modelVersion?: string;
  temperature?: number;
  // Origin of the message for telemetry tracking
  origin?: MessageOrigin;
  // Additional context injected into the LLM call but not stored/shown in chat.
  // Used e.g. by Chrome extension "Read this tab" feature.
  // The document the user is looking at in the panel; the agent resolves
  // "this", "the table" etc. against it (design §4.8).
  documentContext?: DocumentContextRef | null;
  additionalContext?: string;
  projectId?: number | null;
  // Persona/agent ID for routing to specific agent
  personaId?: string | number;
  // Set when this send is retrying/regenerating a previous response, so
  // the backend can mark the resulting duplicate message and history
  // reconstruction can treat the new response as a sibling of the
  // original instead of a new conversation turn.
  isRegenerate?: boolean;
  // Set when this send is editing the text of a previously-sent user
  // message (the message's own id, not its parent). The backend forks the
  // checkpoint at that message and replaces its content, so the new
  // response excludes the old response (and anything sent after it) from
  // its context, while the old branch stays reachable via history.
  editTargetMessageId?: number | null;
  // Answers to an ask_user card. The run is parked on an interrupt, and this
  // is what resumes it — structured rather than text, so the backend never
  // has to guess which question an answer belonged to (design 4.4).
  resumePayload?: Record<string, unknown> | null;
  // Reuse this key when retrying the same user-visible chat operation.
  idempotencyKey?: string;
}
