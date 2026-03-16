"use client";

import { cn } from "@/lib/utils";
import { Message, Thread } from "@langchain/langgraph-sdk";
import { useEffect, useState, forwardRef, ForwardedRef, useCallback } from "react";
import { useQueryState } from "nuqs";
import { createClient } from "@/lib/client";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";

import { useAuthContext } from "@/providers/Auth";
import { MessageContent } from "@langchain/core/messages";
import { FileClock, RefreshCw } from "lucide-react";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { Button } from "@/components/ui/button";

const getMessageStringContent = (
  content: MessageContent | undefined,
): string => {
  if (!content) return "";
  if (typeof content === "string") return content;
  const texts = content
    .filter((c): c is { type: "text"; text: string } => c.type === "text")
    .map((c) => c.text);
  return texts.join(" ");
};

/**
 * Returns the first human message from a thread
 * @param thread The thread to get the first human message from
 * @returns The first human message content, or an empty string if no human message is found
 */
function getFirstHumanMessageContent(thread: Thread) {
  try {
    if (!thread.values) return "";

    // Check for input string first as it might be simpler
    if ("input" in thread.values && typeof thread.values.input === "string") {
      return thread.values.input;
    }

    if (
      "messages" in thread.values &&
      Array.isArray(thread.values.messages) &&
      thread.values.messages.length > 0
    ) {
      const castMessages = thread.values.messages as Message[];
      const firstHumanMsg = castMessages.find((msg) => msg.type === "human");
      const content = getMessageStringContent(firstHumanMsg?.content);
      if (content) return content;
    }

    return "";
  } catch (e) {
    console.error("Failed to get human message from thread", {
      thread,
      error: e,
    });
    return "";
  }
}

const formatDate = (date: string) => {
  try {
    return new Intl.DateTimeFormat("tr-TR", {
      timeZone: "Europe/Istanbul",
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(date));
  } catch (e) {
    console.error("Failed to format date", { date, error: e });
    return "";
  }
};

export interface ThreadHistorySidebarProps {
  className?: string;
  open: boolean;
  setOpen: (open: boolean) => void;
}

export const ThreadHistorySidebar = forwardRef<
  HTMLDivElement,
  ThreadHistorySidebarProps
>(({ className, open, setOpen }, ref: ForwardedRef<HTMLDivElement>) => {
  const { session } = useAuthContext();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadId, setThreadId] = useQueryState("threadId");
  const [agentId] = useQueryState("agentId");
  const [deploymentId] = useQueryState("deploymentId");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  
  // Get stream context to watch for new messages
  const stream = useStreamContext();
  const isStreaming = stream.isLoading;
  const messages = stream.messages;

  const fetchThreads = useCallback(async (
    _agentId: string,
    _deploymentId: string,
    accessToken: string,
    showLoadingState: boolean = true,
  ) => {
    if (showLoadingState) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      const client = createClient(_deploymentId, accessToken);

      const threads = await client.threads.search({
        limit: 100,
        metadata: {
          assistant_id: _agentId,
        },
      });
      setThreads(threads);
    } catch (e) {
      console.error("Failed to fetch threads", e);
      if (showLoadingState) {
        toast.error("Failed to fetch threads");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    if (!agentId || !deploymentId || !session?.accessToken) return;
    fetchThreads(agentId, deploymentId, session.accessToken, true);
  }, [agentId, deploymentId, session?.accessToken, fetchThreads]);

  // Refresh when streaming ends (new message completed)
  useEffect(() => {
    const accessToken = session?.accessToken;
    if (!agentId || !deploymentId || !accessToken) return;
    // When streaming ends and we have messages, refresh the thread list
    if (!isStreaming && messages.length > 0) {
      // Small delay to ensure backend has saved the thread
      const timer = setTimeout(() => {
        fetchThreads(agentId, deploymentId, accessToken, false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, messages.length, agentId, deploymentId, session?.accessToken, fetchThreads]);

  const handleRefresh = () => {
    if (!agentId || !deploymentId || !session?.accessToken) return;
    fetchThreads(agentId, deploymentId, session.accessToken, false);
  };

  const handleChangeThread = (id: string) => {
    if (threadId === id) return;
    setThreadId(id);
    setOpen(false);
  };

  return (
    <div
      ref={ref}
      className={cn(
        "fixed top-0 right-0 z-10 h-screen border-l border-gray-200 bg-white shadow-lg transition-all duration-300",
        open ? "w-80 md:w-xl" : "w-0 overflow-hidden border-l-0",
        className,
      )}
    >
      {open && (
        <div className="flex h-full flex-col">
          <div className="flex flex-shrink-0 items-center justify-between border-b border-gray-200 p-4">
            <h2 className="text-lg font-semibold">History</h2>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="h-8 w-8"
            >
              <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
            </Button>
          </div>

          {loading ? (
            <div className="flex flex-1 items-center justify-center p-4">
              {Array.from({ length: 10 }).map((_, index) => (
                <Skeleton
                  key={`thread-loading-${index}`}
                  className="h-8 w-full"
                />
              ))}
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto">
              {threads.length === 0 && (
                <div className="flex h-full flex-1 items-center justify-center gap-2">
                  <FileClock className="size-6" />
                  <p>No threads found</p>
                </div>
              )}
              {threads.map((thread) => {
                const isSelected = thread.thread_id === threadId;
                return (
                  <div
                    key={thread.thread_id}
                    className={cn(
                      "flex items-center justify-between p-4 transition-all duration-300 hover:cursor-pointer hover:bg-gray-50",
                      isSelected
                        ? "bg-gray-100 hover:cursor-default hover:bg-gray-100"
                        : "",
                    )}
                    onClick={() => handleChangeThread(thread.thread_id)}
                  >
                    <div className="flex items-center gap-2">
                      <div className="size-2 rounded-full bg-gray-200" />
                      <div className="flex flex-col">
                        {/* Use the first human message as the title */}
                        <p className="line-clamp-1 truncate text-sm font-medium">
                          {getFirstHumanMessageContent(thread) ||
                            thread.thread_id}
                        </p>
                        <p className="text-sm text-gray-500">
                          {formatDate(thread.created_at)}
                        </p>
                      </div>
                    </div>
                    {/* TODO: Add save/delete buttons back if needed */}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

ThreadHistorySidebar.displayName = "ThreadHistorySidebar";
