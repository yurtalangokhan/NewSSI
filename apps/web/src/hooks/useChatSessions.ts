"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import useSWRInfinite from "swr/infinite";
import { ChatSession, ChatSessionSharedStatus } from "@/app/app/interfaces";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { AgentId, MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import useAppFocus from "./useAppFocus";
import { agentIdsMatch, useAgents } from "./useAgents";
import { DEFAULT_AGENT_ID } from "@/lib/constants";
import {
  getChatSessionsPageKey,
  mergeChatSessionsByFreshness,
} from "@/lib/chat/chatSessionActivity";

const PAGE_SIZE = 50;
const MIN_LOADING_DURATION_MS = 500;

interface ChatSessionsResponse {
  sessions: ChatSession[];
  has_more: boolean;
  next_cursor?: {
    before_activity?: string | null;
    before_id?: string | null;
  } | null;
}

function isValidChatSession(session: unknown): session is ChatSession {
  if (!session || typeof session !== "object") {
    return false;
  }

  const candidate = session as Partial<ChatSession>;
  return typeof candidate.id === "string" && candidate.id.length > 0;
}

export interface PendingChatSessionParams {
  chatSessionId: string;
  personaId: AgentId;
  projectId?: number | null;
}

interface UseChatSessionsOutput {
  chatSessions: ChatSession[];
  currentChatSessionId: string | null;
  currentChatSession: ChatSession | null;
  agentForCurrentChatSession: MinimalPersonaSnapshot | null;
  isLoading: boolean;
  error: any;
  refreshChatSessions: () => Promise<ChatSessionsResponse[] | undefined>;
  addPendingChatSession: (params: PendingChatSessionParams) => void;
  removeSession: (sessionId: string) => void;
  hasMore: boolean;
  isLoadingMore: boolean;
  loadMore: () => void;
}

// ---------------------------------------------------------------------------
// Shared module-level store for pending chat sessions
// ---------------------------------------------------------------------------
// Pending sessions are optimistic new sessions shown in the sidebar before
// the server returns them. This must be module-level so all hook instances
// (sidebar, ChatButton, etc.) share the same state.

const pendingSessionsStore = {
  sessions: new Map<string, ChatSession>(),
  listeners: new Set<() => void>(),
  cachedSnapshot: [] as ChatSession[],

  add(session: ChatSession) {
    this.sessions.set(session.id, session);
    this.updateSnapshot();
    this.notify();
  },

  remove(sessionId: string) {
    if (this.sessions.delete(sessionId)) {
      this.updateSnapshot();
      this.notify();
    }
  },

  has(sessionId: string): boolean {
    return this.sessions.has(sessionId);
  },

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  },

  notify() {
    this.listeners.forEach((listener) => listener());
  },

  updateSnapshot() {
    this.cachedSnapshot = Array.from(this.sessions.values());
  },

  getSnapshot(): ChatSession[] {
    return this.cachedSnapshot;
  },
};

// Stable empty array for SSR
const EMPTY_SESSIONS: ChatSession[] = [];

function usePendingSessions(): ChatSession[] {
  return useSyncExternalStore(
    (callback) => pendingSessionsStore.subscribe(callback),
    () => pendingSessionsStore.getSnapshot(),
    () => EMPTY_SESSIONS
  );
}

// ---------------------------------------------------------------------------
// Helper hooks
// ---------------------------------------------------------------------------

function useFindAgentForCurrentChatSession(
  currentChatSession: ChatSession | null
): MinimalPersonaSnapshot | null {
  const { agents } = useAgents();
  const appFocus = useAppFocus();

  let agentIdToFind: AgentId;

  // This could be an alreaady existing chat session.
  if (currentChatSession) {
    agentIdToFind = currentChatSession.persona_id;
  }

  // This could be a new chat-session. Therefore, `currentChatSession` is false, but there could still be some agent.
  else if (appFocus.isNewSession()) {
    agentIdToFind = DEFAULT_AGENT_ID;
  }

  // Or this could be a new chat-session with an agent.
  else if (appFocus.isAgent()) {
    agentIdToFind = appFocus.getId()!;
  }

  return agents.find((agent) => agentIdsMatch(agent, agentIdToFind)) ?? null;
}

// ---------------------------------------------------------------------------
// Main hook
// ---------------------------------------------------------------------------

