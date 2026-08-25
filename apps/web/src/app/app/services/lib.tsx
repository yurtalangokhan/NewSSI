import {
  Filters,
  DocumentInfoPacket,
  StreamStopInfo,
} from "@/lib/search/interfaces";
import { handleSSEStream } from "@/lib/search/streamingUtils";
import { getErrorMsg } from "@/lib/fetchUtils";
import { FeedbackType } from "@/app/app/interfaces";
import {
  BackendMessage,
  DocumentsResponse,
  FileDescriptor,
  FileChatDisplay,
  Message,
  MessageResponseIDInfo,
  ResearchType,
  RetrievalType,
  StreamingError,
  ToolCallMetadata,
  UserKnowledgeFilePacket,
} from "../interfaces";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { ReadonlyURLSearchParams } from "next/navigation";
import { SEARCH_PARAM_NAMES } from "./searchParams";
import { WEB_SEARCH_TOOL_ID } from "@/app/app/components/tools/constants";
import { SEARCH_TOOL_ID } from "@/app/app/components/tools/constants";
import { Packet } from "./streamingModels";
import { authenticatedFetch } from "@/lib/fetcher";
import {
  createIdempotencyKey,
  withIdempotencyKey,
} from "@/lib/api/idempotency";

export async function updateLlmOverrideForChatSession(
  chatSessionId: string,
  newAlternateModel: string
) {
  const response = await authenticatedFetch(
    "/api/chat/update-chat-session-model",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        chat_session_id: chatSessionId,
        new_alternate_model: newAlternateModel,
      }),
    }
  );
  return response;
}

export async function updateTemperatureOverrideForChatSession(
  chatSessionId: string,
  newTemperature: number
) {
  const response = await authenticatedFetch(
    "/api/chat/update-chat-session-temperature",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        chat_session_id: chatSessionId,
        temperature_override: newTemperature,
      }),
    }
  );
  return response;
}

export async function createChatSession(
  personaId: string | number,
  description: string | null,
  projectId: number | null
): Promise<string> {
  const createChatSessionResponse = await authenticatedFetch(
    "/api/chat/create-chat-session",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        persona_id: personaId,
        description,
        project_id: projectId,
      }),
    }
  );
  if (!createChatSessionResponse.ok) {
    console.error(
      `Failed to create chat session - ${createChatSessionResponse.status}`
    );
    throw Error("Failed to create chat session");
  }
  const chatSessionResponseJson = await createChatSessionResponse.json();
  const chatSessionId =
    chatSessionResponseJson.chat_session_id ||
    chatSessionResponseJson.id ||
    chatSessionResponseJson.chatSessionId;

  if (!chatSessionId || typeof chatSessionId !== "string") {
    throw new Error("Invalid chat session ID in create-chat-session response");
  }

  return chatSessionId;
}

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

// Origin of the message for telemetry tracking.
// Keep in sync with backend: backend/onyx/server/query_and_chat/models.py::MessageOrigin
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
  // Reuse this key when retrying the same user-visible chat operation.
  idempotencyKey?: string;
}

export async function* sendMessage({
  message,
  fileDescriptors,
  parentMessageId,
  chatSessionId,
  filters,
  signal,
  deepResearch,
  enabledToolIds,
  forcedToolId,
  modelProviderId,
  modelProviderType,
  modelVersion,
  temperature,
  origin,
  additionalContext,
  projectId,
  personaId,
  isRegenerate,
  editTargetMessageId,
  idempotencyKey,
}: SendMessageParams): AsyncGenerator<PacketType, void, unknown> {
  // Build payload for new send-chat-message API
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
  };

  const body = JSON.stringify(payload);

  const response = await authenticatedFetch(`/api/chat/send-chat-message`, {
    method: "POST",
    headers: withIdempotencyKey(
      {
        "Content-Type": "application/json",
      },
      idempotencyKey ?? createIdempotencyKey()
    ),
    body,
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  yield* handleSSEStream<PacketType>(response, signal);
}

export async function nameChatSession(chatSessionId: string) {
  const response = await authenticatedFetch("/api/chat/rename-chat-session", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_session_id: chatSessionId,
      name: null,
    }),
  });
  return response;
}

