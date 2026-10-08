import type {
  KnowledgeGraph,
  KnowledgeSearchHit,
  KnowledgeSearchResponse,
  KnowledgeSearchSource,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

export const documentHit: KnowledgeSearchHit = {
  id: "c1",
  kind: "document",
  relevance: 1,
  score: 0.42,
  collectionId: "legal",
  collectionName: "Hukuk & Sözleşmeler",
  document: {
    content:
      "Tedarikçi, kişisel verileri hizmetin sona ermesinden itibaren 30 gün içinde imha eder; saklama süresi mevzuatla sınırlıdır.",
    fileId: "f-1",
    source: "Tedarikçi Sözleşmesi.pdf",
    title: null,
    page: 7,
    section: "Madde 9",
    fileType: "pdf",
    metadata: { source: "Tedarikçi Sözleşmesi.pdf", token_count: 212 },
  },
  entity: null,
};

export const entityHit: KnowledgeSearchHit = {
  id: "n1",
  kind: "entity",
  relevance: 0.98,
  score: 0.03,
  collectionId: "kg",
  collectionName: "Kurumsal Graph",
  document: null,
  entity: {
    nodeId: "n1",
    name: "Veri Saklama Politikası",
    label: "Policy",
    matched: true,
    properties: { sürüm: "v3" },
    relations: [
      {
        type: "SORUMLUSU",
        direction: "out",
        nodeId: "n2",
        nodeName: "Veri Koruma Sorumlusu",
        nodeLabel: "Role",
      },
    ],
    neighborCount: 6,
  },
};

export const searchGraph: KnowledgeGraph = {
  nodes: [
    {
      id: "n1",
      name: "Veri Saklama Politikası",
      label: "Policy",
      matched: true,
      score: 0.03,
      collectionId: "kg",
      properties: { sürüm: "v3" },
    },
    {
      id: "n2",
      name: "Veri Koruma Sorumlusu",
      label: "Role",
      matched: false,
      score: null,
      collectionId: "kg",
      properties: {},
    },
  ],
  edges: [
    {
      id: "e1",
      source: "n1",
      target: "n2",
      type: "SORUMLUSU",
      collectionId: "kg",
      properties: {},
    },
  ],
};

export function searchResponse(
  overrides: Partial<KnowledgeSearchResponse> = {}
): KnowledgeSearchResponse {
  return {
    query: "saklama süresi",
    kind: "hybrid",
    elapsedMs: 418,
    total: 2,
    graphAvailable: true,
    graphUnavailable: false,
    hits: [documentHit, entityHit],
    graph: searchGraph,
    collections: [
      {
        id: "legal",
        name: "Hukuk & Sözleşmeler",
        documentHits: 1,
        entityHits: 0,
        status: "ok",
      },
      {
        id: "kg",
        name: "Kurumsal Graph",
        documentHits: 0,
        entityHits: 1,
        status: "ok",
      },
    ],
    facets: {
      fileTypes: [{ value: "pdf", count: 1 }],
      entityLabels: [{ value: "Policy", count: 1 }],
    },
    ...overrides,
  };
}

export const sources: KnowledgeSearchSource[] = [
  {
    id: "legal",
    name: "Hukuk & Sözleşmeler",
    sourceType: "document",
    connectorType: "",
    syncStatus: "idle",
    hasGraph: false,
  },
  {
    id: "drive",
    name: "Satın Alma",
    sourceType: "connector",
    connectorType: "google-drive",
    syncStatus: "succeeded",
    hasGraph: false,
  },
  {
    id: "kg",
    name: "Kurumsal Graph",
    sourceType: "document",
    connectorType: "",
    syncStatus: "idle",
    hasGraph: true,
  },
];
