import * as z from "zod";

/**
 * KnowledgeEvidence v1 — what one knowledge retrieval call handed the model.
 *
 * Streamed on a `custom_tool_delta` whose `response_type` is
 * {@link KNOWLEDGE_RESPONSE_TYPE}. The backend contract lives in
 * `docs/contracts/knowledge-evidence.v1.json`; this is its browser-side reader. Unknown
 * fields are ignored so an older client keeps working with a newer backend.
 */
export const KNOWLEDGE_RESPONSE_TYPE = "knowledge_retrieval";

const propertyValue = z.union([z.string(), z.number(), z.boolean(), z.null()]);

const sourceSchema = z
  .object({
    document: z.string().nullish(),
    title: z.string().nullish(),
    page: z.number().int().nullish(),
    section: z.string().nullish(),
    file_id: z.string().nullish(),
  })
  .transform((source) => ({
    document: source.document ?? null,
    title: source.title ?? null,
    page: source.page ?? null,
    section: source.section ?? null,
    fileId: source.file_id ?? null,
  }));

const chunkSchema = z
  .object({
    ref: z.number().int().min(1),
    id: z.string().nullish(),
    score: z.number().nullish(),
    content: z.string(),
    truncated: z.boolean().default(false),
    collection_id: z.string().nullish(),
    source: sourceSchema.default({
      document: null,
      title: null,
      page: null,
      section: null,
      fileId: null,
    }),
  })
  .transform((chunk) => ({
    ref: chunk.ref,
    id: chunk.id ?? null,
    score: chunk.score ?? null,
    content: chunk.content,
    truncated: chunk.truncated,
    collectionId: chunk.collection_id ?? null,
    source: chunk.source,
  }));

const nodeSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    label: z.string().default("Entity"),
    matched: z.boolean().default(false),
    score: z.number().nullish(),
    properties: z.record(z.string(), propertyValue).default({}),
  })
  .transform((node) => ({ ...node, score: node.score ?? null }));

const edgeSchema = z
  .object({
    id: z.string().nullish(),
    source: z.string(),
    target: z.string(),
    type: z.string(),
    properties: z.record(z.string(), propertyValue).default({}),
  })
  .transform((edge) => ({ ...edge, id: edge.id ?? null }));

const graphSchema = z
  .object({
    nodes: z.array(nodeSchema).default([]),
    edges: z.array(edgeSchema).default([]),
  })
  .transform((graph) => {
    const nodeIds = new Set(graph.nodes.map((node) => node.id));
    return {
      nodes: graph.nodes,
      edges: graph.edges.filter(
        (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)
      ),
    };
  });

const evidenceSchema = z
  .object({
    schema_version: z.literal(1),
    kind: z.enum(["document", "graph"]),
    tool: z.string(),
    query: z.string(),
    collections: z
      .array(z.object({ id: z.string(), name: z.string().nullish() }))
      .default([]),
    chunks: z.array(chunkSchema).default([]),
    graph: graphSchema.nullish(),
    model_context: z.string().default(""),
    model_context_truncated: z.boolean().default(false),
    elapsed_ms: z.number().int().nullish(),
  })
  .transform((evidence) => ({
    kind: evidence.kind,
    tool: evidence.tool,
    query: evidence.query,
    collections: evidence.collections.map((collection) => ({
      id: collection.id,
      name: collection.name ?? null,
    })),
    chunks: evidence.chunks,
    graph: evidence.graph ?? null,
    modelContext: evidence.model_context,
    modelContextTruncated: evidence.model_context_truncated,
    elapsedMs: evidence.elapsed_ms ?? null,
  }));

export type KnowledgeEvidence = z.output<typeof evidenceSchema>;
export type EvidenceChunk = KnowledgeEvidence["chunks"][number];
export type EvidenceSource = EvidenceChunk["source"];
export type EvidenceGraph = NonNullable<KnowledgeEvidence["graph"]>;
export type EvidenceGraphNode = EvidenceGraph["nodes"][number];
export type EvidenceGraphEdge = EvidenceGraph["edges"][number];
export type EvidenceCollection = KnowledgeEvidence["collections"][number];

/** The evidence in a packet's `data`, or `null` when it is absent or untrusted. */
export function parseKnowledgeEvidence(
  data: unknown
): KnowledgeEvidence | null {
  const result = evidenceSchema.safeParse(data);
  return result.success ? result.data : null;
}
