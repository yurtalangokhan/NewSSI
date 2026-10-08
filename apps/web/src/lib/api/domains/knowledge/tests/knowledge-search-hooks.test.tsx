import React from "react";
import { SWRConfig } from "swr";
import { renderHook, waitFor } from "@testing-library/react";

import {
  useKnowledgeNeighborhoods,
  useKnowledgeSearch,
  useKnowledgeSearchSources,
} from "@/lib/api/domains/knowledge/hooks";
import {
  fetchKnowledgeNeighborhood,
  fetchKnowledgeSearchSources,
  searchKnowledge,
} from "@/lib/api/domains/knowledge/api";
import type {
  KnowledgeSearchRequest,
  KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

jest.mock("@/lib/api/domains/knowledge/api", () => ({
  ...jest.requireActual("@/lib/api/domains/knowledge/api"),
  searchKnowledge: jest.fn(),
  fetchKnowledgeSearchSources: jest.fn(),
  fetchKnowledgeNeighborhood: jest.fn(),
}));

const search = jest.mocked(searchKnowledge);
const sources = jest.mocked(fetchKnowledgeSearchSources);
const neighborhood = jest.mocked(fetchKnowledgeNeighborhood);

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        provider: () => new Map(),
        dedupingInterval: 0,
        shouldRetryOnError: false,
      }}
    >
      {children}
    </SWRConfig>
  );
}

function response(query: string): KnowledgeSearchResponse {
  return {
    query,
    kind: "hybrid",
    elapsedMs: 1,
    total: 0,
    graphAvailable: true,
    graphUnavailable: false,
    hits: [],
    graph: { nodes: [], edges: [] },
    collections: [],
    facets: { fileTypes: [], entityLabels: [] },
  };
}

describe("useKnowledgeSearch", () => {
  beforeEach(() => {
    search.mockReset();
  });

  it("stays idle without a request", () => {
    const { result } = renderHook(() => useKnowledgeSearch(null), { wrapper });

    expect(result.current.result).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
    expect(search).not.toHaveBeenCalled();
  });

  it("searches and keeps the previous result while a filter change loads", async () => {
    search.mockImplementation(async (request) => response(request.query));
    const first: KnowledgeSearchRequest = {
      query: "retention",
      kind: "hybrid",
      limit: 50,
    };

    const { result, rerender } = renderHook(
      ({ request }) => useKnowledgeSearch(request),
      { wrapper, initialProps: { request: first } }
    );

    await waitFor(() => expect(result.current.result?.query).toBe("retention"));
    expect(search).toHaveBeenCalledWith(first, expect.any(AbortSignal));
    expect(result.current.isSearching).toBe(false);

    let resolveNext: (value: KnowledgeSearchResponse) => void = () => {};
    search.mockImplementation(
      () => new Promise((resolve) => (resolveNext = resolve))
    );
    rerender({ request: { ...first, kind: "vector" } });

    await waitFor(() => expect(result.current.isSearching).toBe(true));
    expect(result.current.result?.query).toBe("retention");

    resolveNext(response("retention"));
    await waitFor(() => expect(result.current.isSearching).toBe(false));
  });

  it("never returns the previous query's response as the new query's result", async () => {
    search.mockImplementation(async (request) => response(request.query));
    const first: KnowledgeSearchRequest = {
      query: "retention",
      kind: "hybrid",
      limit: 50,
    };
    const { result, rerender } = renderHook(
      ({ request }) => useKnowledgeSearch(request),
      { wrapper, initialProps: { request: first } }
    );
    await waitFor(() => expect(result.current.result?.query).toBe("retention"));

    let resolveNext: (value: KnowledgeSearchResponse) => void = () => {};
    search.mockImplementation(
      () => new Promise((resolve) => (resolveNext = resolve))
    );
    rerender({ request: { ...first, query: "contracts" } });

    await waitFor(() => expect(result.current.isSearching).toBe(true));
    expect(result.current.result).toBeUndefined();

    resolveNext(response("contracts"));
    await waitFor(() => expect(result.current.result?.query).toBe("contracts"));
    expect(result.current.isSearching).toBe(false);
  });

  it("stops searching and shows the error when a new query fails", async () => {
    search.mockImplementation(async (request) => response(request.query));
    const first: KnowledgeSearchRequest = {
      query: "retention",
      kind: "hybrid",
      limit: 50,
    };
    const { result, rerender } = renderHook(
      ({ request }) => useKnowledgeSearch(request),
      { wrapper, initialProps: { request: first } }
    );
    await waitFor(() => expect(result.current.result?.query).toBe("retention"));

    search.mockRejectedValue(new Error("search failed"));
    rerender({ request: { ...first, query: "contracts" } });

    await waitFor(() => expect(result.current.error).toBeDefined());
    expect(result.current.result).toBeUndefined();
    expect(result.current.isSearching).toBe(false);
  });

  it("aborts a superseded request when the next one starts", async () => {
    const signals: AbortSignal[] = [];
    search.mockImplementation((request, signal) => {
      signals.push(signal!);
      return new Promise(() => undefined);
    });
    const first: KnowledgeSearchRequest = {
      query: "retention",
      kind: "hybrid",
      limit: 50,
    };

    const { rerender } = renderHook(
      ({ request }) => useKnowledgeSearch(request),
      { wrapper, initialProps: { request: first } }
    );
    await waitFor(() => expect(signals).toHaveLength(1));
    expect(signals[0]!.aborted).toBe(false);

    rerender({ request: { ...first, query: "contracts" } });

    await waitFor(() => expect(signals).toHaveLength(2));
    expect(signals[0]!.aborted).toBe(true);
    expect(signals[1]!.aborted).toBe(false);
  });

  it("aborts the in-flight request on unmount", async () => {
    let signal: AbortSignal | undefined;
    search.mockImplementation((request, given) => {
      signal = given;
      return new Promise(() => undefined);
    });

    const { unmount } = renderHook(
      () => useKnowledgeSearch({ query: "q", kind: "vector", limit: 10 }),
      { wrapper }
    );
    await waitFor(() => expect(signal).toBeDefined());

    unmount();

    expect(signal!.aborted).toBe(true);
  });

  it("exposes errors", async () => {
    const failure = new Error("down");
    search.mockRejectedValue(failure);

    const { result } = renderHook(
      () => useKnowledgeSearch({ query: "q", kind: "vector", limit: 10 }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.error).toBe(failure));
  });
});

