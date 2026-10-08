import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

// ============================================================================
// Types — Collections
// ============================================================================

export interface RagCollection {
  uuid: string;
  name: string;
  metadata?: Record<string, unknown>;
}

export interface CreateCollectionInput {
  name: string;
  metadata?: Record<string, unknown>;
}

// ============================================================================
// Types — Documents
// ============================================================================

export interface RagDocument {
  id: string;
  collection_id: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface RagChunk {
  id: string;
  content: string;
  metadata?: Record<string, unknown>;
}

export interface RagChunkStats {
  total_chunks: number;
  avg_chars: number;
  avg_tokens: number;
}

export interface RagDocumentChunksResponse {
  stats: RagChunkStats;
  chunks: RagChunk[];
  total_chunks: number;
  has_more: boolean;
}

export interface UploadDocumentsResponse {
  success: boolean;
  message: string;
  added_chunk_ids: string[];
  warnings?: string;
}

export type UploadJobStatus = "pending" | "processing" | "completed" | "failed";

export interface UploadJobStartResponse {
  collection_id: string;
  status: UploadJobStatus;
  message: string;
}

export interface UploadProgress {
  collection_id: string;
  status: UploadJobStatus;
  total_files: number;
  processed_files: number;
  current_file: string | null;
  total_chunks: number;
  processed_chunks: number;
  duplicate_files: string[];
  failed_files: string[];
  added_chunk_ids: string[];
  error?: string | null;
  progress_percent: number;
}

// ============================================================================
// Types — Search
// ============================================================================

export interface SearchResult {
  id: string;
  page_content: string;
  metadata?: Record<string, unknown>;
  score: number;
}

export interface SearchInput {
  query: string;
  limit?: number;
  filter?: Record<string, unknown>;
}

// ============================================================================
// Types — Graph RAG
// ============================================================================

export type GraphBuildStatus =
  | "pending"
  | "extracting"
  | "building"
  | "completed"
  | "failed";

export interface GraphBuildStatusResponse {
  collection_id: string;
  status: GraphBuildStatus;
  is_paused: boolean;
  total_chunks: number;
  processed_chunks: number;
  extracted_entities: number;
  extracted_relations: number;
  error?: string;
  progress_percent: number;
}

export interface GraphStats {
  collection_id: string;
  node_count: number;
  edge_count: number;
  label_counts: Record<string, number>;
  relationship_type_counts: Record<string, number>;
}

export interface GraphBuildInput {
  collection_id: string;
  entity_types?: string[];
  relationship_types?: string[];
}

export type SearchType = "entity" | "cypher" | "hybrid";

export interface GraphSearchInput {
  query: string;
  collection_id: string;
  limit?: number;
  search_type?: SearchType;
  vector_weight?: number;
  graph_weight?: number;
}

// ---- Flat graph types (used by search results and entity preview) ----

export interface GraphNode {
  id: string;
  label: string;
  name: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---- Scalable / clustered graph types ----

export interface ClusterNode {
  id: string;
  label: string;
  name: string;
  node_count: number;
  top_entities: string[];
  properties: Record<string, unknown>;
  is_cluster: true;
}

export interface ClusterEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
  relationship_types: string[];
  properties: Record<string, unknown>;
}

export type ScalableNode = GraphNode | ClusterNode;
export type ScalableEdge = GraphEdge | ClusterEdge;

export type GraphViewMode =
  | "auto"
  | "overview"
  | "expand"
  | "neighborhood"
  | "full";

export interface ClusteredGraphData {
  nodes: ScalableNode[];
  edges: ScalableEdge[];
  total_node_count: number;
  total_edge_count: number;
  cluster_count: number;
  mode: GraphViewMode;
  scope_label?: string | null;
  metadata?: {
    neighbor_label_counts?: Record<string, number>;
    rel_type_counts?: Record<string, number>;
    scope_skip?: number;
    scope_limit?: number;
  };
}

// ---- Force-graph rendering types ----

export interface ForceGraphNode {
  id: string;
  name: string;
  label: string;
  val?: number;
  color?: string;
  properties?: Record<string, unknown>;
  isCluster?: boolean;
  nodeCount?: number;
  topEntities?: string[];
}

export interface ForceGraphLink {
  // react-force-graph mutates source/target to objects after init
  source: string | ForceGraphNode;
  target: string | ForceGraphNode;
  type: string;
  color?: string;
  weight?: number;
  relationshipTypes?: string[];
}

export interface ForceGraphData {
  nodes: ForceGraphNode[];
  links: ForceGraphLink[];
}

// ---- Paginated counts (for stats/labels filter panel) ----

export interface PaginatedCountItem {
  name: string;
  count: number;
}

export interface PaginatedCounts {
  items: PaginatedCountItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

// ---- Type guards ----

export function isClusterNode(n: ScalableNode): n is ClusterNode {
  return (n as ClusterNode).is_cluster === true;
}

export function isClusterEdge(e: ScalableEdge): e is ClusterEdge {
  return (
    typeof (e as ClusterEdge).weight === "number" &&
    Array.isArray((e as ClusterEdge).relationship_types)
  );
}

export interface GraphSearchResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  context: string;
  score: number;
}

// ============================================================================
// SWR Hooks
// ============================================================================

export const CHUNKS_PAGE_SIZE = 20;

export function getDocumentChunksPageKey(
  pageIndex: number,
  previousPageData: RagDocumentChunksResponse | null,
  collectionId: string | null,
  documentId: string | null
): string | null {
  if (!collectionId || !documentId) return null;
  if (previousPageData && !previousPageData.has_more) return null;
  const offset = pageIndex * CHUNKS_PAGE_SIZE;
  return `${knowledgeEndpoints.ragCollections.browserPath}/${collectionId}/documents/${documentId}/chunks?limit=${CHUNKS_PAGE_SIZE}&offset=${offset}`;
}

export type DateRangePickerValue = DateRange & {
  selectValue: string;
};
export type DateRange =
  | {
      from: Date;
      to: Date;
    }
  | undefined;

export interface KnowledgeEntityTypeUpdate {
  active: boolean;
  name: string;
  description: string;
  grounded_source_name: string;
}

export interface EmbeddingCredentialPayload {
  provider_type: string;
  api_key: string;
  api_url: string;
  is_default_provider: boolean;
  is_configured: boolean;
  api_version?: string | null;
  deployment_name?: string | null;
  model_name?: string;
  custom_config?: Record<string, string>;
}
