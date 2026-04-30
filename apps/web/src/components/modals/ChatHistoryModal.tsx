"use client";

import React, { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { ChatSession, ChatSessionSharedStatus } from "@/app/app/interfaces";
import { deleteChatSession, deleteAllChatSessions } from "@/app/app/services/lib";
import { errorHandlingFetcher } from "@/lib/fetcher";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import { showErrorNotification } from "@/sections/sidebar/sidebarUtils";
import { UNNAMED_CHAT } from "@/lib/constants";
import {
  SvgTrash,
  SvgX,
  SvgCheck,
  SvgEditBig,
  SvgChevronLeft,
  SvgChevronRight,
} from "@opal/icons";

function dedupeChatHistorySessions(sessions: ChatSession[]): ChatSession[] {
  const byId = new Map<string, ChatSession>();
  for (const session of sessions) {
    const existing = byId.get(session.id);
    if (!existing) {
      byId.set(session.id, session);
      continue;
    }
    const existingTime = existing.time_updated || "";
    const currentTime = session.time_updated || "";
    if (currentTime >= existingTime) {
      byId.set(session.id, session);
    }
  }

  return Array.from(byId.values()).sort(
    (left, right) =>
      new Date(right.time_updated || 0).getTime() -
      new Date(left.time_updated || 0).getTime()
  );
}

interface ChatHistoryResponse {
  sessions: ChatSession[];
  chat_sessions: ChatSession[];
  has_more: boolean;
}

interface ChatHistoryModalProps {
  open: boolean;
  onClose: () => void;
  onSelectChat: (chatId: string) => void;
  onRefresh: () => void;
}

export default function ChatHistoryModal({
  open,
  onClose,
  onSelectChat,
  onRefresh,
}: ChatHistoryModalProps) {
  const [selectedChats, setSelectedChats] = useState<Set<string>>(new Set());
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [deleteAllModalOpen, setDeleteAllModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  // Fetch all chat sessions
  const { data, mutate, isLoading } = useSWR<ChatHistoryResponse>(
    `/api/chat/get-user-chat-sessions?page_size=${PAGE_SIZE}`,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: true,
    }
  );

  const allSessions = dedupeChatHistorySessions(data?.sessions || []);
  const hasMore = data?.has_more || false;

  // Reset selection when modal opens
  useEffect(() => {
    if (open) {
      setSelectedChats(new Set());
      setIsSelectionMode(false);
      setPage(0);
      mutate();
    }
  }, [open, mutate]);

  const handleToggleSelect = useCallback((chatId: string) => {
    setSelectedChats((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(chatId)) {
        newSet.delete(chatId);
      } else {
        newSet.delete("__select_all__");
        newSet.add(chatId);
      }
      return newSet;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    if (selectedChats.has("__select_all__")) {
      setSelectedChats(new Set());
    } else {
      setSelectedChats(new Set(["__select_all__", ...allSessions.map((s) => s.id)]));
    }
  }, [allSessions, selectedChats]);

  const handleDeleteSelected = useCallback(async () => {
    if (selectedChats.size === 0) return;

    setIsDeleting(true);
    try {
      const chatIds = Array.from(selectedChats).filter((id) => id !== "__select_all__");
      for (const chatId of chatIds) {
        await deleteChatSession(chatId);
      }
      setSelectedChats(new Set());
      setIsSelectionMode(false);
      mutate();
      onRefresh();
    } catch (error) {
      console.error("Failed to delete selected chats:", error);
      showErrorNotification("Failed to delete some chats. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }, [selectedChats, mutate, onRefresh]);

  const handleDeleteAll = useCallback(async () => {
    setIsDeleting(true);
    try {
      await deleteAllChatSessions();
      setSelectedChats(new Set());
      setIsSelectionMode(false);
      setDeleteAllModalOpen(false);
      mutate();
      onRefresh();
    } catch (error) {
      console.error("Failed to delete all chats:", error);
      showErrorNotification("Failed to delete all chats. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }, [mutate, onRefresh]);

  const handleSelect = useCallback(
    (chatId: string) => {
      onSelectChat(chatId);
      onClose();
    },
    [onSelectChat, onClose]
  );

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return "";
    try {
      const date = new Date(dateString);
      return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    } catch {
      return "";
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Modal Overlay */}
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        {/* Backdrop */}
        <div
          className="absolute inset-0 bg-black/50"
          onClick={onClose}
        />

        {/* Modal Content */}
        <div className="relative z-10 flex h-[80vh] w-[90vw] max-w-4xl flex-col rounded-lg bg-white shadow-xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <div className="flex items-center gap-3">
              {isSelectionMode ? (
                <>
                  <IconButton
                    icon={SvgChevronLeft}
                    onClick={() => {
                      setIsSelectionMode(false);
                      setSelectedChats(new Set());
                    }}
                  />
                  <span className="text-lg font-semibold">
                    {selectedChats.size > 0
                      ? `${selectedChats.size} selected`
                      : "Select chats"}
                  </span>
                </>
              ) : (
                <>
                  <h2 className="text-lg font-semibold">Chat History</h2>
                  <span className="text-sm text-gray-500">
                    {allSessions.length} chats
                  </span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              {isSelectionMode ? (
                <>
                  <Button
                    onClick={handleDeleteSelected}
                    disabled={selectedChats.size === 0 || isDeleting}
                    danger
                  >
                    <SvgTrash className="mr-2 h-4 w-4" />
                    Delete Selected
                  </Button>
                  <IconButton icon={SvgX} onClick={onClose} />
                </>
              ) : (
                <>
                  <Button
                    onClick={() => setIsSelectionMode(true)}
                    secondary
                  >
                    Select
                  </Button>
                  <Button
                    onClick={() => setDeleteAllModalOpen(true)}
                    secondary
                    disabled={allSessions.length === 0}
                  >
                    <SvgTrash className="mr-2 h-4 w-4" />
                    Delete All
                  </Button>
                  <IconButton icon={SvgX} onClick={onClose} />
                </>
              )}
            </div>
          </div>

          {/* Chat List */}
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex h-full items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-solid border-gray-200 border-t-primary" />
              </div>
            ) : allSessions.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <div className="text-center text-gray-500">
                  <SvgEditBig className="mx-auto mb-2 h-12 w-12 text-gray-300" />
                  <p>No chat sessions yet</p>
                  <p className="text-sm">Start a new conversation to see it here</p>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {/* Select All Row */}
                {isSelectionMode && (
                  <div className="flex items-center gap-3 bg-gray-50 px-6 py-3">
                    <Checkbox
                      checked={selectedChats.has("__select_all__")}
                      onChange={handleSelectAll}
                    />
                    <span className="text-sm font-medium">Select all</span>
                  </div>
                )}

                {/* Chat Rows */}
                {allSessions.map((session) => {
                  const isSelected = selectedChats.has(session.id);
                  return (
                    <div
                      key={session.id}
                      className={`flex items-center gap-3 px-6 py-3 hover:bg-gray-50 ${
                        isSelected ? "bg-primary/5" : ""
                      }`}
                    >
                      {isSelectionMode && (
                        <Checkbox
                          checked={isSelected}
                          onChange={() => handleToggleSelect(session.id)}
                        />
                      )}
                      <div
                        className={`flex flex-1 cursor-pointer flex-col ${
                          isSelectionMode ? "" : "hover:text-primary"
                        }`}
                        onClick={() =>
                          isSelectionMode
                            ? handleToggleSelect(session.id)
                            : handleSelect(session.id)
                        }
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            {session.name || session.description || UNNAMED_CHAT}
                          </span>
                          <span className="text-sm text-gray-500">
                            {formatDate(session.time_updated)}
                          </span>
                        </div>
                        {session.persona_id !== null && session.persona_id !== 0 && (
                          <span className="text-xs text-gray-400">
                            Agent ID: {session.persona_id}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}

                {/* Load More */}
                {hasMore && (
                  <div className="flex justify-center py-4">
                    <Button
                      onClick={() => setPage((p) => p + 1)}
                      secondary
                    >
                      Load More
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delete All Confirmation Modal */}
      {deleteAllModalOpen && (
        <ConfirmationModalLayout
          title="Delete All Chats"
          icon={SvgTrash}
          onClose={() => setDeleteAllModalOpen(false)}
          submit={
            <Button
              danger
              onClick={handleDeleteAll}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete All"}
            </Button>
          }
        >
          <p>
            Are you sure you want to delete all {allSessions.length} chat sessions?
            This action cannot be undone.
          </p>
        </ConfirmationModalLayout>
      )}
    </>
  );
}