export async function patchMessageToBeLatest(messageId: number) {
  const response = await authenticatedFetch("/api/chat/set-message-as-latest", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message_id: messageId,
    }),
  });
  return response;
}

export async function handleChatFeedback(
  messageId: number,
  feedback: FeedbackType,
  feedbackDetails: string,
  predefinedFeedback: string | undefined
) {
  const response = await authenticatedFetch(
    "/api/chat/create-chat-message-feedback",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        chat_message_id: messageId,
        is_positive: feedback === "like",
        feedback_text: feedbackDetails,
        predefined_feedback: predefinedFeedback,
      }),
    }
  );
  return response;
}

export async function removeChatFeedback(messageId: number) {
  const response = await authenticatedFetch(
    `/api/chat/remove-chat-message-feedback?chat_message_id=${messageId}`,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
  return response;
}

export async function renameChatSession(
  chatSessionId: string,
  newName: string
) {
  const response = await authenticatedFetch(`/api/chat/rename-chat-session`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_session_id: chatSessionId,
      name: newName,
    }),
  });
  return response;
}

export async function deleteChatSession(chatSessionId: string) {
  const response = await authenticatedFetch(
    `/api/chat/delete-chat-session/${chatSessionId}`,
    {
      method: "DELETE",
    }
  );
  return response;
}

