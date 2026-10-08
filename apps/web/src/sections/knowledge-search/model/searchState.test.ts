import {
  PAGE_SIZE,
  initialSearchState,
  searchReducer,
  toSearchRequest,
  type KnowledgeSearchState,
  type SearchAction,
} from "@/sections/knowledge-search/model/searchState";
import { DEFAULT_SEARCH_LIMIT } from "@/lib/api/domains/knowledge/knowledge-search-types";

function run(
  actions: SearchAction[],
  state: KnowledgeSearchState = initialSearchState()
): KnowledgeSearchState {
  return actions.reduce(searchReducer, state);
}

describe("searchReducer", () => {
  it("starts idle in hybrid mode with the default limit", () => {
    const state = initialSearchState();

    expect(state).toMatchObject({
      draft: "",
      query: null,
      kind: "hybrid",
      limit: DEFAULT_SEARCH_LIMIT,
      tab: "list",
      visibleCount: PAGE_SIZE,
      selection: null,
      graphDepth: 1,
      matchedOnly: false,
    });
  });

  it("submits the trimmed draft and ignores blank drafts", () => {
    expect(
      run([{ type: "draftChanged", draft: "   " }, { type: "submitted" }]).query
    ).toBeNull();

    const state = run([
      { type: "draftChanged", draft: "  retention  " },
      { type: "submitted" },
    ]);

    expect(state.query).toBe("retention");
    expect(state.draft).toBe("  retention  ");
  });

  it("toggles a collection in and out of the filter and resets paging", () => {
    const added = run([
      { type: "queryApplied", query: "q" },
      { type: "collectionsChanged", collectionIds: ["legal"] },
      { type: "moreRevealed" },
      { type: "collectionToggled", collectionId: "kg" },
    ]);
    expect(added.collectionIds).toEqual(["legal", "kg"]);
    expect(added.visibleCount).toBe(PAGE_SIZE);

    const removed = searchReducer(added, {
      type: "collectionToggled",
      collectionId: "legal",
    });
    expect(removed.collectionIds).toEqual(["kg"]);
  });

  it("resets paging, selection, and limit on a new query but keeps filters", () => {
    const state = run([
      { type: "queryApplied", query: "first" },
      { type: "collectionsChanged", collectionIds: ["legal"] },
      { type: "fileTypeToggled", value: "pdf" },
      { type: "moreRevealed" },
      { type: "limitRaised" },
      { type: "selected", selection: { type: "hit", hitId: "c1" } },
      { type: "draftChanged", draft: "second" },
      { type: "submitted" },
    ]);

    expect(state.query).toBe("second");
    expect(state.visibleCount).toBe(PAGE_SIZE);
    expect(state.limit).toBe(DEFAULT_SEARCH_LIMIT);
    expect(state.selection).toBeNull();
    expect(state.collectionIds).toEqual(["legal"]);
    expect(state.fileTypes).toEqual(["pdf"]);
  });

  it("keeps the chosen result limit for new queries", () => {
    const state = run([
      { type: "limitChanged", limit: 25 },
      { type: "queryApplied", query: "first" },
      { type: "limitRaised" },
      { type: "queryApplied", query: "second" },
    ]);

    expect(state.limit).toBe(25);
    expect(state.chosenLimit).toBe(25);
  });

  it("applies a recent search to both draft and query", () => {
    const state = run([{ type: "queryApplied", query: " contracts " }]);

    expect(state.draft).toBe("contracts");
    expect(state.query).toBe("contracts");
  });

  it("clears the query, selection, and filters", () => {
    const state = run([
      { type: "queryApplied", query: "q" },
      { type: "entityLabelToggled", value: "Policy" },
      { type: "tabChanged", tab: "graph" },
      { type: "cleared" },
    ]);

    expect(state).toMatchObject({
      draft: "",
      query: null,
      entityLabels: [],
      tab: "list",
    });
  });

  it("changing kind resets paging and selection", () => {
    const state = run([
      { type: "queryApplied", query: "q" },
      { type: "moreRevealed" },
      { type: "selected", selection: { type: "hit", hitId: "x" } },
      { type: "kindChanged", kind: "graph" },
    ]);

    expect(state.kind).toBe("graph");
    expect(state.visibleCount).toBe(PAGE_SIZE);
    expect(state.selection).toBeNull();
  });

  it("toggles file type and entity label filters", () => {
    const state = run([
      { type: "fileTypeToggled", value: "pdf" },
      { type: "fileTypeToggled", value: "docx" },
      { type: "fileTypeToggled", value: "pdf" },
      { type: "entityLabelToggled", value: "Role" },
    ]);

    expect(state.fileTypes).toEqual(["docx"]);
    expect(state.entityLabels).toEqual(["Role"]);
    expect(run([{ type: "filtersReset" }], state)).toMatchObject({
      collectionIds: [],
      fileTypes: [],
      entityLabels: [],
    });
  });

  it("clears file types or entity labels on their own", () => {
    const state = run([
      { type: "fileTypeToggled", value: "pdf" },
      { type: "entityLabelToggled", value: "Role" },
      { type: "collectionsChanged", collectionIds: ["kg"] },
    ]);

    expect(run([{ type: "fileTypesCleared" }], state)).toMatchObject({
      fileTypes: [],
      entityLabels: ["Role"],
      collectionIds: ["kg"],
    });
    expect(run([{ type: "entityLabelsCleared" }], state)).toMatchObject({
      fileTypes: ["pdf"],
      entityLabels: [],
    });
  });

  it("filter changes reset paging", () => {
    const state = run([
      { type: "moreRevealed" },
      { type: "collectionsChanged", collectionIds: ["a", "b"] },
    ]);

    expect(state.visibleCount).toBe(PAGE_SIZE);
    expect(state.collectionIds).toEqual(["a", "b"]);
  });

  it("reveals pages and raises the limit to the next step", () => {
    const state = run([{ type: "moreRevealed" }, { type: "limitRaised" }]);

    expect(state.visibleCount).toBe(PAGE_SIZE * 3);
    expect(state.limit).toBe(100);
    expect(run([{ type: "limitRaised" }], state).limit).toBe(100);
  });

  it("sets the limit from settings and resets paging", () => {
    const state = run([
      { type: "moreRevealed" },
      { type: "limitChanged", limit: 25 },
    ]);

    expect(state.limit).toBe(25);
    expect(state.visibleCount).toBe(PAGE_SIZE);
  });

  it("tracks tab, selection, depth, and matched-only", () => {
    const state = run([
      { type: "tabChanged", tab: "graph" },
      {
        type: "selected",
        selection: { type: "node", nodeId: "n", collectionId: "kg" },
      },
      { type: "graphDepthChanged", depth: 2 },
      { type: "matchedOnlyToggled" },
    ]);

    expect(state.tab).toBe("graph");
    expect(state.selection).toEqual({
      type: "node",
      nodeId: "n",
      collectionId: "kg",
    });
    expect(state.graphDepth).toBe(2);
    expect(state.matchedOnly).toBe(true);
    expect(run([{ type: "selectionCleared" }], state).selection).toBeNull();
  });
});

describe("toSearchRequest", () => {
  it("is null before a query is submitted", () => {
    expect(toSearchRequest(initialSearchState())).toBeNull();
  });

  it("includes only active filters", () => {
    const state = run([
      { type: "queryApplied", query: "q" },
      { type: "kindChanged", kind: "vector" },
      { type: "fileTypeToggled", value: "pdf" },
    ]);

    expect(toSearchRequest(state)).toEqual({
      query: "q",
      kind: "vector",
      limit: DEFAULT_SEARCH_LIMIT,
      fileTypes: ["pdf"],
    });
  });

  it("passes collection and entity filters", () => {
    const state = run([
      { type: "queryApplied", query: "q" },
      { type: "collectionsChanged", collectionIds: ["legal"] },
      { type: "entityLabelToggled", value: "Policy" },
    ]);

    expect(toSearchRequest(state)).toMatchObject({
      collectionIds: ["legal"],
      entityLabels: ["Policy"],
    });
  });
});
