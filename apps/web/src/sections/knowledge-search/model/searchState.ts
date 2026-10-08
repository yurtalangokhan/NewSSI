import {
  DEFAULT_SEARCH_LIMIT,
  type KnowledgeSearchRequest,
  type RetrievalKind,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import { nextLimit } from "@/sections/knowledge-search/model/resultsView";

/** Results revealed per "show more" step. */
export const PAGE_SIZE = 10;

export type SearchTab = "list" | "graph";
export type GraphDepth = 1 | 2 | 3;

/** What the preview drawer shows: a result card or a graph node. */
export type SearchSelection =
  | { type: "hit"; hitId: string }
  | { type: "node"; nodeId: string; collectionId: string };

export interface KnowledgeSearchState {
  /** What the search box shows. */
  draft: string;
  /** The submitted query; `null` shows the landing state. */
  query: string | null;
  kind: RetrievalKind;
  /** Results per search chosen in the settings. */
  chosenLimit: number;
  /** Results requested now; "show more" can raise it above `chosenLimit`. */
  limit: number;
  collectionIds: readonly string[];
  fileTypes: readonly string[];
  entityLabels: readonly string[];
  tab: SearchTab;
  visibleCount: number;
  selection: SearchSelection | null;
  graphDepth: GraphDepth;
  matchedOnly: boolean;
}

export type SearchAction =
  | { type: "draftChanged"; draft: string }
  | { type: "submitted" }
  | { type: "queryApplied"; query: string }
  | { type: "cleared" }
  | { type: "kindChanged"; kind: RetrievalKind }
  | { type: "limitChanged"; limit: number }
  | { type: "collectionsChanged"; collectionIds: readonly string[] }
  | { type: "collectionToggled"; collectionId: string }
  | { type: "fileTypeToggled"; value: string }
  | { type: "entityLabelToggled"; value: string }
  | { type: "fileTypesCleared" }
  | { type: "entityLabelsCleared" }
  | { type: "filtersReset" }
  | { type: "tabChanged"; tab: SearchTab }
  | { type: "moreRevealed" }
  | { type: "limitRaised" }
  | { type: "selected"; selection: SearchSelection }
  | { type: "selectionCleared" }
  | { type: "graphDepthChanged"; depth: GraphDepth }
  | { type: "matchedOnlyToggled" };

export function initialSearchState(): KnowledgeSearchState {
  return {
    draft: "",
    query: null,
    kind: "hybrid",
    chosenLimit: DEFAULT_SEARCH_LIMIT,
    limit: DEFAULT_SEARCH_LIMIT,
    collectionIds: [],
    fileTypes: [],
    entityLabels: [],
    tab: "list",
    visibleCount: PAGE_SIZE,
    selection: null,
    graphDepth: 1,
    matchedOnly: false,
  };
}

function toggled(values: readonly string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

/** A different result set: back to the first page with nothing selected. */
function freshResults(state: KnowledgeSearchState): KnowledgeSearchState {
  return { ...state, visibleCount: PAGE_SIZE, selection: null };
}

function withQuery(
  state: KnowledgeSearchState,
  query: string
): KnowledgeSearchState {
  return {
    ...freshResults(state),
    query,
    limit: state.chosenLimit,
    graphDepth: 1,
  };
}

export function searchReducer(
  state: KnowledgeSearchState,
  action: SearchAction
): KnowledgeSearchState {
  switch (action.type) {
    case "draftChanged":
      return { ...state, draft: action.draft };
    case "submitted": {
      const query = state.draft.trim();
      return query ? withQuery(state, query) : state;
    }
    case "queryApplied": {
      const query = action.query.trim();
      return query ? { ...withQuery(state, query), draft: query } : state;
    }
    case "cleared":
      return {
        ...initialSearchState(),
        kind: state.kind,
        chosenLimit: state.chosenLimit,
        limit: state.chosenLimit,
      };
    case "kindChanged":
      return { ...freshResults(state), kind: action.kind };
    case "limitChanged":
      return {
        ...freshResults(state),
        chosenLimit: action.limit,
        limit: action.limit,
      };
    case "collectionsChanged":
      return { ...freshResults(state), collectionIds: action.collectionIds };
    case "collectionToggled":
      return {
        ...freshResults(state),
        collectionIds: toggled(state.collectionIds, action.collectionId),
      };
    case "fileTypeToggled":
      return {
        ...freshResults(state),
        fileTypes: toggled(state.fileTypes, action.value),
      };
    case "entityLabelToggled":
      return {
        ...freshResults(state),
        entityLabels: toggled(state.entityLabels, action.value),
      };
    case "fileTypesCleared":
      return { ...freshResults(state), fileTypes: [] };
    case "entityLabelsCleared":
      return { ...freshResults(state), entityLabels: [] };
    case "filtersReset":
      return {
        ...freshResults(state),
        collectionIds: [],
        fileTypes: [],
        entityLabels: [],
      };
    case "tabChanged":
      return { ...state, tab: action.tab };
    case "moreRevealed":
      return { ...state, visibleCount: state.visibleCount + PAGE_SIZE };
    case "limitRaised":
      return {
        ...state,
        limit: nextLimit(state.limit) ?? state.limit,
        visibleCount: state.visibleCount + PAGE_SIZE,
      };
    case "selected":
      return { ...state, selection: action.selection };
    case "selectionCleared":
      return { ...state, selection: null };
    case "graphDepthChanged":
      return { ...state, graphDepth: action.depth };
    case "matchedOnlyToggled":
      return { ...state, matchedOnly: !state.matchedOnly };
  }
}

function nonEmpty(values: readonly string[]): readonly string[] | undefined {
  return values.length > 0 ? values : undefined;
}

/** The backend request for the state, or `null` while nothing is submitted. */
export function toSearchRequest(
  state: KnowledgeSearchState
): KnowledgeSearchRequest | null {
  if (state.query === null) return null;
  const collectionIds = nonEmpty(state.collectionIds);
  const fileTypes = nonEmpty(state.fileTypes);
  const entityLabels = nonEmpty(state.entityLabels);
  return {
    query: state.query,
    kind: state.kind,
    limit: state.limit,
    ...(collectionIds && { collectionIds }),
    ...(fileTypes && { fileTypes }),
    ...(entityLabels && { entityLabels }),
  };
}
