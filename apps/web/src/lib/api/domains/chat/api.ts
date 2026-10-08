import { parseResponseModel } from "@/lib/api/responseModel";
import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";

import "@/lib/fetchUtils";
import type { FeedbackType } from "@/lib/api/domains/chat/types";
import type {
  PacketType,
  SendMessageParams,
} from "@/lib/api/domains/chat/message-types";
import {
  createIdempotencyKey,
  withIdempotencyKey,
} from "@/lib/api/idempotency";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

import type { ActiveRunInfo } from "./resumableChatStream";
import { resumableChatStream } from "./resumableChatStream";

import type { ChatSearchPageRequest } from "@/lib/api/domains/chat/types";

import type { ChatSessionId } from "@/lib/api/domains/chat/endpoints";
import i18n from "@/i18n/config";

export async function fetchChatHistory<T>(pageSize: number): Promise<T> {
  const response = await apiRequest(
    chatEndpoints.chatHistory(pageSize).browserPath
  );
  return parseResponseModel<T>(response);
}

export async function fetchChatSearchPage<T>({
  page,
  pageSize,
  query,
}: ChatSearchPageRequest): Promise<T> {
  const response = await apiRequest(
    chatEndpoints.chatSearchPage(page, pageSize, query).browserPath,
    {
      headers: { "X-Language": i18n.language },
    }
  );
  if (!response.ok) {
    const parsedError = await parseApiErrorResponse(response);
    throw new FetchError(
      parsedError.userMessage,
      response.status,
      parsedError.raw,
      parsedError
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    return {} as T;
  }
}

// ============================================================================
// Paginated chat sessions (for useSWRInfinite)
// ============================================================================

export interface ChatSessionsPage {
  sessions: unknown[];
  has_more: boolean;
  next_cursor?: {
    before_activity?: string | null;
    before_id?: string | null;
  } | null;
}

export async function fetchChatSessionsPage<T = ChatSessionsPage>(
  url: string
): Promise<T> {
  const response = await apiRequest(url, {
    headers: { "X-Language": i18n.language },
  }).then(agentServicePayloadResponse);
  if (!response.ok) {
    const parsedError = await parseApiErrorResponse(response);
    throw new FetchError(
      parsedError.userMessage,
      response.status,
      parsedError.raw,
      parsedError
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    return {} as T;
  }
}

export async function renameChatSession(
  sessionId: ChatSessionId,
  name: string | null
): Promise<Response> {
  return apiRequest(chatEndpoints.renameSession.browserPath, {
    method: chatEndpoints.renameSession.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_session_id: sessionId, name }),
  }).then(agentServicePayloadResponse);
}

export function deleteAllChatSessions(): Promise<Response> {
  return apiRequest(chatEndpoints.deleteAllSessions.browserPath, {
    method: chatEndpoints.deleteAllSessions.method,
  }).then(agentServicePayloadResponse);
}

export async function fetchChatFile(fileId: string): Promise<Response> {
  const response = await apiRequest(chatEndpoints.file(fileId).browserPath, {
    method: "GET",
  });
  if (!response.ok) throw new Error("Failed to load document.");
  return response;
}

export async function fetchMaxSelectedDocumentTokens(
  personaId: number
): Promise<number> {
  const response = await apiRequest(
    chatEndpoints.maxSelectedDocumentTokens(personaId).browserPath
  );
  if (!response.ok) {
    return 128_000;
  }
  const data = (await response.json()) as { max_tokens?: number };
  return data.max_tokens ?? 128_000;
}

export async function createChatSession(
  personaId: string | number,
  description: string | null,
  projectId: number | null
): Promise<string> {
  const response = await apiRequest(chatEndpoints.createSession.browserPath, {
    method: chatEndpoints.createSession.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      persona_id: personaId,
      description,
      project_id: projectId,
    }),
  }).then(agentServicePayloadResponse);
  if (!response.ok) {
    console.error(`Failed to create chat session - ${response.status}`);
    throw new Error("Failed to create chat session");
  }
  const result = (await response.json()) as {
    chat_session_id?: string;
    id?: string;
    chatSessionId?: string;
  };
  const chatSessionId =
    result.chat_session_id || result.id || result.chatSessionId;
  if (!chatSessionId || typeof chatSessionId !== "string") {
    throw new Error("Invalid chat session ID in create-chat-session response");
  }
  return chatSessionId;
}

