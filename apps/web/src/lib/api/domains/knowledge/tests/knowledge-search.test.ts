import {
  fetchKnowledgeNeighborhood,
  fetchKnowledgeSearchSources,
  searchKnowledge,
} from "@/lib/api/domains/knowledge/api";
import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";
import { FetchError } from "@/lib/api/http/errors";

function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
}

const graphBody = {
  nodes: [
    {
      id: "p",
      name: "Retention policy",
      label: "Policy",
      matched: true,
      score: 0.03,
      collection_id: "legal",
      properties: { version: "v3" },
    },
  ],
  edges: [
    {
      id: null,
      source: "p",
      target: "p",
      type: "SELF",
      collection_id: "legal",
      properties: {},
    },
  ],
};

const searchBody = {
  query: "retention",
  kind: "hybrid",
  elapsed_ms: 412,
  total: 2,
  graph_available: true,
  hits: [
    {
      id: "c1",
      kind: "document",
      relevance: 1,
      score: 0.42,
      collection_id: "legal",
      collection_name: "Legal",
      document: {
        content: "Keep supplier data for two years.",
        file_id: "f-1",
        source: "Retention.pdf",
        title: null,
        page: 3,
        section: "4.2",
        file_type: "pdf",
        metadata: { source: "Retention.pdf" },
      },
      entity: null,
    },
    {
      id: "p",
      kind: "entity",
      relevance: 0.98,
      score: 0.03,
      collection_id: "legal",
      collection_name: "Legal",
      document: null,
      entity: {
        node_id: "p",
        name: "Retention policy",
        label: "Policy",
        matched: true,
        properties: {},
        relations: [
          {
            type: "OWNED_BY",
            direction: "out",
            node_id: "r",
            node_name: "DPO",
            node_label: "Role",
          },
        ],
        neighbor_count: 1,
      },
    },
  ],
  graph: graphBody,
  collections: [
    {
      id: "legal",
      name: "Legal",
      document_hits: 1,
      entity_hits: 1,
      status: "ok",
    },
  ],
  facets: {
    file_types: [{ value: "pdf", count: 1 }],
    entity_labels: [{ value: "Policy", count: 1 }],
  },
};

function lastRequest(): [string, RequestInit] {
  const calls = (global.fetch as jest.MockedFunction<typeof fetch>).mock.calls;
  const [url, init] = calls[calls.length - 1]!;
  return [String(url), init ?? {}];
}

describe("knowledge search endpoints", () => {
  it("maps the search, sources, and neighborhood browser paths", () => {
    expect(knowledgeEndpoints.ragSearch.browserPath).toBe("/api/rag/search");
    expect(knowledgeEndpoints.ragSearchSources.browserPath).toBe(
      "/api/rag/search/sources"
    );
    expect(knowledgeEndpoints.ragSearchNeighborhood.browserPath).toBe(
      "/api/rag/search/graph/neighborhood"
    );
    expect(knowledgeEndpoints.ragProxyTarget(["search"]).backend.path).toBe(
      "/api/v1/search"
    );
  });
});

