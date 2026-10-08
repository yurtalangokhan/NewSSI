"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import useDebouncedValue from "@/hooks/useDebouncedValue";
import { buildAppPath } from "@/hooks/appNavigation";
import { useChatHistoryList } from "@/lib/api/domains/chat/history-hooks";
import { ChatSession } from "@/lib/api/domains/chat/types";
import { getChatSessionActivityTime } from "@/lib/chat/chatSessionActivity";
import { UNNAMED_CHAT } from "@/lib/constants";
import { formatMessageTime } from "@/lib/dateUtils";
import { groupSessionsByDay } from "@/sections/chat/chatHistoryGroups";
import { Button } from "@opal/components";
import { SvgBubbleText, SvgHistory } from "@opal/icons";
import Popover from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import TextSeparator from "@/refresh-components/TextSeparator";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import ChatSessionSkeleton from "@/refresh-components/skeletons/ChatSessionSkeleton";

/** Longest search text the sessions endpoint accepts (422 above this). */
export const MAX_CHAT_SEARCH_LENGTH = 200;
const SEARCH_DEBOUNCE_MS = 300;
const SKELETON_ROW_COUNT = 4;

interface ChatHistoryListProps {
  sessions: ChatSession[];
  currentChatSessionId: string | null;
  hasMore: boolean;
  isLoading: boolean;
  isLoadingMore: boolean;
  isSearching: boolean;
  hasError: boolean;
  retry: () => Promise<unknown>;
  loadMore: () => Promise<void>;
  onSelect: () => void;
}

function ChatHistoryList({
  sessions,
  currentChatSessionId,
  hasMore,
  isLoading,
  isLoadingMore,
  isSearching,
  hasError,
  retry,
  loadMore,
  onSelect,
}: ChatHistoryListProps) {
  const { t, i18n } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // The sentinel sits under the last row. Re-arming after every page means a
  // page too short to fill the menu keeps loading until it scrolls.
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!hasMore || !sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void loadMore();
        }
      },
      { root: scrollRef.current }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadMore, sessions.length]);

  if (isLoading) {
    return (
      <div
        role="status"
        aria-label={t("common.loading")}
        className="flex flex-col"
      >
        {Array.from({ length: SKELETON_ROW_COUNT }, (_, index) => (
          <ChatSessionSkeleton key={index} />
        ))}
      </div>
    );
  }

  if (hasError && sessions.length === 0) {
    return (
      <div
        role="alert"
        className="flex items-center justify-between gap-2 px-2 py-1"
      >
        <Text text03 secondaryBody>
          {t("sidebar.chatHistoryError")}
        </Text>
        <Button prominence="tertiary" onClick={() => void retry()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <Text text03 secondaryBody className="px-2 py-1">
        {isSearching
          ? t("sidebar.chatHistoryNoResults")
          : t("sidebar.chatHistoryEmpty")}
      </Text>
    );
  }

  const groups = groupSessionsByDay(sessions, i18n.language, t);

  // Height follows the popover's available space so short viewports scroll.
  return (
    <div
      ref={scrollRef}
      className="max-h-[min(20rem,calc(var(--radix-popover-content-available-height)-5rem))] overflow-y-auto"
    >
      {groups.map((group) => (
        <div key={group.key}>
          {group.label && (
            <TextSeparator text={group.label} className="px-2 py-1" />
          )}
          {group.sessions.map((session) => {
            const time = formatMessageTime(
              getChatSessionActivityTime(session),
              i18n.language
            );
            return (
              <LineItem
                key={session.id}
                icon={SvgBubbleText}
                href={buildAppPath({ type: "chat", id: session.id })}
                selected={session.id === currentChatSessionId}
                onClick={onSelect}
                rightChildren={
                  time && (
                    // Out of the flow until hovered, so the name only gives up
                    // room to the time while the pointer is on the row.
                    <div className="hidden group-hover/LineItem:block group-focus-visible/LineItem:block">
                      <Text as="p" secondaryBody text03 nowrap>
                        {time}
                      </Text>
                    </div>
                  )
                }
              >
                {session.name || UNNAMED_CHAT}
              </LineItem>
            );
          })}
        </div>
      ))}
      {hasMore && <div ref={sentinelRef} className="h-px" />}
      {isLoadingMore && (
        <div
          role="status"
          aria-label={t("common.loading")}
          className="flex justify-center py-2"
        >
          <SimpleLoader />
        </div>
      )}
    </div>
  );
}

interface ChatHistoryDropdownProps {
  currentChatSessionId: string | null;
}

/**
 * Header menu for jumping between earlier agent and flow chats. Paging and
 * search are served by the backend; nothing is fetched until the menu opens.
 */
export default function ChatHistoryDropdown({
  currentChatSessionId,
}: ChatHistoryDropdownProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const query = useDebouncedValue(search, SEARCH_DEBOUNCE_MS);

  const {
    sessions,
    hasMore,
    isLoading,
    isLoadingMore,
    error,
    loadMore,
    retry,
  } = useChatHistoryList({ query, enabled: open });

  function handleOpenChange(state: boolean) {
    setOpen(state);
    if (!state) setSearch("");
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <Popover.Trigger asChild>
        <div>
          <Button
            icon={SvgHistory}
            prominence="tertiary"
            transient={open}
            responsiveHideText
            aria-label={t("sidebar.chatHistory")}
            data-testid="chat-history-button"
          >
            {t("sidebar.chatHistory")}
          </Button>
        </div>
      </Popover.Trigger>
      <Popover.Content side="bottom" align="end" width="xl">
        <div className="flex flex-col gap-2 p-1">
          <InputTypeIn
            leftSearchIcon
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => setSearch("")}
            maxLength={MAX_CHAT_SEARCH_LENGTH}
            placeholder={t("sidebar.chatHistorySearchPlaceholder")}
          />
          <ChatHistoryList
            sessions={sessions}
            currentChatSessionId={currentChatSessionId}
            hasMore={hasMore}
            isLoading={isLoading}
            isLoadingMore={isLoadingMore}
            isSearching={query.trim().length > 0}
            hasError={Boolean(error)}
            retry={retry}
            loadMore={loadMore}
            onSelect={() => handleOpenChange(false)}
          />
        </div>
      </Popover.Content>
    </Popover>
  );
}