export async function updateLlmOverrideForChatSession(
  chatSessionId: string,
  newAlternateModel: string
): Promise<Response> {
  return apiRequest(chatEndpoints.updateModel.browserPath, {
    method: chatEndpoints.updateModel.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_session_id: chatSessionId,
      new_alternate_model: newAlternateModel,
    }),
  }).then(agentServicePayloadResponse);
}

export async function deleteChatSession(
  chatSessionId: ChatSessionId
): Promise<Response> {
  return apiRequest(chatEndpoints.deleteSession(chatSessionId).browserPath, {
    method: "DELETE",
  }).then(agentServicePayloadResponse);
}

// Migrated chat actions (behavior-preserving)
export async function updateTemperatureOverrideForChatSession(
  chatSessionId: string,
  newTemperature: number
) {
  const response = await apiRequest(
    chatEndpoints.updateTemperature.browserPath,
    {
      method: chatEndpoints.updateTemperature.method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        chat_session_id: chatSessionId,
        temperature_override: newTemperature,
      }),
    }
  ).then(agentServicePayloadResponse);
  return response;
}

/**
 * Opens the POST /chat/messages SSE response without inspecting it: the
 * resumable wrapper owns status handling (409 active-run, !ok errors).
 */
export function openChatMessageStream(
  {
    message,
    fileDescriptors,
    parentMessageId,
    chatSessionId,
    filters,
    deepResearch,
    enabledToolIds,
    forcedToolId,
    modelProviderId,
    modelProviderType,
    modelVersion,
    temperature,
    origin,
    additionalContext,
    documentContext,
    projectId,
    personaId,
    isRegenerate,
    editTargetMessageId,
    resumePayload,
    idempotencyKey,
  }: SendMessageParams,
  signal?: AbortSignal
): Promise<Response> {
  const payload = {
    message: message,
    chat_session_id: chatSessionId,
    project_id: projectId ?? null,
    persona_id: personaId ?? null,
    parent_message_id: parentMessageId,
    file_descriptors: fileDescriptors,
    internal_search_filters: filters,
    deep_research: deepResearch ?? false,
    allowed_tool_ids: enabledToolIds,
    forced_tool_id: forcedToolId ?? null,
    is_regenerate: isRegenerate ?? false,
    edit_target_message_id: editTargetMessageId ?? null,
    llm_override:
      temperature || modelVersion || modelProviderId || modelProviderType
        ? {
            temperature,
            model: modelVersion,
            provider_id: modelProviderId,
            provider_type: modelProviderType,
          }
        : null,
    // Default to "unknown" for consistency with backend; callers should set explicitly
    origin: origin ?? "unknown",
    additional_context: additionalContext ?? null,
    document_context: documentContext ?? null,
    resume_payload: resumePayload ?? null,
  };

  return apiRequest(chatEndpoints.sendMessage.browserPath, {
    method: chatEndpoints.sendMessage.method,
    headers: withIdempotencyKey(
      {
        "Content-Type": "application/json",
      },
      idempotencyKey ?? createIdempotencyKey()
    ),
    body: JSON.stringify(payload),
    signal,
  });
}

export function sendMessage(
  params: SendMessageParams
): AsyncGenerator<PacketType, void, unknown> {
  const clientRequestId = params.idempotencyKey ?? createIdempotencyKey();
  return resumableChatStream({
    open: (signal) =>
      openChatMessageStream(
        { ...params, idempotencyKey: clientRequestId },
        signal
      ),
    attach: (runId, signal) => openRunEvents(runId, signal),
    findActiveRun: (signal) =>
      params.chatSessionId
        ? fetchActiveRun(params.chatSessionId, signal)
        : Promise.resolve(null),
    clientRequestId,
    onReplayChange: params.onReplayChange,
    signal: params.signal ?? new AbortController().signal,
  });
}

export async function fetchActiveRun(
  sessionId: string,
  signal?: AbortSignal
): Promise<ActiveRunInfo | null> {
  const response = await apiRequest(
    chatEndpoints.activeRun(sessionId).browserPath,
    { method: "GET", signal }
  );
  if (!response.ok) return null;
  const body = (await response.json()) as { active_run: ActiveRunInfo | null };
  return body.active_run;
}

/**
 * Advances the chat's read watermark so the sidebar's unread dot clears for an
 * answer already on screen. Best-effort: callers ignore a failure; the dot is
 * reconciled by the next session-list refresh.
 */
