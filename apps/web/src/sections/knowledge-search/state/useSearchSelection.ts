"use client";

import { useMemo } from "react";
import type {
  KnowledgeGraph,
  KnowledgeGraphNode,
  KnowledgeSearchHit,
  KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import { nodeFromEntityHit } from "@/sections/knowledge-search/model/graphModel";
import type { SearchSelection } from "@/sections/knowledge-search/model/searchState";

export type SelectedPreview =
  | { kind: "document"; hit: KnowledgeSearchHit }
  | {
      kind: "entity";
      node: KnowledgeGraphNode;
      hit: KnowledgeSearchHit | undefined;
      collectionName: string;
    };

interface SearchSelectionOptions {
  selection: SearchSelection | null;
  result: KnowledgeSearchResponse | undefined;
  graph: KnowledgeGraph;
  collectionName: (collectionId: string) => string;
}

/** Resolve the selection into what the preview drawer shows. */
export function useSearchSelection({
  selection,
  result,
  graph,
  collectionName,
}: SearchSelectionOptions) {
  const selected = useMemo<SelectedPreview | null>(() => {
    if (!selection || !result) return null;
    if (selection.type === "hit") {
      const hit = result.hits.find((item) => item.id === selection.hitId);
      return hit ? { kind: "document", hit } : null;
    }
    const hit = result.hits.find(
      (item) => item.entity?.nodeId === selection.nodeId
    );
    const node =
      graph.nodes.find((item) => item.id === selection.nodeId) ??
      (hit ? nodeFromEntityHit(hit) : undefined);
    if (!node) return null;
    return {
      kind: "entity",
      node,
      hit,
      collectionName: collectionName(selection.collectionId),
    };
  }, [selection, result, graph, collectionName]);

  const selectedHitId =
    selected === null
      ? null
      : selected.kind === "document"
        ? selected.hit.id
        : selected.hit?.id ?? null;

  return { selected, selectedHitId };
}
