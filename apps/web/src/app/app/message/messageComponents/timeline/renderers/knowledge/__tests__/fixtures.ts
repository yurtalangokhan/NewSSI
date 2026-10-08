import { Packet, PacketType } from "@/lib/api/domains/chat/streaming-types";

export const documentEvidence = {
  schema_version: 1,
  kind: "document",
  tool: "database_search",
  query: "yıllık izin devri onay",
  collections: [{ id: "col-1", name: "İK Politikaları" }],
  chunks: [
    {
      ref: 1,
      id: "chk_9f2a41",
      score: 0.89,
      content:
        "Kullanılmayan yıllık izin günleri, birim yöneticisinin onayı ile devredilir.",
      collection_id: "col-1",
      source: {
        document: "İzin Yönetmeliği 2026.pdf",
        page: 7,
        section: "§4.2",
      },
    },
    {
      ref: 2,
      id: "chk_1c07b3",
      score: 0.77,
      content: "Portal üzerinden İzin Devri formu doldurulur.",
      collection_id: "col-1",
      source: { document: "İK Süreç El Kitabı.docx", page: 22 },
    },
  ],
  model_context:
    "[1] (İzin Yönetmeliği 2026.pdf)\nKullanılmayan yıllık izin...",
  elapsed_ms: 420,
};

export const graphEvidence = {
  schema_version: 1,
  kind: "graph",
  tool: "graph_search",
  query: "izin devri onay",
  collections: [{ id: "g-1", name: "İK Bilgi Grafı" }],
  graph: {
    nodes: [
      {
        id: "n1",
        name: "Yıllık İzin Devri",
        label: "Process",
        matched: true,
        score: 0.0098,
        properties: {
          son_tarih: "15 Aralık",
          sorumlu: null,
          rrf_score: 0.0098,
          bm25_score: 3.2,
        },
      },
      { id: "n2", name: "Birim Yöneticisi", label: "Role", matched: true },
      { id: "n3", name: "İK Direktörlüğü", label: "Department" },
    ],
    edges: [
      { id: "e1", source: "n1", target: "n2", type: "REQUIRES_APPROVAL_FROM" },
      { id: "e2", source: "n1", target: "n3", type: "OWNED_BY" },
    ],
  },
  model_context: "== RRF-Ranked Entities ==",
  elapsed_ms: 310,
};

const PLACEMENT = { turn_index: 0, tab_index: 0 };

export function knowledgePackets(
  evidence: Record<string, unknown> | null,
  toolName = "database_search"
): Packet[] {
  return [
    {
      placement: PLACEMENT,
      obj: {
        type: PacketType.CUSTOM_TOOL_START,
        tool_name: toolName,
        args: { query: "yıllık izin devri onay" },
        call_id: "call-1",
      },
    },
    {
      placement: PLACEMENT,
      obj: {
        type: PacketType.CUSTOM_TOOL_DELTA,
        tool_name: toolName,
        response_type: "knowledge_retrieval",
        evidence_id: "ev-1",
        data: evidence,
        call_id: "call-1",
      },
    },
  ] as Packet[];
}
