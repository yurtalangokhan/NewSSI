"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWRInfinite from "swr/infinite";

import { fetchChatSessionsPage } from "@/lib/api/domains/chat/api";
import { ChatSession } from "@/lib/api/domains/chat/types";
import { getChatSessionsPageKey } from "@/lib/chat/chatSessionActivity";

const HISTORY_PAGE_SIZE = 20;

interface ChatHistoryPage {
  sessions: ChatSession[];
  has_more: boolean;
  next_cursor?: {
    before_activity?: string | null;
    before_id?: string | null;
  } | null;
}

interface UseChatHistoryListParams {
  /** Text the backend matches against session names. */
  query: string;
  /** Fetch only while the history menu is open. */
  enabled: boolean;
}

interface UseChatHistoryListOutput {
  sessions: ChatSession[];
  hasMore: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  error: unknown;
  loadMore: () => Promise<void>;
  retry: () => Promise<unknown>;
}

/**
 * Agent and flow chat history for the chat header menu.
 *
 * Paging and search both run on the backend; this hook keeps no full list in
 * memory. It is separate from `useChatSessions` on purpose: the sidebar list
 * merges optimistic pending sessions and must not see search-filtered pages.
 */
export function useChatHistoryList({
  query,
  enabled,
}: UseChatHistoryListParams): UseChatHistoryListOutput {
  const getKey = (
    pageIndex: number,
    previousPageData: ChatHistoryPage | null
  ): string | null =>
    enabled
      ? getChatSessionsPageKey(pageIndex, previousPageData, HISTORY_PAGE_SIZE, {
          query,
          agentsOnly: true,
        })
      : null;

  const { data, error, isLoading, setSize, mutate } =
    useSWRInfinite<ChatHistoryPage>(
      getKey,
      (url) => fetchChatSessionsPage<ChatHistoryPage>(url),
      { revalidateOnFocus: false, revalidateFirstPage: false }
    );

  // Cached pages are not refetched on their own (first-page revalidation is off
  // so loadMore stays one request), so refresh them each time the menu reopens.
  const wasEnabled = useRef(enabled);
  useEffect(() => {
    if (enabled && !wasEnabled.current) void mutate();
    wasEnabled.current = enabled;
  }, [enabled, mutate]);

  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Pages arrive in backend activity order; keep it, only drop repeats that a
  // session moving between pages would otherwise produce.
  const sessions = useMemo(() => {
    const seen = new Set<string>();
    return (data ?? [])
      .flatMap((page) => (Array.isArray(page?.sessions) ? page.sessions : []))
      .filter((session) => {
        if (!session?.id || seen.has(session.id)) return false;
        seen.add(session.id);
        return true;
      });
  }, [data]);

  const hasMore = Boolean(data?.[data.length - 1]?.has_more);

  const loadMore = useCallback(async () => {
    if (isLoadingMore || !hasMore) return;
    setIsLoadingMore(true);
    try {
      // SWR stores fetch failures in `error` rather than rejecting.
      await setSize((size) => size + 1);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMore, setSize]);

  return {
    sessions,
    hasMore,
    isLoading,
    isLoadingMore,
    error,
    loadMore,
    retry: mutate,
  };
}
