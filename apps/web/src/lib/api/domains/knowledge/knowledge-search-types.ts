import * as z from "zod";

/**
 * Knowledge search — the browser-side reader of rag-service `/api/v1/search*`.
 *
 * Wire payloads are snake_case; these schemas validate them at the boundary
 * and hand the UI camelCase values. Unknown fields are ignored so an older
 * client keeps working with a newer backend.
 */

export const RETRIEVAL_KINDS = ["hybrid", "vector", "graph"] as const;
export type RetrievalKind = (typeof RETRIEVAL_KINDS)[number];

export const SEARCH_RESULT_LIMITS = [25, 50, 100] as const;
export const DEFAULT_SEARCH_LIMIT = 50;

const properties = z.record(z.string(), z.unknown()).default({});

const documentHitSchema = z
  .object({
    content: z.string(),
    file_id: z.string().nullish(),
    source: z.string().nullish(),
    title: z.string().nullish(),
    page: z.number().int().nullish(),
    section: z.string().nullish(),
    file_type: z.string().nullish(),
    metadata: properties,
  })
  .transform((hit) => ({
    content: hit.content,
    fileId: hit.file_id ?? null,
    source: hit.source ?? null,
    title: hit.title ?? null,
    page: hit.page ?? null,
    section: hit.section ?? null,
    fileType: hit.file_type ?? null,
    metadata: hit.metadata,
  }));

const relationSchema = z
  .object({
    type: z.string(),
    direction: z.enum(["out", "in"]),
    node_id: z.string(),
    node_name: z.string(),
    node_label: z.string(),
  })
  .transform((relation) => ({
    type: relation.type,
    direction: relation.direction,
    nodeId: relation.node_id,
    nodeName: relation.node_name,
    nodeLabel: relation.node_label,
  }));

const entityHitSchema = z
  .object({
    node_id: z.string(),
    name: z.string(),
    label: z.string(),
    matched: z.boolean(),
    properties,
    relations: z.array(relationSchema).default([]),
    neighbor_count: z.number().int().min(0).default(0),
  })
  .transform((hit) => ({
    nodeId: hit.node_id,
    name: hit.name,
    label: hit.label,
    matched: hit.matched,
    properties: hit.properties,
    relations: hit.relations,
    neighborCount: hit.neighbor_count,
  }));

const searchHitSchema = z
  .object({
    id: z.string(),
    kind: z.enum(["document", "entity"]),
    relevance: z.number(),
    score: z.number(),
    collection_id: z.string(),
    collection_name: z.string(),
    document: documentHitSchema.nullish(),
    entity: entityHitSchema.nullish(),
  })
  .transform((hit) => ({
    id: hit.id,
    kind: hit.kind,
    relevance: hit.relevance,
    score: hit.score,
    collectionId: hit.collection_id,
    collectionName: hit.collection_name,
    document: hit.document ?? null,
    entity: hit.entity ?? null,
  }));

const graphNodeSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    label: z.string(),
    matched: z.boolean(),
    score: z.number().nullish(),
    collection_id: z.string(),
    properties,
  })
  .transform((node) => ({
    id: node.id,
    name: node.name,
    label: node.label,
    matched: node.matched,
    score: node.score ?? null,
    collectionId: node.collection_id,
    properties: node.properties,
  }));

const graphEdgeSchema = z
  .object({
    id: z.string().nullish(),
    source: z.string(),
    target: z.string(),
    type: z.string(),
    collection_id: z.string(),
    properties,
  })
  .transform((edge) => ({
    id: edge.id ?? null,
    source: edge.source,
    target: edge.target,
    type: edge.type,
    collectionId: edge.collection_id,
    properties: edge.properties,
  }));

export const knowledgeGraphSchema = z.object({
  nodes: z.array(graphNodeSchema),
  edges: z.array(graphEdgeSchema),
});

