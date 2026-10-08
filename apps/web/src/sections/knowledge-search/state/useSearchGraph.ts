"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import { useKnowledgeNeighborhoods } from "@/lib/api/domains/knowledge/hooks";
import { fetchKnowledgeNeighborhood } from "@/lib/api/domains/knowledge/api";
import {
  NODE_EXPANSION_LIMIT,
  type KnowledgeGraph,
  type KnowledgeGraphNode,
  type KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import {
  entityLabelGraph,
  MAX_NODE_EXPANSION_DEPTH,
  matchedNodesByCollection,
  matchedOnlyGraph,
  mergeKnowledgeGraphs,
} from "@/sections/knowledge-search/model/graphModel";
import type { GraphDepth } from "@/sections/knowledge-search/model/searchState";

const EMPTY_GRAPH: KnowledgeGraph = { nodes: [], edges: [] };

/** Neighbors added by "expand", valid only for the result they extend. */
interface ManualExpansion {
  result: KnowledgeSearchResponse | undefined;
  graph: KnowledgeGraph;
  /** Hops already loaded around each expanded node. */
  depths: Readonly<Record<string, number>>;
}

const NO_DEPTHS: ManualExpansion["depths"] = {};

interface SearchGraphOptions {
  result: KnowledgeSearchResponse | undefined;
  depth: GraphDepth;
  matchedOnly: boolean;
  /** Entity labels the results are refined to; empty keeps every label. */
  entityLabels: readonly string[];
  /** Whether the user may read graph neighborhoods (`graph:read`). */
  canExpand: boolean;
}

/**
 * The result graph plus depth expansion and per-node "expand neighbors";
 * failures surface as toasts instead of silently keeping the old graph.
 */
export function useSearchGraph({
  result,
  depth,
  matchedOnly,
  entityLabels,
  canExpand,
}: SearchGraphOptions) {
  const { t } = useTranslation();
  const expansionGroups = useMemo(
    () =>
      result && canExpand && depth > 1
        ? matchedNodesByCollection(result.graph)
        : [],
    [result, canExpand, depth]
  );
  const depthExpansion = useKnowledgeNeighborhoods(expansionGroups, depth);
  const [manual, setManual] = useState<ManualExpansion>({
    result: undefined,
    graph: EMPTY_GRAPH,
    depths: NO_DEPTHS,
  });
  const [expandingNodeId, setExpandingNodeId] = useState<string | null>(null);

  useEffect(() => {
    if (depthExpansion.error) {
      toast.error(t("knowledgeSearch.graph.expandError"));
    }
  }, [depthExpansion.error, t]);

  const fullGraph = useMemo(() => {
    const base = result?.graph ?? EMPTY_GRAPH;
    const withDepth = depthExpansion.graphs.reduce(mergeKnowledgeGraphs, base);
    return manual.result === result
      ? mergeKnowledgeGraphs(withDepth, manual.graph)
      : withDepth;
  }, [result, depthExpansion.graphs, manual]);

  const graph = useMemo(() => {
    const labelled = entityLabelGraph(fullGraph, entityLabels);
    return matchedOnly ? matchedOnlyGraph(labelled) : labelled;
  }, [fullGraph, matchedOnly, entityLabels]);

  const expansionDepthOf = useCallback(
    (nodeId: string) =>
      (manual.result === result ? manual.depths[nodeId] : undefined) ?? 0,
    [manual, result]
  );

  /**
   * Each call reaches one hop further than the last for the same node, so
   * pressing it again always has something new to load, up to the cap.
   */
  const expandNode = useCallback(
    async (node: KnowledgeGraphNode) => {
      const depth = expansionDepthOf(node.id) + 1;
      if (depth > MAX_NODE_EXPANSION_DEPTH) return;
      setExpandingNodeId(node.id);
      try {
        const neighborhood = await fetchKnowledgeNeighborhood({
          collectionId: node.collectionId,
          nodeIds: [node.id],
          depth,
          limit: NODE_EXPANSION_LIMIT,
        });
        const known = new Set(fullGraph.nodes.map((item) => item.id));
        if (neighborhood.nodes.every((item) => known.has(item.id))) {
          toast.info(t("knowledgeSearch.graph.nothingNew"));
        }
        setManual((current) => {
          const same = current.result === result;
          return {
            result,
            graph: mergeKnowledgeGraphs(
              same ? current.graph : EMPTY_GRAPH,
              neighborhood
            ),
            depths: {
              ...(same ? current.depths : NO_DEPTHS),
              [node.id]: depth,
            },
          };
        });
      } catch {
        toast.error(t("knowledgeSearch.graph.expandError"));
      } finally {
        setExpandingNodeId(null);
      }
    },
    [result, t, fullGraph, expansionDepthOf]
  );

  return {
    /** Everything known about the graph, expansions included. */
    fullGraph,
    /** The graph as displayed (matched-only applied). */
    graph,
    isExpanding: depthExpansion.isLoading || expandingNodeId !== null,
    expandingNodeId,
    expandNode,
    /** Hops of neighbors loaded around a node so far (0 = none). */
    expansionDepthOf,
  };
}
