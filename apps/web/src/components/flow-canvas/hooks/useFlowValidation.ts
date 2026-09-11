/**
 * Debounced client-side validation against
 * `POST /agent-definitions/validate-flow` — an affordance (blocks the
 * Publish button, paints issues onto nodes/edges), not the actual gate:
 * `publish_flow` validates server-side regardless of client state (design
 * spec §10), so a stale client can never publish an invalid flow.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { useEffect, useMemo, useState } from "react";
import type { StoreApi } from "zustand";
import type { FlowStore } from "../stores/flowStore";
import type { ValidationIssue } from "../types/flow";
import { toFlowSpec } from "../utils/compile";
import { flowApi } from "@/components/flow-canvas/api/flowApi";

export type { ValidationIssue };

export type ValidationResponse = {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
};

function groupById(
  issues: ValidationIssue[],
  key: "node_id" | "edge_id"
): Map<string, ValidationIssue[]> {
  const map = new Map<string, ValidationIssue[]>();
  for (const issue of issues) {
    const id = issue[key];
    if (!id) continue;
    const existing = map.get(id);
    if (existing) existing.push(issue);
    else map.set(id, [issue]);
  }
  return map;
}

function groupByNodeIdRecord(
  issues: ValidationIssue[]
): Record<string, ValidationIssue[]> {
  const record: Record<string, ValidationIssue[]> = {};
  for (const issue of issues) {
    if (!issue.node_id) continue;
    (record[issue.node_id] ??= []).push(issue);
  }
  return record;
}

export type UseFlowValidationOptions = {
  debounceMs?: number;
};

export function useFlowValidation(
  store: StoreApi<FlowStore>,
  { debounceMs = 800 }: UseFlowValidationOptions = {}
) {
  const [result, setResult] = useState<ValidationResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    async function runValidation() {
      const { nodes, edges, viewport } = store.getState();
      const spec = toFlowSpec(nodes, edges, viewport);
      setIsValidating(true);
      try {
        const res = await fetch(flowApi.validate(), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ flow_spec: spec }),
        });
        if (!cancelled && res.ok) {
          const body = (await res.json()) as ValidationResponse;
          setResult(body);
          // Written into the store (not just returned locally) so
          // TemplateNode — instantiated well before this hook exists,
          // via its own store-bound factory — can reactively paint the
          // node red without a new prop threaded through `nodeTypes`.
          store.getState().setNodeErrors(groupByNodeIdRecord(body.errors));
        }
      } finally {
        if (!cancelled) setIsValidating(false);
      }
    }

    // Validate once on mount, then re-validate on a debounce after every
    // structural change — same "settle before hitting the network"
    // reasoning as useFlowDraft's autosave.
    void runValidation();

    const unsubscribe = store.subscribe((state, prevState) => {
      // runValidation's own result is written back via setNodeErrors —
      // a store change like any other, which an unconditional subscriber
      // would mistake for a fresh edit and re-arm itself over. Since
      // setNodeErrors never touches nodes/edges/viewport, gating on those
      // three staying referentially equal is what breaks that loop, while
      // still catching every real edit (setNodes/onNodesChange/
      // setNodeValues always replace at least one of them).
      if (
        state.nodes === prevState.nodes &&
        state.edges === prevState.edges &&
        state.viewport === prevState.viewport
      ) {
        return;
      }
      if (timer) clearTimeout(timer);
      timer = setTimeout(runValidation, debounceMs);
    });

    return () => {
      cancelled = true;
      unsubscribe();
      if (timer) clearTimeout(timer);
    };
  }, [store, debounceMs]);

  const errorsByNode = useMemo(
    () => groupById(result?.errors ?? [], "node_id"),
    [result]
  );
  const errorsByEdge = useMemo(
    () => groupById(result?.errors ?? [], "edge_id"),
    [result]
  );
  const warningsByNode = useMemo(
    () => groupById(result?.warnings ?? [], "node_id"),
    [result]
  );

  return {
    result,
    isValidating,
    hasErrors: (result?.errors.length ?? 0) > 0,
    errorsByNode,
    errorsByEdge,
    warningsByNode,
  };
}
