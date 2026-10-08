"use client";

import { useCallback, useReducer } from "react";
import { useUser } from "@/providers/UserProvider";
import {
  useKnowledgeSearch,
  useKnowledgeSearchSources,
} from "@/lib/api/domains/knowledge/hooks";
import type {
  KnowledgeGraphNode,
  KnowledgeSearchHit,
  RetrievalKind,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import { showMoreAction } from "@/sections/knowledge-search/model/resultsView";
import {
  initialSearchState,
  searchReducer,
  toSearchRequest,
  type GraphDepth,
  type SearchTab,
} from "@/sections/knowledge-search/model/searchState";
import { useRecentSearches } from "@/sections/knowledge-search/state/useRecentSearches";
import { useSearchGraph } from "@/sections/knowledge-search/state/useSearchGraph";
import { useSearchSelection } from "@/sections/knowledge-search/state/useSearchSelection";

export type { SelectedPreview } from "@/sections/knowledge-search/state/useSearchSelection";

/**
 * The knowledge search page's state: it composes the query reducer, the fused
 * search, the result graph, the preview selection, and recent searches.
 */
export function useKnowledgeSearchController() {
  const { user, hasPermission } = useUser();
  const [state, dispatch] = useReducer(
    searchReducer,
    undefined,
    initialSearchState
  );
  const search = useKnowledgeSearch(toSearchRequest(state));
  const sourcesQuery = useKnowledgeSearchSources();
  const recentSearches = useRecentSearches(user?.id ?? null);
  const { result } = search;
  const { add: rememberSearch } = recentSearches;

  const submit = useCallback(() => {
    const query = state.draft.trim();
    if (query) rememberSearch(query);
    dispatch({ type: "submitted" });
  }, [state.draft, rememberSearch]);

  const applyQuery = useCallback(
    (query: string) => {
      const trimmed = query.trim();
      if (trimmed) rememberSearch(trimmed);
      dispatch({ type: "queryApplied", query });
    },
    [rememberSearch]
  );

  const canExpandGraph = hasPermission("graph:read");
  const canSearchGraph =
    hasPermission("graph:search") &&
    (sourcesQuery.isLoading ||
      sourcesQuery.sources.some((source) => source.hasGraph));

  const searchGraph = useSearchGraph({
    result,
    depth: state.graphDepth,
    matchedOnly: state.matchedOnly,
    entityLabels: state.entityLabels,
    canExpand: canExpandGraph,
  });

  const collectionName = useCallback(
    (collectionId: string) =>
      result?.collections.find((item) => item.id === collectionId)?.name ??
      sourcesQuery.sources.find((item) => item.id === collectionId)?.name ??
      collectionId,
    [result, sourcesQuery.sources]
  );

  const { selected, selectedHitId } = useSearchSelection({
    selection: state.selection,
    result,
    graph: searchGraph.fullGraph,
    collectionName,
  });

  const openHit = useCallback((hit: KnowledgeSearchHit) => {
    dispatch({
      type: "selected",
      selection:
        hit.kind === "entity" && hit.entity
          ? {
              type: "node",
              nodeId: hit.entity.nodeId,
              collectionId: hit.collectionId,
            }
          : { type: "hit", hitId: hit.id },
    });
  }, []);

  const selectNode = useCallback((node: KnowledgeGraphNode) => {
    dispatch({
      type: "selected",
      selection: {
        type: "node",
        nodeId: node.id,
        collectionId: node.collectionId,
      },
    });
  }, []);

  const showMore = useCallback(() => {
    if (!result) return;
    const action = showMoreAction(result, state.visibleCount, state.limit);
    if (action === "reveal") dispatch({ type: "moreRevealed" });
    if (action === "raiseLimit") dispatch({ type: "limitRaised" });
  }, [result, state.visibleCount, state.limit]);

  return {
    state,
    result,
    error: search.error,
    isLoading: search.isLoading,
    isValidating: search.isValidating,
    isSearching: search.isSearching,
    retry: () => void search.retry(),
    sources: sourcesQuery.sources,
    sourcesLoading: sourcesQuery.isLoading,
    sourcesError: sourcesQuery.error,
    recentSearches: recentSearches.recent,
    clearRecentSearches: recentSearches.clear,
    canSearchGraph,
    canExpandGraph,
    graph: searchGraph.graph,
    isExpanding: searchGraph.isExpanding,
    expandingNodeId: searchGraph.expandingNodeId,
    expandNode: searchGraph.expandNode,
    expansionDepthOf: searchGraph.expansionDepthOf,
    selected,
    selectedHitId,
    hasFilters:
      state.collectionIds.length > 0 ||
      state.fileTypes.length > 0 ||
      state.entityLabels.length > 0,
    setDraft: (draft: string) => dispatch({ type: "draftChanged", draft }),
    submit,
    applyQuery,
    clear: () => dispatch({ type: "cleared" }),
    setKind: (kind: RetrievalKind) => dispatch({ type: "kindChanged", kind }),
    setLimit: (limit: number) => dispatch({ type: "limitChanged", limit }),
    setCollections: (collectionIds: readonly string[]) =>
      dispatch({ type: "collectionsChanged", collectionIds }),
    toggleCollection: (collectionId: string) =>
      dispatch({ type: "collectionToggled", collectionId }),
    toggleFileType: (value: string) =>
      dispatch({ type: "fileTypeToggled", value }),
    clearFileTypes: () => dispatch({ type: "fileTypesCleared" }),
    toggleEntityLabel: (value: string) =>
      dispatch({ type: "entityLabelToggled", value }),
    clearEntityLabels: () => dispatch({ type: "entityLabelsCleared" }),
    resetFilters: () => dispatch({ type: "filtersReset" }),
    setTab: (tab: SearchTab) => dispatch({ type: "tabChanged", tab }),
    setDepth: (depth: GraphDepth) =>
      dispatch({ type: "graphDepthChanged", depth }),
    toggleMatchedOnly: () => dispatch({ type: "matchedOnlyToggled" }),
    closePreview: () => dispatch({ type: "selectionCleared" }),
    showMore,
    openHit,
    selectNode,
  };
}

export type KnowledgeSearchController = ReturnType<
  typeof useKnowledgeSearchController
>;