export async function deleteAllChatSessions() {
  const response = await authenticatedFetch(
    `/api/chat/delete-all-chat-sessions`,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
  return response;
}

export async function getAvailableContextTokens(
  chatSessionId: string
): Promise<number> {
  const response = await authenticatedFetch(
    `/api/chat/available-context-tokens/${chatSessionId}`
  );
  if (!response.ok) {
    return 0;
  }
  const data = (await response.json()) as { available_tokens: number };
  return data?.available_tokens ?? 0;
}

export function processRawChatHistory(
  rawMessages: BackendMessage[] | undefined,
  packets: Packet[][]
): Map<number, Message> {
  const messages: Map<number, Message> = new Map();
  const parentMessageChildrenMap: Map<number, number[]> = new Map();

  let agentMessageInd = 0;

  // Handle undefined or empty messages
  if (!rawMessages || !Array.isArray(rawMessages)) {
    return messages;
  }

  rawMessages.forEach((messageInfo, _ind) => {
    const packetsForMessage = packets[agentMessageInd];
    if (messageInfo.message_type === "assistant") {
      agentMessageInd++;
    }

    const hasContextDocs = (messageInfo?.context_docs || []).length > 0;
    let retrievalType;
    if (hasContextDocs) {
      if (messageInfo.rephrased_query) {
        retrievalType = RetrievalType.Search;
      } else {
        retrievalType = RetrievalType.SelectedDocs;
      }
    } else {
      retrievalType = RetrievalType.None;
    }

    const message: Message = {
      // for existing messages, use the message_id as the nodeId
      // all that matters is that the nodeId is unique for a given chat session
      nodeId: messageInfo.message_id,
      messageId: messageInfo.message_id,
      message: messageInfo.message,
      type: messageInfo.message_type as "user" | "assistant",
      files: messageInfo.files,
      alternateAgentID:
        messageInfo.alternate_assistant_id !== null
          ? Number(messageInfo.alternate_assistant_id)
          : null,
      // only include these fields if this is an agent message so that
      // this is identical to what is computed at streaming time
      ...(messageInfo.message_type === "assistant"
        ? {
            retrievalType: retrievalType,
            researchType: messageInfo.research_type as ResearchType | undefined,
            query: messageInfo.rephrased_query,
            documents: messageInfo?.context_docs || [],
            citations: messageInfo?.citations || {},
            processingDurationSeconds: messageInfo.processing_duration_seconds,
          }
        : {}),
      toolCall: messageInfo.tool_call,
      parentNodeId: messageInfo.parent_message,
      childrenNodeIds: [],
      latestChildNodeId: messageInfo.latest_child_message,
      overridden_model: messageInfo.overridden_model,
      packets: packetsForMessage || [],
      currentFeedback: messageInfo.current_feedback as FeedbackType | null,
    };

    messages.set(messageInfo.message_id, message);

    if (messageInfo.parent_message !== null) {
      if (!parentMessageChildrenMap.has(messageInfo.parent_message)) {
        parentMessageChildrenMap.set(messageInfo.parent_message, []);
      }
      parentMessageChildrenMap
        .get(messageInfo.parent_message)!
        .push(messageInfo.message_id);
    }
  });

  // Populate childrenMessageIds for each message
  parentMessageChildrenMap.forEach((childrenIds, parentId) => {
    childrenIds.sort((a, b) => a - b);
    const parentMesage = messages.get(parentId);
    if (parentMesage) {
      parentMesage.childrenNodeIds = childrenIds;
    }
  });

  return messages;
}

export function personaIncludesRetrieval(
  selectedPersona: MinimalPersonaSnapshot
) {
  return selectedPersona.tools.some(
    (tool) =>
      tool.in_code_tool_id &&
      [SEARCH_TOOL_ID, WEB_SEARCH_TOOL_ID].includes(tool.in_code_tool_id)
  );
}

const PARAMS_TO_SKIP = [
  SEARCH_PARAM_NAMES.SUBMIT_ON_LOAD,
  SEARCH_PARAM_NAMES.USER_PROMPT,
  SEARCH_PARAM_NAMES.TITLE,
  // only use these if explicitly passed in
  SEARCH_PARAM_NAMES.CHAT_ID,
  SEARCH_PARAM_NAMES.PERSONA_ID,
  SEARCH_PARAM_NAMES.PROJECT_ID,
  // do not persist project context in the URL after navigation
  "projectid",
];

export function buildChatUrl(
  existingSearchParams: ReadonlyURLSearchParams | null,
  chatSessionId: string | null,
  personaId: string | number | null,
  search?: boolean,
  skipReload?: boolean
) {
  if (!search) {
    const finalSearchParams = new URLSearchParams();
    if (skipReload) {
      finalSearchParams.append(SEARCH_PARAM_NAMES.SKIP_RELOAD, "true");
    }
    existingSearchParams?.forEach((value, key) => {
      if (!PARAMS_TO_SKIP.includes(key)) {
        finalSearchParams.append(key, value);
      }
    });
    const finalSearchParamsString = finalSearchParams.toString();
    const querySuffix = finalSearchParamsString
      ? `?${finalSearchParamsString}`
      : "";

    if (chatSessionId) {
      return `/app/chats/${encodeURIComponent(chatSessionId)}${querySuffix}`;
    }
    if (personaId !== null) {
      return `/app/agents/${encodeURIComponent(
        String(personaId)
      )}${querySuffix}`;
    }
    return `/app${querySuffix}`;
  }

  const finalSearchParams: string[] = [];
  if (chatSessionId) {
    finalSearchParams.push(
      `${
        search ? SEARCH_PARAM_NAMES.SEARCH_ID : SEARCH_PARAM_NAMES.CHAT_ID
      }=${chatSessionId}`
    );
  }
  if (personaId !== null) {
    finalSearchParams.push(`${SEARCH_PARAM_NAMES.PERSONA_ID}=${personaId}`);
  }

  existingSearchParams?.forEach((value, key) => {
    if (!PARAMS_TO_SKIP.includes(key)) {
      finalSearchParams.push(`${key}=${value}`);
    }
  });

  const finalSearchParamsString = finalSearchParams.join("&");

  if (finalSearchParamsString) {
    return `/app?${finalSearchParamsString}`;
  }

  return "/app";
}

export async function uploadFilesForChat(
  files: File[]
): Promise<[FileDescriptor[], string | null]> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await authenticatedFetch("/api/chat/file", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    return [
      [],
      `Failed to upload files - ${
        (await getErrorMsg(response)) ?? "Unknown error"
      }`,
    ];
  }
  const responseJson = await response.json();

  return [responseJson.files as FileDescriptor[], null];
}
