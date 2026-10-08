import { FeedbackType } from "@/lib/api/domains/chat/types";
import {
  BackendMessage,
  Message,
  ResearchType,
  RetrievalType,
} from "@/lib/api/domains/chat/types";
import { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import { ReadonlyURLSearchParams } from "next/navigation";
import { SEARCH_PARAM_NAMES } from "./searchParams";
import { WEB_SEARCH_TOOL_ID } from "@/app/app/components/tools/constants";
import { SEARCH_TOOL_ID } from "@/lib/api/domains/tools/constants";
import { Packet } from "@/lib/api/domains/chat/streaming-types";

// Origin of the message for telemetry tracking.
// Keep in sync with backend: backend/atlas/server/query_and_chat/models.py::MessageOrigin

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
      timeSent: messageInfo.time_sent ?? undefined,
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
