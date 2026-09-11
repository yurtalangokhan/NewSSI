import { useEffect, useMemo } from "react";
import useSWR from "swr";
import type { StoreApi } from "zustand";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { fromFlowSpec } from "../utils/compile";
import type { WireFlowSpec } from "../types/flow";
import type { CanvasEdge, CanvasNode } from "../types/flow";
import type { FlowStore } from "../stores/flowStore";
import { flowApi } from "@/components/flow-canvas/api/flowApi";

export type FlowSource = "draft" | "published";

/** A specific archived/published version, pinned by its version number —
 * used chat-side so a message keeps showing the flow that actually ran,
 * even after a later publish changes what "published" points at. */
export interface PinnedFlowVersion {
  versionNo: number;
}

export type FlowSourceOption = FlowSource | PinnedFlowVersion;

export interface UseLoadFlowIntoStoreResult {
  isLoading: boolean;
  error: unknown;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  nodesCount: number;
  edgesCount: number;
}

const EMPTY_NODES: CanvasNode[] = [];
const EMPTY_EDGES: CanvasEdge[] = [];

function isPinnedVersion(
  source: FlowSourceOption
): source is PinnedFlowVersion {
  return typeof source === "object" && source !== null;
}

/** Fetches a flow-backed definition's spec and loads it into `store`.
 * `source: "draft"` (default) mirrors what the editor shows; `"published"`
 * is what actually executes — a chat-side consumer must use "published" so
 * it never shows an in-progress, possibly-invalid edit; `{ versionNo }` pins
 * to one archived version, for a chat message that must keep showing the
 * flow that ran even after a later publish. Also returns the converted
 * nodes/edges directly, since a caller may need them for its own logic
 * (e.g. ordering) without re-reading them back out of the store. */
export function useLoadFlowIntoStore(
  definitionId: string | null,
  store: StoreApi<FlowStore>,
  options?: { source?: FlowSourceOption }
): UseLoadFlowIntoStoreResult {
  const source = options?.source ?? "draft";
  // The version-detail endpoint nests the spec under `flow_spec` and adds
  // version metadata alongside it; draft/published return the spec directly.
  const pinned = isPinnedVersion(source);
  const url = definitionId
    ? pinned
      ? flowApi.version(definitionId, source.versionNo)
      : flowApi.bySource(definitionId, source)
    : null;
  const {
    data: raw,
    isLoading,
    error,
  } = useSWR<WireFlowSpec | { flow_spec: WireFlowSpec }>(
    url,
    errorHandlingFetcher
  );

  // A pinned version that fails to load (e.g. the version endpoint is
  // unavailable, or the run predates version archiving) must NOT leave the
  // consumer with an empty graph — fall back to the published spec so the
  // stage strip still renders something sensible.
  const fallbackUrl =
    pinned && error && definitionId ? flowApi.published(definitionId) : null;
  const { data: fallbackRaw } = useSWR<
    WireFlowSpec | { flow_spec: WireFlowSpec }
  >(fallbackUrl, errorHandlingFetcher);

  const spec: WireFlowSpec | undefined = useMemo(() => {
    const src = raw ?? fallbackRaw;
    if (!src) return undefined;
    return "flow_spec" in src && src.flow_spec
      ? (src.flow_spec as WireFlowSpec)
      : (src as WireFlowSpec);
  }, [raw, fallbackRaw]);

  const graph = useMemo(
    () => (spec && spec.nodes ? fromFlowSpec(spec) : null),
    [spec]
  );

  useEffect(() => {
    if (graph) {
      store.getState().loadGraph(graph);
    }
  }, [graph, store]);

  return {
    isLoading,
    error,
    nodes: graph?.nodes ?? EMPTY_NODES,
    edges: graph?.edges ?? EMPTY_EDGES,
    nodesCount: spec?.nodes?.length ?? 0,
    edgesCount: spec?.edges?.length ?? 0,
  };
}
