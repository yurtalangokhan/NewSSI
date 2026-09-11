import { useCallback, useEffect, useState } from "react";
import type { StoreApi } from "zustand";
import type { FlowStore } from "../stores/flowStore";
import { discardDraft, saveDraftNow } from "./useFlowDraft";

export type UseFlowExitGuardOptions = {
  definitionId: string;
  store: StoreApi<FlowStore>;
  /** Whether a draft row exists server-side — the "you have unpublished
   * work" signal. Autosave writes it, so it is equivalent to "the canvas
   * differs from what is published". */
  hasDraft: boolean;
  onExited: () => void;
};

/**
 * Guards the way out of the studio.
 *
 * Autosave means nothing is ever lost, so the question on exit is not
 * "save?" but "keep this draft or throw it away?". The browser's own back
 * button and tab close are not interceptable here; those paths just flush
 * the pending autosave, which lands on the non-destructive side.
 */
export function useFlowExitGuard({
  definitionId,
  store,
  hasDraft,
  onExited,
}: UseFlowExitGuardOptions) {
  const [isConfirmOpen, setConfirmOpen] = useState(false);
  const [isDiscarding, setDiscarding] = useState(false);

  const requestExit = useCallback(async () => {
    await saveDraftNow(definitionId, store);
    if (!hasDraft) {
      onExited();
      return;
    }
    setConfirmOpen(true);
  }, [definitionId, store, hasDraft, onExited]);

  const keepDraft = useCallback(async () => {
    await saveDraftNow(definitionId, store);
    setConfirmOpen(false);
    onExited();
  }, [definitionId, store, onExited]);

  const discardAndExit = useCallback(async () => {
    setDiscarding(true);
    try {
      await discardDraft(definitionId);
      setConfirmOpen(false);
      onExited();
    } finally {
      setDiscarding(false);
    }
  }, [definitionId, onExited]);

  const cancel = useCallback(() => setConfirmOpen(false), []);

  useEffect(() => {
    function flushOnUnload() {
      void saveDraftNow(definitionId, store);
    }
    window.addEventListener("beforeunload", flushOnUnload);
    return () => window.removeEventListener("beforeunload", flushOnUnload);
  }, [definitionId, store]);

  return {
    requestExit,
    isConfirmOpen,
    keepDraft,
    discardAndExit,
    cancel,
    isDiscarding,
  };
}