const facetValueSchema = z.object({
  value: z.string(),
  count: z.number().int().min(0),
});

export const knowledgeSearchResponseSchema = z
  .object({
    query: z.string(),
    kind: z.enum(RETRIEVAL_KINDS),
    elapsed_ms: z.number().int().min(0),
    total: z.number().int().min(0),
    graph_available: z.boolean(),
    graph_unavailable: z.boolean().default(false),
    hits: z.array(searchHitSchema),
    graph: knowledgeGraphSchema,
    collections: z.array(
      z
        .object({
          id: z.string(),
          name: z.string(),
          document_hits: z.number().int().min(0),
          entity_hits: z.number().int().min(0),
          status: z.enum(["ok", "failed"]),
        })
        .transform((collection) => ({
          id: collection.id,
          name: collection.name,
          documentHits: collection.document_hits,
          entityHits: collection.entity_hits,
          status: collection.status,
        }))
    ),
    facets: z.object({
      file_types: z.array(facetValueSchema),
      entity_labels: z.array(facetValueSchema),
    }),
  })
  .transform((response) => ({
    query: response.query,
    kind: response.kind,
    elapsedMs: response.elapsed_ms,
    total: response.total,
    graphAvailable: response.graph_available,
    graphUnavailable: response.graph_unavailable,
    hits: response.hits,
    graph: response.graph,
    collections: response.collections,
    facets: {
      fileTypes: response.facets.file_types,
      entityLabels: response.facets.entity_labels,
    },
  }));

export const knowledgeSearchSourcesSchema = z
  .object({
    sources: z.array(
      z
        .object({
          id: z.string(),
          name: z.string(),
          source_type: z.enum(["document", "connector"]),
          connector_type: z.string().default(""),
          sync_status: z.string().default("idle"),
          has_graph: z.boolean(),
        })
        .transform((source) => ({
          id: source.id,
          name: source.name,
          sourceType: source.source_type,
          connectorType: source.connector_type,
          syncStatus: source.sync_status,
          hasGraph: source.has_graph,
        }))
    ),
  })
  .transform((response) => response.sources);

export type KnowledgeSearchResponse = z.output<
  typeof knowledgeSearchResponseSchema
>;
export type KnowledgeSearchHit = KnowledgeSearchResponse["hits"][number];
export type KnowledgeDocumentHit = NonNullable<KnowledgeSearchHit["document"]>;
export type KnowledgeEntityHit = NonNullable<KnowledgeSearchHit["entity"]>;
export type KnowledgeEntityRelation = KnowledgeEntityHit["relations"][number];
export type KnowledgeGraph = z.output<typeof knowledgeGraphSchema>;
export type KnowledgeGraphNode = KnowledgeGraph["nodes"][number];
export type KnowledgeGraphEdge = KnowledgeGraph["edges"][number];
export type KnowledgeCollectionOutcome =
  KnowledgeSearchResponse["collections"][number];
export type KnowledgeFacetValue =
  KnowledgeSearchResponse["facets"]["fileTypes"][number];
export type KnowledgeSearchSource = z.output<
  typeof knowledgeSearchSourcesSchema
>[number];

export interface KnowledgeSearchRequest {
  query: string;
  kind: RetrievalKind;
  limit: number;
  collectionIds?: readonly string[];
  fileTypes?: readonly string[];
  entityLabels?: readonly string[];
}

/** Seed nodes of one collection to expand in the knowledge graph. */
export interface KnowledgeNeighborhoodGroup {
  collectionId: string;
  nodeIds: readonly string[];
}

export interface KnowledgeNeighborhoodRequest
  extends KnowledgeNeighborhoodGroup {
  depth: number;
  limit: number;
}

/** Nodes one "expand neighbors" request may return. */
export const NODE_EXPANSION_LIMIT = 100;
/** Nodes one depth-expansion request may return (the backend maximum). */
export const DEPTH_EXPANSION_LIMIT = 300;
