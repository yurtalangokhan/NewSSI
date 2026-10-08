export type ChatSessionId = string;

// ============================================================================
// Chat file utilities
// ============================================================================

/**
 * The URL that serves a chat file's *original* bytes.
 *
 * The plain endpoint is a preview endpoint: it deliberately transcodes an
 * XLSX to CSV text so the table preview can render it without extra parsing.
 * Saving that response under the original `.xlsx` name hands the user a file
 * Excel refuses to open ("file format or extension is not valid"), so
 * anything that downloads has to ask for the original bytes explicitly.
 */

/**
 * Where a download button should point.
 *
 * A file that has not been sent yet has no backend copy — it is previewed
 * straight from a `data:`/`blob:` URL, and that URL is also the only thing
 * there is to save. Anything stored server-side must come from the backend,
 * never from the blob the preview was built out of.
 */
export function resolveDownloadHref(
  fileId: string,
  previewUrl: string,
  isInlinePreview: boolean
): string {
  return isInlinePreview
    ? previewUrl
    : chatEndpoints.chatFileDownload(fileId).browserPath;
}

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const chatEndpoints = {
  deleteAllSessions: {
    method: "DELETE",
    browserPath: "/api/chat/delete-all-chat-sessions",
    backend: {
      service: "agent",
      path: "/api/v1/chat/delete-all-chat-sessions",
    },
  },
  getSession: (id: string) =>
    ({
      method: "GET",
      browserPath: `/api/chat/get-chat-session/${id}`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/sessions/${id}`,
      },
    }) as const,
  shareSession: (id: string) =>
    ({
      method: "PATCH",
      browserPath: `/api/chat/chat-session/${id}`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/sessions/${id}`,
      },
    }) as const,
  deleteSession: (id: string) =>
    ({
      method: "DELETE",
      browserPath: `/api/chat/delete-chat-session/${encodeURIComponent(id)}`,
      // Next.js route parameters are decoded before forwarding. Preserve that contract.
      backend: {
        service: "agent",
        path: `/api/v1/chat/sessions/${id}`,
      },
    }) as const,
  file: (id: string) =>
    ({
      method: "GET",
      browserPath: `/api/chat/file/${encodeURIComponent(id)}`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/file/${encodeURIComponent(id)}`,
      },
    }) as const,
  fileText: (id: string) =>
    ({
      method: "GET",
      browserPath: `/api/chat/file/${encodeURIComponent(id)}/text`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/file/${encodeURIComponent(id)}/text`,
      },
    }) as const,
  stopSession: (id: string) =>
    ({
      method: "POST",
      browserPath: `/api/chat/stop-chat-session/${id}`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/stop-chat-session/${id}`,
      },
    }) as const,
  availableContextTokens: (id: string) =>
    ({
      method: "GET",
      browserPath: `/api/chat/available-context-tokens/${id}`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/available-context-tokens/${id}`,
      },
    }) as const,
  activeRun: (sessionId: string) =>
    ({
      method: "GET",
      browserPath: `/api/chat/sessions/${encodeURIComponent(
        sessionId
      )}/active-run`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/sessions/${encodeURIComponent(
          sessionId
        )}/active-run`,
      },
    }) as const,
  markSeen: (sessionId: string) =>
    ({
      method: "POST",
      browserPath: `/api/chat/sessions/${encodeURIComponent(sessionId)}/seen`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/seen`,
      },
    }) as const,
  runEvents: (runId: string) =>
    ({
      method: "GET",
      browserPath: `/api/chat/runs/${encodeURIComponent(runId)}/events`,
      backend: {
        service: "agent",
        path: `/api/v1/chat/runs/${encodeURIComponent(runId)}/events`,
      },
    }) as const,
  sessions: {
    method: "GET",
    browserPath: "/api/chat/get-user-chat-sessions",
    backend: { service: "agent", path: "/api/v1/chat/sessions" },
  },
  sendMessage: {
    method: "POST",
    browserPath: "/api/chat/send-chat-message",
    backend: { service: "agent", path: "/api/v1/chat/messages" },
  },
  renameSession: {
    method: "PUT",
    browserPath: "/api/chat/rename-chat-session",
    backend: { service: "agent", path: "/api/v1/chat/rename-chat-session" },
  },
  setLatestMessage: {
    method: "PUT",
    browserPath: "/api/chat/set-message-as-latest",
    backend: { service: "agent", path: "/api/v1/chat/set-message-as-latest" },
  },
  createFeedback: {
    method: "POST",
    browserPath: "/api/chat/create-chat-message-feedback",
    backend: {
      service: "agent",
      path: "/api/v1/chat/create-chat-message-feedback",
    },
  },
  removeFeedback: {
    method: "DELETE",
    browserPath: "/api/chat/remove-chat-message-feedback",
    backend: {
      service: "agent",
      path: "/api/v1/chat/remove-chat-message-feedback",
    },
  },
  updateModel: {
    method: "PUT",
    browserPath: "/api/chat/update-chat-session-model",
    backend: {
      service: "agent",
      path: "/api/v1/chat/update-chat-session-model",
    },
  },
  updateTemperature: {
    method: "PUT",
    browserPath: "/api/chat/update-chat-session-temperature",
    backend: {
      service: "agent",
      path: "/api/v1/chat/update-chat-session-temperature",
    },
  },
  createSession: {
    method: "POST",
    browserPath: "/api/chat/create-chat-session",
    backend: { service: "agent", path: "/api/v1/chat/sessions" },
  },
  chatSearch: { browserPath: "/api/chat/search" },
  chatSearchPage: (
    page: number,
    pageSize: number,
    query?: string
  ): { browserPath: string } => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (query?.trim()) params.set("query", query);
    return {
      browserPath: `${
        chatEndpoints.chatSearch.browserPath
      }?${params.toString()}`,
    };
  },
  chatDocumentSearchFeedback: {
    browserPath: "/api/chat/document-search-feedback",
  },
  chatFile: { browserPath: "/api/chat/file" },
  chatHistory: (pageSize: number): { browserPath: string } => {
    return {
      browserPath: `/api/chat/get-user-chat-sessions?page_size=${pageSize}`,
    };
  },
  chatSeedFromSlack: { browserPath: "/api/chat/seed-chat-session-from-slack" },
  maxSelectedDocumentTokens: (personaId: number): { browserPath: string } => {
    return {
      browserPath: `/api/chat/max-selected-document-tokens?persona_id=${encodeURIComponent(
        String(personaId)
      )}`,
    };
  },
  chatFileDownload: (fileId: string): { browserPath: string } => {
    return {
      browserPath: `${chatEndpoints.chatFile.browserPath}/${encodeURIComponent(
        fileId
      )}?download=1`,
    };
  },
  fetchCsvChatFile: (id: string): { browserPath: string } => {
    return { browserPath: `/api/chat/file/${id}` };
  },
  fetchAgentDocumentTokenMaximum: (
    id: number | undefined
  ): { browserPath: string } => {
    return {
      browserPath: `/api/chat/max-selected-document-tokens?persona_id=${id}`,
    };
  },
  fetchChatFileText: (pathValue: string): { browserPath: string } => {
    return { browserPath: `/api/chat/file/${pathValue}/text` };
  },
  removeChatFeedback: (value0: number): { browserPath: string } => {
    return {
      browserPath: `/api/chat/remove-chat-message-feedback?chat_message_id=${value0}`,
    };
  },
  chatFileRoutePrefix: { browserPath: "/api/chat/file/" },
  chatSessionHistoryQueryKey: (query: string): { browserPath: string } => {
    return { browserPath: `/api/chat/get-user-chat-sessions?${query}` };
  },
} as const;