export async function markChatSessionSeen(sessionId: string): Promise<void> {
  const endpoint = chatEndpoints.markSeen(sessionId);
  await apiRequest(endpoint.browserPath, { method: endpoint.method });
}

export function openRunEvents(
  runId: string,
  signal?: AbortSignal
): Promise<Response> {
  return apiRequest(`${chatEndpoints.runEvents(runId).browserPath}?after=0`, {
    method: "GET",
    headers: { Accept: "text/event-stream" },
    signal,
  });
}

export async function patchMessageToBeLatest(messageId: number) {
  const response = await apiRequest(
    chatEndpoints.setLatestMessage.browserPath,
    {
      method: chatEndpoints.setLatestMessage.method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message_id: messageId,
      }),
    }
  ).then(agentServicePayloadResponse);
  return response;
}

export async function handleChatFeedback(
  messageId: number,
  feedback: FeedbackType,
  feedbackDetails: string,
  predefinedFeedback: string | undefined
) {
  const response = await apiRequest(chatEndpoints.createFeedback.browserPath, {
    method: chatEndpoints.createFeedback.method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_message_id: messageId,
      is_positive: feedback === "like",
      feedback_text: feedbackDetails,
      predefined_feedback: predefinedFeedback,
    }),
  }).then(agentServicePayloadResponse);
  return response;
}

export async function removeChatFeedback(messageId: number) {
  const response = await apiRequest(
    chatEndpoints.removeChatFeedback(messageId).browserPath,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }
  ).then(agentServicePayloadResponse);
  return response;
}

export async function getAvailableContextTokens(
  chatSessionId: string
): Promise<number> {
  const response = await apiRequest(
    chatEndpoints.availableContextTokens(chatSessionId).browserPath
  ).then(agentServicePayloadResponse);
  if (!response.ok) {
    return 0;
  }
  const data = (await response.json()) as { available_tokens: number };
  return data?.available_tokens ?? 0;
}

export function submitDocumentSearchFeedback(payload: {
  message_id: number;
  document_id: string;
  document_rank: number;
  click: boolean;
  search_feedback: "endorse" | "reject" | "hide" | "unhide";
}): Promise<Response> {
  return apiRequest(chatEndpoints.chatDocumentSearchFeedback.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function fetchCsvChatFile(id: string): Promise<Response> {
  return apiRequest(chatEndpoints.fetchCsvChatFile(id).browserPath, {
    cache: "no-store",
  });
}

export function stopActiveChatSession(
  chatSessionId: string,
  clientRequestId?: string
): Promise<Response> {
  const query = clientRequestId
    ? `?${new URLSearchParams({ client_request_id: clientRequestId })}`
    : "";
  return apiRequest(
    `${chatEndpoints.stopSession(chatSessionId).browserPath}${query}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  ).then(agentServicePayloadResponse);
}

export function seedChatFromSlack(payload: {
  chat_session_id: string;
}): Promise<Response> {
  return apiRequest(chatEndpoints.chatSeedFromSlack.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function fetchAgentDocumentTokenMaximum(
  id: number | undefined
): Promise<Response> {
  return apiRequest(
    chatEndpoints.fetchAgentDocumentTokenMaximum(id).browserPath
  );
}

export function fetchInitialChatSession(
  existingChatSessionId: string,
  signal: AbortSignal
): Promise<Response> {
  return apiRequest(
    chatEndpoints.getSession(existingChatSessionId).browserPath,
    { signal: signal }
  ).then(agentServicePayloadResponse);
}

export function setChatSessionSharing(
  chatSessionId: string,
  payload: { sharing_status: string }
): Promise<Response> {
  return apiRequest(chatEndpoints.shareSession(chatSessionId).browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchChatFileBlob(
  pathValue: string,
  signal: AbortSignal
): Promise<Response> {
  return apiRequest(chatEndpoints.fetchCsvChatFile(pathValue).browserPath, {
    method: "GET",
    signal: signal,
  });
}

export function fetchChatFileTextResponse(
  pathValue: string,
  signal: AbortSignal
): Promise<Response> {
  return apiRequest(chatEndpoints.fetchChatFileText(pathValue).browserPath, {
    method: "GET",
    signal: signal,
  });
}

export function downloadMessageImage(fileId: string): Promise<Response> {
  return apiRequest(chatEndpoints.fetchCsvChatFile(fileId).browserPath);
}
