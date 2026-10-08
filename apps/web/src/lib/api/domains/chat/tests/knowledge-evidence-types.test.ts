import {
  KNOWLEDGE_RESPONSE_TYPE,
  parseKnowledgeEvidence,
} from "../knowledge-evidence-types";

const documentEvidence = {
  schema_version: 1,
  kind: "document",
  tool: "database_search",
  query: "yıllık izin devri",
  collections: [{ id: "col-1", name: "İK Politikaları" }],
  chunks: [
    {
      ref: 1,
      id: "chk_9f2a41",
      score: 0.89,
      content: "Kullanılmayan yıllık izin günleri devredilebilir.",
      truncated: false,
      collection_id: "col-1",
      source: { document: "İzin Yönetmeliği 2026.pdf", page: 7 },
    },
  ],
  graph: null,
  model_context: "[1] (İzin Yönetmeliği 2026.pdf)\nKullanılmayan...",
  model_context_truncated: false,
  elapsed_ms: 420,
};

describe("parseKnowledgeEvidence", () => {
  it("names the packet response type the backend uses", () => {
    expect(KNOWLEDGE_RESPONSE_TYPE).toBe("knowledge_retrieval");
  });

  it("parses document evidence into camel-cased fields", () => {
    const evidence = parseKnowledgeEvidence(documentEvidence);

    expect(evidence).not.toBeNull();
    expect(evidence?.kind).toBe("document");
    expect(evidence?.collections).toEqual([
      { id: "col-1", name: "İK Politikaları" },
    ]);
    expect(evidence?.chunks[0]).toEqual({
      ref: 1,
      id: "chk_9f2a41",
      score: 0.89,
      content: "Kullanılmayan yıllık izin günleri devredilebilir.",
      truncated: false,
      collectionId: "col-1",
      source: {
        document: "İzin Yönetmeliği 2026.pdf",
        title: null,
        page: 7,
        section: null,
        fileId: null,
      },
    });
    expect(evidence?.modelContext).toContain("[1]");
    expect(evidence?.elapsedMs).toBe(420);
    expect(evidence?.graph).toBeNull();
  });

  it("parses graph evidence with matched and expanded entities", () => {
    const evidence = parseKnowledgeEvidence({
      ...documentEvidence,
      kind: "graph",
      tool: "graph_search",
      chunks: [],
      graph: {
        nodes: [
          {
            id: "n1",
            name: "Yıllık İzin Devri",
            label: "Process",
            matched: true,
            score: 0.0098,
            properties: { limit: "10 iş günü" },
          },
          { id: "n2", name: "Birim Yöneticisi", label: "Role" },
        ],
        edges: [{ source: "n1", target: "n2", type: "REQUIRES_APPROVAL_FROM" }],
      },
    });

    expect(evidence?.graph?.nodes).toEqual([
      {
        id: "n1",
        name: "Yıllık İzin Devri",
        label: "Process",
        matched: true,
        score: 0.0098,
        properties: { limit: "10 iş günü" },
      },
      {
        id: "n2",
        name: "Birim Yöneticisi",
        label: "Role",
        matched: false,
        score: null,
        properties: {},
      },
    ]);
    expect(evidence?.graph?.edges).toEqual([
      {
        id: null,
        source: "n1",
        target: "n2",
        type: "REQUIRES_APPROVAL_FROM",
        properties: {},
      },
    ]);
  });

  it("drops edges that point at unknown entities", () => {
    const evidence = parseKnowledgeEvidence({
      ...documentEvidence,
      kind: "graph",
      graph: {
        nodes: [{ id: "n1", name: "A" }],
        edges: [{ source: "n1", target: "ghost", type: "R" }],
      },
    });

    expect(evidence?.graph?.edges).toEqual([]);
  });

  it("ignores fields it does not know, for forward compatibility", () => {
    const evidence = parseKnowledgeEvidence({
      ...documentEvidence,
      future_field: { anything: true },
    });

    expect(evidence).not.toBeNull();
  });

  it.each([
    null,
    undefined,
    "text",
    42,
    { ...documentEvidence, schema_version: 2 },
    { ...documentEvidence, kind: "video" },
    { ...documentEvidence, chunks: [{ ref: 0, content: "x" }] },
  ])("rejects a payload it cannot trust: %p", (payload) => {
    expect(parseKnowledgeEvidence(payload)).toBeNull();
  });
});