describe("useKnowledgeSearchSources", () => {
  it("loads sources", async () => {
    sources.mockResolvedValue([
      {
        id: "legal",
        name: "Legal",
        sourceType: "document",
        connectorType: "",
        syncStatus: "idle",
        hasGraph: true,
      },
    ]);

    const { result } = renderHook(() => useKnowledgeSearchSources(), {
      wrapper,
    });

    expect(result.current.sources).toEqual([]);
    await waitFor(() => expect(result.current.sources).toHaveLength(1));
    expect(result.current.isLoading).toBe(false);
  });
});

describe("useKnowledgeNeighborhoods", () => {
  beforeEach(() => neighborhood.mockReset());

  it("stays idle without groups", () => {
    const { result } = renderHook(() => useKnowledgeNeighborhoods([], 2), {
      wrapper,
    });

    expect(result.current.graphs).toEqual([]);
    expect(neighborhood).not.toHaveBeenCalled();
  });

  it("expands every group at the requested depth", async () => {
    neighborhood.mockImplementation(async (request) => ({
      nodes: [
        {
          id: request.nodeIds[0]!,
          name: "N",
          label: "L",
          matched: false,
          score: null,
          collectionId: request.collectionId,
          properties: {},
        },
      ],
      edges: [],
    }));
    const groups = [
      { collectionId: "a", nodeIds: ["n1"] },
      { collectionId: "b", nodeIds: ["n2", "n3"] },
    ];

    const { result } = renderHook(() => useKnowledgeNeighborhoods(groups, 3), {
      wrapper,
    });

    await waitFor(() => expect(result.current.graphs).toHaveLength(2));
    expect(neighborhood).toHaveBeenCalledWith({
      collectionId: "b",
      nodeIds: ["n2", "n3"],
      depth: 3,
      limit: 300,
    });
    expect(result.current.isLoading).toBe(false);
  });
});
