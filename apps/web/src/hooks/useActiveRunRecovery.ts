"use client";

import { useEffect, useRef } from "react";
import { fetchActiveRun } from "@/lib/api/domains/chat/api";
import type { ActiveRunInfo } from "@/lib/api/domains/chat/resumableChatStream";

interface UseActiveRunRecoveryProps {
  sessionId: string | null;
  /** True when the chat shows no stream of its own (state `input`). */
  isIdle: () => boolean;
  attach: (sessionId: string, run: ActiveRunInfo) => Promise<void>;
}

/**
 * Re-attaches an idle chat to a run that is still producing its answer when
 * the tab becomes visible again or the browser comes back online — the two
 * moments a stream is most likely to have been lost (a suspended background
 * tab, a dropped connection). An in-flight stream recovers by itself; this
 * only covers a chat that already gave up or never had one.
 */
export default function useActiveRunRecovery({
  sessionId,
  isIdle,
  attach,
}: UseActiveRunRecoveryProps) {
  // Read through refs so the listeners are registered once per session and
  // still see the latest callbacks.
  const isIdleRef = useRef(isIdle);
  const attachRef = useRef(attach);
  isIdleRef.current = isIdle;
  attachRef.current = attach;

  useEffect(() => {
    if (!sessionId) return;
    let inFlight = false;
    let disposed = false;

    const recover = async () => {
      if (inFlight || !isIdleRef.current()) return;
      inFlight = true;
      try {
        const run = await fetchActiveRun(sessionId);
        if (run && !disposed && isIdleRef.current()) {
          await attachRef.current(sessionId, run);
        }
      } catch (error) {
        console.error("Failed to recover the active chat run:", error);
      } finally {
        inFlight = false;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void recover();
    };
    const onOnline = () => {
      void recover();
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("online", onOnline);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("online", onOnline);
    };
  }, [sessionId]);
}