export default function useChatSessions(): UseChatSessionsOutput {
  const getKey = (
    pageIndex: number,
    previousPageData: ChatSessionsResponse | null
  ): string | null =>
    getChatSessionsPageKey(pageIndex, previousPageData, PAGE_SIZE);

  const { data, error, setSize, mutate } = useSWRInfinite<ChatSessionsResponse>(
    getKey,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      revalidateFirstPage: true,
      revalidateAll: false,
      dedupingInterval: 30000,
    }
  );

  const appFocus = useAppFocus();
  const pendingSessions = usePendingSessions();

  // Flatten all pages into a single session list
  const allFetchedSessions = useMemo(
    () =>
      data
        ? data.flatMap((page) =>
            Array.isArray(page?.sessions)
              ? page.sessions.filter(isValidChatSession)
              : []
          )
        : [],
    [data]
  );

  // hasMore: check the last loaded page
  const hasMore = useMemo(() => {
    if (!data || data.length === 0) return false;
    const lastPage = data[data.length - 1];
    return lastPage ? lastPage.has_more : false;
  }, [data]);

  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const loadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore) return;

    setIsLoadingMore(true);
    const loadStart = Date.now();

    try {
      await setSize((s) => s + 1);

      // Enforce minimum loading duration to avoid skeleton flash
      const elapsed = Date.now() - loadStart;
      if (elapsed < MIN_LOADING_DURATION_MS) {
        await new Promise((r) =>
          setTimeout(r, MIN_LOADING_DURATION_MS - elapsed)
        );
      }
    } catch (err) {
      console.error("Failed to load more chat sessions:", err);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMore, setSize]);

  // Clean up pending sessions that now appear in fetched data
  // (they now have messages and the server returns them)
  useEffect(() => {
    const fetchedIds = new Set(allFetchedSessions.map((s) => s.id));
    pendingSessions.forEach((pending) => {
      if (fetchedIds.has(pending.id)) {
        pendingSessionsStore.remove(pending.id);
      }
    });
  }, [allFetchedSessions, pendingSessions]);

  // Merge fetched sessions with pending sessions.
  // This ensures pending sessions persist across SWR revalidations.
  const chatSessions = useMemo(() => {
    const fetchedIds = new Set(allFetchedSessions.map((s) => s.id));

    // Get pending sessions that are not yet in fetched data
    const remainingPending = pendingSessions.filter(
      (pending) => !fetchedIds.has(pending.id)
    );

    // Pending sessions go first (most recent), then fetched sessions
    return mergeChatSessionsByFreshness([
      ...remainingPending,
      ...allFetchedSessions,
    ]);
  }, [allFetchedSessions, pendingSessions]);

  const currentChatSessionId = appFocus.isChat() ? appFocus.getId() : null;
  const currentChatSession =
    chatSessions.find(
      (chatSession) => chatSession.id === currentChatSessionId
    ) ?? null;

  const agentForCurrentChatSession =
    useFindAgentForCurrentChatSession(currentChatSession);

  // Add a pending chat session that will persist across SWR revalidations.
  // The session will be automatically removed once it appears in the server response.
  const addPendingChatSession = useCallback(
    ({ chatSessionId, personaId, projectId }: PendingChatSessionParams) => {
      // Don't add sessions that belong to a project
      if (projectId != null) return;

      // Don't add if already in pending store (duplicates are also filtered during merge)
      if (pendingSessionsStore.has(chatSessionId)) return;

      const now = new Date().toISOString();
      pendingSessionsStore.add({
        id: chatSessionId,
        name: "", // Empty name will display as "New Chat" via UNNAMED_CHAT constant
        persona_id: personaId,
        time_created: now,
        time_updated: now,
        last_message_at: now,
        last_accessed_at: null,
        shared_status: ChatSessionSharedStatus.Private,
        project_id: projectId ?? null,
        current_alternate_model: "",
        current_temperature_override: null,
      });
    },
    []
  );

  const removeSession = useCallback(
    (sessionId: string) => {
      pendingSessionsStore.remove(sessionId);
      // Optimistically remove from all loaded pages
      mutate(
        (pages) =>
          pages?.map((page) => ({
            ...page,
            sessions: (page.sessions || []).filter(
              (s) => isValidChatSession(s) && s.id !== sessionId
            ),
          })),
        { revalidate: false }
      );
    },
    [mutate]
  );

  const refreshChatSessions = useCallback(() => mutate(), [mutate]);

  return {
    chatSessions,
    currentChatSessionId,
    currentChatSession,
    agentForCurrentChatSession,
    isLoading: !error && !data,
    error,
    refreshChatSessions,
    addPendingChatSession,
    removeSession,
    hasMore,
    isLoadingMore,
    loadMore,
  };
}
