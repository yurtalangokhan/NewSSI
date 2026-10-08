import { act, renderHook, waitFor } from "@testing-library/react";

import { useKnowledgeSearchController } from "@/sections/knowledge-search/state/useKnowledgeSearchController";
import {
  useKnowledgeNeighborhoods,
  useKnowledgeSearch,
  useKnowledgeSearchSources,
} from "@/lib/api/domains/knowledge/hooks";
import { fetchKnowledgeNeighborhood } from "@/lib/api/domains/knowledge/api";
import { toast } from "@/hooks/useToast";
import { recentSearchesStorageKey } from "@/sections/knowledge-search/model/recentSearches";
import {
  documentHit,
  entityHit,
  searchGraph,
  searchResponse,
  sources,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";
import type { KnowledgeSearchResponse } from "@/lib/api/domains/knowledge/knowledge-search-types";

jest.mock("@/lib/api/domains/knowledge/hooks", () => ({
  useKnowledgeSearch: jest.fn(),
  useKnowledgeSearchSources: jest.fn(),
  useKnowledgeNeighborhoods: jest.fn(),
}));
jest.mock("@/lib/api/domains/knowledge/api", () => ({
  fetchKnowledgeNeighborhood: jest.fn(),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { error: jest.fn(), info: jest.fn() },
}));
const mockPermissions = new Set(["graph:search", "graph:read"]);
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: { id: "user-1" },
    hasPermission: (permission: string) => mockPermissions.has(permission),
  }),
}));
jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

const searchHook = jest.mocked(useKnowledgeSearch);
const sourcesHook = jest.mocked(useKnowledgeSearchSources);
const neighborhoodsHook = jest.mocked(useKnowledgeNeighborhoods);
const fetchNeighborhood = jest.mocked(fetchKnowledgeNeighborhood);

let currentResult: KnowledgeSearchResponse | undefined;

beforeEach(() => {
  window.localStorage.clear();
  mockPermissions.clear();
  mockPermissions.add("graph:search");
  mockPermissions.add("graph:read");
  jest.mocked(toast.error).mockClear();
  jest.mocked(toast.info).mockClear();
  currentResult = undefined;
  searchHook.mockImplementation((request) => ({
    result: request ? currentResult : undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    isSearching: false,
    retry: jest.fn(),
  }));
  sourcesHook.mockReturnValue({
    sources,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  });
  neighborhoodsHook.mockReturnValue({
    graphs: [],
    error: undefined,
    isLoading: false,
  });
  fetchNeighborhood.mockReset();
});

function setup() {
  return renderHook(() => useKnowledgeSearchController());
}

function submit(result: ReturnType<typeof setup>["result"], query: string) {
  currentResult = searchResponse({ query });
  act(() => result.current.setDraft(query));
  act(() => result.current.submit());
}

