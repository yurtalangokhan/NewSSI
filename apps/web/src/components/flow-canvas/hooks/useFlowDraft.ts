/**
 * Loads a flow-backed agent definition's draft into the canvas on mount,
 * and autosaves it back on a debounce. No direct Langflow equivalent —
 * Langflow's build/run cycle has no separate "draft" persistence step.
 *
 * Autosave writes the **draft only** (`PUT .../flow/draft`) — it can
 * never change what production runs (P3's core guarantee, Task 15.8).
 * `FlowDraftApi` is injectable so tests exercise the debounce/error paths
 * without a real network call, matching this project's DI convention
 * throughout flow-canvas (`HandleTypeLookup`, `createFlowStore()`, etc.).
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { useEffect, useState } from "react";
import type { StoreApi } from "zustand";
import type { FlowStore } from "../stores/flowStore";
import { fromFlowSpec, toFlowSpec } from "../utils/compile";
import type { WireFlowSpec } from "../types/flow";
import { flowApi } from "@/components/flow-canvas/api/flowApi";

export type FlowDraftApi = {
  loadDraft: (definitionId: string) => Promise<WireFlowSpec | null>;
  saveDraft: (definitionId: string, spec: WireFlowSpec) => Promise<void>;
};

async function defaultLoadDraft(
  definitionId: string
): Promise<WireFlowSpec | null> {
  const res = await fetch(flowApi.draft(definitionId), {
    credentials: "include",
  });
  if (res.status === 404) return loadPublishedAsDraftSeed(definitionId);
  if (!res.ok) throw new Error(`Failed to load draft: ${res.status}`);
  return res.json();
}

/**
 * Publishing *consumes* the draft row (the server promotes it rather than
 * copying it), so "no draft" is the normal state of a freshly published
 * flow — as it is after discarding a draft on exit. Opening the studio on
 * an empty canvas in that state was not just confusing: the next flush
 * persisted the emptiness as a brand-new draft, and version history then
 * showed a draft with every node removed. Seeding from what is published
 * means the canvas always opens on the flow that actually runs.
 *
 * Still null when nothing has ever been published — a genuinely new flow
 * whose seed spec `createFlow` writes has yet to arrive.
 */
async function loadPublishedAsDraftSeed(
  definitionId: string
): Promise<WireFlowSpec | null> {
  const res = await fetch(flowApi.published(definitionId), {
    credentials: "include",
  });
  if (!res.ok) return null;
  return res.json();
}

/**
 * An empty canvas is never worth persisting: the flow validator requires
 * a Chat Input node, so an empty draft can never be published, and every
 * legitimate way to reach an empty canvas (a failed load, a load still in
 * flight) is one where writing it would destroy the stored draft. This is
 * the backstop that makes that write impossible, whichever path fires it
 * — the debounced autosave, the exit guard, or the unload flush.
 */
function isEmptyCanvas(spec: WireFlowSpec): boolean {
  return (spec.nodes?.length ?? 0) === 0;
}

async function defaultSaveDraft(
  definitionId: string,
  spec: WireFlowSpec
): Promise<void> {
  const res = await fetch(flowApi.draft(definitionId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ flow_spec: spec }),
  });
  if (!res.ok) throw new Error(`Failed to save draft: ${res.status}`);
}

const DEFAULT_API: FlowDraftApi = {
  loadDraft: defaultLoadDraft,
  saveDraft: defaultSaveDraft,
};

export type UseFlowDraftOptions = {
  api?: FlowDraftApi;
  /** P3 Task 19 coalesces `flow:updated` audit events server-side at 60s
   * — a client debounce far below that produces version-row churn with
   * no audit value, but must still feel responsive. 3s, not tunable via
   * product decision yet — see task-28-report.md. */
  debounceMs?: number;
};

export function useFlowDraft(
  definitionId: string,
  store: StoreApi<FlowStore>,
  { api = DEFAULT_API, debounceMs = 3000 }: UseFlowDraftOptions = {}
) {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    api
      .loadDraft(definitionId)
      .then((spec) => {
        if (cancelled || !spec) return;
        const { nodes, edges, viewport } = fromFlowSpec(spec);
        store.getState().setNodes(nodes);
        store.getState().setEdges(edges);
        store.getState().setViewport(viewport);
        store.getState().resetDirty();
      })
      .catch((err) => {
        if (!cancelled)
          setLoadError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Re-run only when the definition itself changes, not on every store
    // mutation — `api`/`store` are stable across a mount.
  }, [definitionId]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function saveNow() {
      // Task 45: a timer armed *before* a version preview started must not
      // fire *into* it — saveNow would read the previewed historical spec
      // out of the store and silently overwrite the user's draft with it.
      if (store.getState().isPreviewMode) return;
      const { nodes, edges, viewport } = store.getState();
      const spec = toFlowSpec(nodes, edges, viewport);
      if (isEmptyCanvas(spec)) return;
      setIsSaving(true);
      try {
        await api.saveDraft(definitionId, spec);
        setSaveError(null);
        store.getState().resetDirty();
      } catch (err) {
        setSaveError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        setIsSaving(false);
      }
    }

    // Every dirtying mutation re-arms the timer (not just the first) —
    // otherwise a burst of edits fires the debounce once per burst-start
    // rather than once per burst-end, defeating the point of debouncing.
    const unsubscribe = store.subscribe((state) => {
      if (!state.isDirty || state.isPreviewMode) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(saveNow, debounceMs);
    });

    return () => {
      unsubscribe();
      if (timer) clearTimeout(timer);
    };
  }, [definitionId, store, api, debounceMs]);

  return { isLoading, loadError, isSaving, saveError };
}

/**
 * Task 45 — publish-consumes-draft parity. Publishing archives the draft row
 * (P3 Task 16), which would leave the playground with nothing to run until
 * the user happened to edit something and autosave recreated the draft.
 * VersionBar calls this immediately after a successful publish so the just-
 * published spec also exists again as the new draft row.
 */
export async function saveDraftNow(
  definitionId: string,
  store: StoreApi<FlowStore>
): Promise<void> {
  const { nodes, edges, viewport } = store.getState();
  const spec = toFlowSpec(nodes, edges, viewport);
  if (isEmptyCanvas(spec)) return;
  await DEFAULT_API.saveDraft(definitionId, spec);
  store.getState().resetDirty();
}

/**
 * Throw away the working draft server-side.
 *
 * Idempotent by contract with the API (204 whether or not a draft
 * existed), so a double-click on "discard changes" is harmless.
 */
export async function discardDraft(definitionId: string): Promise<void> {
  const res = await fetch(flowApi.draft(definitionId), {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to discard draft: ${res.status}`);
  }
}