describe("knowledge search api", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("posts the snake_case request and returns a camelCase result", async () => {
    // Serves POST /api/rag/search.
    jest
      .spyOn(global, "fetch")
      .mockImplementation(() => jsonResponse(searchBody));
    const controller = new AbortController();

    const result = await searchKnowledge(
      {
        query: "retention",
        kind: "hybrid",
        limit: 50,
        collectionIds: ["legal"],
        fileTypes: ["pdf"],
        entityLabels: ["Policy"],
      },
      controller.signal
    );

    const [url, init] = lastRequest();
    expect(url).toBe("/api/rag/search");
    expect(init.method).toBe("POST");
    expect(init.signal).toBe(controller.signal);
    expect(JSON.parse(String(init.body))).toEqual({
      query: "retention",
      kind: "hybrid",
      limit: 50,
      collection_ids: ["legal"],
      file_types: ["pdf"],
      entity_labels: ["Policy"],
    });
    expect(result.elapsedMs).toBe(412);
    expect(result.graphAvailable).toBe(true);
    expect(result.graphUnavailable).toBe(false);
    expect(result.hits[0]!.document).toEqual({
      content: "Keep supplier data for two years.",
      fileId: "f-1",
      source: "Retention.pdf",
      title: null,
      page: 3,
      section: "4.2",
      fileType: "pdf",
      metadata: { source: "Retention.pdf" },
    });
    expect(result.hits[1]!.entity!.relations[0]).toEqual({
      type: "OWNED_BY",
      direction: "out",
      nodeId: "r",
      nodeName: "DPO",
      nodeLabel: "Role",
    });
    expect(result.hits[1]!.entity!.neighborCount).toBe(1);
    expect(result.collections[0]).toEqual({
      id: "legal",
      name: "Legal",
      documentHits: 1,
      entityHits: 1,
      status: "ok",
    });
    expect(result.facets.fileTypes).toEqual([{ value: "pdf", count: 1 }]);
    expect(result.graph.nodes[0]!.collectionId).toBe("legal");
    expect(result.graph.edges[0]!.id).toBeNull();
  });

  it("maps a graph store outage from graph_unavailable", async () => {
    // Serves POST /api/rag/search while the graph store is unreachable.
    jest.spyOn(global, "fetch").mockImplementation(() =>
      jsonResponse({
        ...searchBody,
        graph_available: false,
        graph_unavailable: true,
      })
    );

    const result = await searchKnowledge({
      query: "retention",
      kind: "hybrid",
      limit: 50,
    });

    expect(result.graphAvailable).toBe(false);
    expect(result.graphUnavailable).toBe(true);
  });

  it("omits unset filters from the request body", async () => {
    // Serves POST /api/rag/search.
    jest
      .spyOn(global, "fetch")
      .mockImplementation(() => jsonResponse(searchBody));

    await searchKnowledge({ query: "q", kind: "vector", limit: 10 });

    expect(JSON.parse(String(lastRequest()[1].body))).toEqual({
      query: "q",
      kind: "vector",
      limit: 10,
    });
  });

  it("raises a FetchError with the backend message", async () => {
    // Serves POST /api/rag/search with a 403.
    jest.spyOn(global, "fetch").mockImplementation(() =>
      jsonResponse(
        {
          error: {
            code: "forbidden",
            message: "Graph search permission is required.",
          },
        },
        403
      )
    );

    const failure = searchKnowledge({ query: "q", kind: "graph", limit: 10 });

    await expect(failure).rejects.toBeInstanceOf(FetchError);
    await expect(failure).rejects.toMatchObject({ status: 403 });
  });

  it("rejects malformed responses", async () => {
    // Serves POST /api/rag/search with an unexpected shape.
    jest
      .spyOn(global, "fetch")
      .mockImplementation(() => jsonResponse({ hits: "nope" }));

    await expect(
      searchKnowledge({ query: "q", kind: "hybrid", limit: 10 })
    ).rejects.toThrow();
  });

  it("loads searchable sources", async () => {
    // Serves GET /api/rag/search/sources.
    jest.spyOn(global, "fetch").mockImplementation(() =>
      jsonResponse({
        sources: [
          {
            id: "drive",
            name: "Drive",
            source_type: "connector",
            connector_type: "google-drive",
            sync_status: "succeeded",
            has_graph: false,
          },
        ],
      })
    );

    const sources = await fetchKnowledgeSearchSources();

    expect(lastRequest()[0]).toBe("/api/rag/search/sources");
    expect(sources).toEqual([
      {
        id: "drive",
        name: "Drive",
        sourceType: "connector",
        connectorType: "google-drive",
        syncStatus: "succeeded",
        hasGraph: false,
      },
    ]);
  });

  it("expands a neighborhood", async () => {
    // Serves POST /api/rag/search/graph/neighborhood.
    jest
      .spyOn(global, "fetch")
      .mockImplementation(() => jsonResponse(graphBody));

    const graph = await fetchKnowledgeNeighborhood({
      collectionId: "legal",
      nodeIds: ["p"],
      depth: 2,
      limit: 80,
    });

    const [url, init] = lastRequest();
    expect(url).toBe("/api/rag/search/graph/neighborhood");
    expect(JSON.parse(String(init.body))).toEqual({
      collection_id: "legal",
      node_ids: ["p"],
      depth: 2,
      limit: 80,
    });
    expect(graph.nodes[0]!.name).toBe("Retention policy");
  });
});