describe("useKnowledgeSearchController", () => {
  it("searches the submitted query and remembers it", () => {
    const { result } = setup();

    expect(searchHook).toHaveBeenLastCalledWith(null);
    submit(result, "saklama süresi");

    expect(searchHook).toHaveBeenLastCalledWith({
      query: "saklama süresi",
      kind: "hybrid",
      limit: 50,
    });
    expect(result.current.result?.query).toBe("saklama süresi");
    expect(result.current.recentSearches).toEqual(["saklama süresi"]);
    expect(
      JSON.parse(
        window.localStorage.getItem(recentSearchesStorageKey("user-1")!)!
      )
    ).toEqual(["saklama süresi"]);
  });

  it("reports the search hook's pending state", () => {
    const { result } = setup();
    searchHook.mockImplementation(() => ({
      result: undefined,
      error: undefined,
      isLoading: false,
      isValidating: true,
      isSearching: true,
      retry: jest.fn(),
    }));
    submit(result, "ikinci sorgu");

    expect(result.current.result).toBeUndefined();
    expect(result.current.isSearching).toBe(true);
  });

  it("remembers a search when it is submitted, not when state changes", () => {
    const { result } = setup();

    act(() => result.current.setDraft("  saklama  "));
    expect(result.current.recentSearches).toEqual([]);

    act(() => result.current.submit());
    expect(result.current.recentSearches).toEqual(["saklama"]);

    act(() => result.current.setKind("vector"));
    act(() => result.current.setLimit(10));
    expect(result.current.recentSearches).toEqual(["saklama"]);
  });

  it("does not remember an empty submission", () => {
    const { result } = setup();

    act(() => result.current.setDraft("   "));
    act(() => result.current.submit());

    expect(result.current.recentSearches).toEqual([]);
  });

  it("remembers a query applied from the recent list", () => {
    const { result } = setup();
    submit(result, "ilk");
    submit(result, "ikinci");

    act(() => result.current.applyQuery("ilk"));

    expect(result.current.recentSearches).toEqual(["ilk", "ikinci"]);
    expect(result.current.state.query).toBe("ilk");
  });

  it("clears recent searches", () => {
    const { result } = setup();
    submit(result, "q");

    act(() => result.current.clearRecentSearches());

    expect(result.current.recentSearches).toEqual([]);
  });

  it("passes filters to the search", () => {
    const { result } = setup();
    submit(result, "q");

    act(() => result.current.setCollections(["legal"]));
    act(() => result.current.toggleFileType("pdf"));
    act(() => result.current.setKind("vector"));

    expect(searchHook).toHaveBeenLastCalledWith({
      query: "q",
      kind: "vector",
      limit: 50,
      collectionIds: ["legal"],
      fileTypes: ["pdf"],
    });
    expect(result.current.hasFilters).toBe(true);
  });

  it("toggles a collection filter through the reducer", () => {
    const { result } = setup();
    submit(result, "q");

    act(() => result.current.toggleCollection("legal"));
    act(() => result.current.toggleCollection("kg"));
    act(() => result.current.toggleCollection("legal"));

    expect(result.current.state.collectionIds).toEqual(["kg"]);
  });

  it("opens document and entity previews", () => {
    const { result } = setup();
    submit(result, "q");

    act(() => result.current.openHit(documentHit));
    expect(result.current.selected).toEqual({
      kind: "document",
      hit: documentHit,
    });
    expect(result.current.selectedHitId).toBe("c1");

    act(() => result.current.openHit(entityHit));
    expect(result.current.selected).toMatchObject({
      kind: "entity",
      node: searchGraph.nodes[0],
      hit: entityHit,
      collectionName: "Kurumsal Graph",
    });
    expect(result.current.selectedHitId).toBe("n1");

    act(() => result.current.selectNode(searchGraph.nodes[1]!));
    expect(result.current.selected).toMatchObject({
      kind: "entity",
      node: searchGraph.nodes[1],
      hit: undefined,
    });

    act(() => result.current.closePreview());
    expect(result.current.selected).toBeNull();
  });

  it("merges expanded neighbors into the graph", async () => {
    fetchNeighborhood.mockResolvedValue({
      nodes: [
        {
          id: "n9",
          name: "İmha Tutanağı",
          label: "Document",
          matched: false,
          score: null,
          collectionId: "kg",
          properties: {},
        },
      ],
      edges: [
        {
          id: "e9",
          source: "n2",
          target: "n9",
          type: "ONAYLAR",
          collectionId: "kg",
          properties: {},
        },
      ],
    });
    const { result } = setup();
    submit(result, "q");

    await act(async () => {
      await result.current.expandNode(searchGraph.nodes[1]!);
    });

    expect(fetchNeighborhood).toHaveBeenCalledWith({
      collectionId: "kg",
      nodeIds: ["n2"],
      depth: 1,
      limit: 100,
    });
    expect(result.current.graph.nodes.map((node) => node.id)).toEqual([
      "n1",
      "n2",
      "n9",
    ]);
    expect(result.current.expandingNodeId).toBeNull();
  });

  it("expands a node one hop deeper on every repeat", async () => {
    fetchNeighborhood.mockResolvedValue({ nodes: [], edges: [] });
    const { result } = setup();
    submit(result, "q");
    const node = searchGraph.nodes[1]!;

    await act(async () => {
      await result.current.expandNode(node);
    });
    await act(async () => {
      await result.current.expandNode(node);
    });

    expect(
      fetchNeighborhood.mock.calls.map(([request]) => request.depth)
    ).toEqual([1, 2]);
    expect(result.current.expansionDepthOf(node.id)).toBe(2);
    expect(result.current.expansionDepthOf("n1")).toBe(0);
  });

  it("stops requesting past the deepest expansion", async () => {
    fetchNeighborhood.mockResolvedValue({ nodes: [], edges: [] });
    const { result } = setup();
    submit(result, "q");
    const node = searchGraph.nodes[1]!;

    for (let attempt = 0; attempt < 5; attempt += 1) {
      await act(async () => {
        await result.current.expandNode(node);
      });
    }

    expect(fetchNeighborhood).toHaveBeenCalledTimes(3);
    expect(result.current.expansionDepthOf(node.id)).toBe(3);
  });

  it("tells the user when an expansion finds nothing new", async () => {
    fetchNeighborhood.mockResolvedValue({
      nodes: [searchGraph.nodes[0]!],
      edges: [],
    });
    const { result } = setup();
    submit(result, "q");

    await act(async () => {
      await result.current.expandNode(searchGraph.nodes[1]!);
    });

    expect(toast.info).toHaveBeenCalledWith(
      "Bu düğüm için yeni komşu bulunamadı."
    );
  });

  it("reports failed expansions", async () => {
    fetchNeighborhood.mockRejectedValue(new Error("down"));
    const { result } = setup();
    submit(result, "q");

    await act(async () => {
      await result.current.expandNode(searchGraph.nodes[0]!);
    });

    expect(toast.error).toHaveBeenCalledWith("Komşular yüklenemedi.");
  });

  it("expands matched nodes to the chosen depth", () => {
    neighborhoodsHook.mockImplementation((groups, depth) => ({
      graphs:
        groups.length > 0 && depth === 2
          ? [
              {
                nodes: [
                  {
                    id: "deep",
                    name: "Deep",
                    label: "Role",
                    matched: false,
                    score: null,
                    collectionId: "kg",
                    properties: {},
                  },
                ],
                edges: [],
              },
            ]
          : [],
      error: undefined,
      isLoading: false,
    }));
    const { result } = setup();
    submit(result, "q");

    expect(neighborhoodsHook).toHaveBeenLastCalledWith([], 1);
    act(() => result.current.setDepth(2));

    expect(neighborhoodsHook).toHaveBeenLastCalledWith(
      [{ collectionId: "kg", nodeIds: ["n1"] }],
      2
    );
    expect(result.current.graph.nodes.map((node) => node.id)).toContain("deep");
  });

  it("reports failed depth expansion once", () => {
    neighborhoodsHook.mockReturnValue({
      graphs: [],
      error: new Error("forbidden"),
      isLoading: false,
    });
    const { result, rerender } = setup();
    submit(result, "q");
    act(() => result.current.setDepth(2));
    rerender();

    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith("Komşular yüklenemedi.");
  });

  it("offers graph search only with permission and a graph collection", () => {
    const { result, rerender } = setup();
    expect(result.current.canSearchGraph).toBe(true);
    expect(result.current.canExpandGraph).toBe(true);

    mockPermissions.clear();
    rerender();
    expect(result.current.canSearchGraph).toBe(false);
    expect(result.current.canExpandGraph).toBe(false);

    mockPermissions.add("graph:search");
    sourcesHook.mockReturnValue({
      sources: sources.map((source) => ({ ...source, hasGraph: false })),
      error: undefined,
      isLoading: false,
      mutate: jest.fn(),
    });
    rerender();
    expect(result.current.canSearchGraph).toBe(false);
  });

  it("shows only matched nodes on request", () => {
    const { result } = setup();
    submit(result, "q");

    act(() => result.current.toggleMatchedOnly());

    expect(result.current.graph.nodes.map((node) => node.id)).toEqual(["n1"]);
  });

  it("reveals loaded results before raising the limit", () => {
    const { result } = setup();
    const hits = Array.from({ length: 50 }, (_, index) => ({
      ...documentHit,
      id: `c${index}`,
    }));
    currentResult = searchResponse({ query: "q", hits, total: 80 });
    act(() => result.current.setDraft("q"));
    act(() => result.current.submit());

    act(() => result.current.showMore());
    expect(result.current.state.visibleCount).toBe(20);

    act(() => {
      for (let step = 0; step < 3; step += 1) result.current.showMore();
    });
    expect(result.current.state.visibleCount).toBe(50);

    act(() => result.current.showMore());
    expect(result.current.state.limit).toBe(100);
  });

  it("applies a recent search", async () => {
    const { result } = setup();
    currentResult = searchResponse({ query: "eski" });

    act(() => result.current.applyQuery("eski"));

    await waitFor(() => expect(result.current.state.query).toBe("eski"));
    expect(result.current.state.draft).toBe("eski");
  });
});
