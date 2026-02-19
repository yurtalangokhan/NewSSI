/**
 * TypeScript types for Graph RAG feature.
 */

// ============================================================================
// Graph Data Types
// ============================================================================

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

// ============================================================================
// Graph Stats
// ============================================================================

export interface GraphStats {
  collection_id: string;
  node_count: number;
  edge_count: number;
  label_counts: Record<string, number>;
  relationship_type_counts: Record<string, number>;
}

// ============================================================================
// Paginated Counts (for label / relationship-type browsing)
// ============================================================================

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

// ============================================================================
// Build Pipeline
// ============================================================================

export type BuildStatusType =
  | "pending"
  | "extracting"
  | "building"
  | "completed"
  | "failed";

export interface BuildProgress {
  collection_id: string;
  status: BuildStatusType;
  total_chunks: number;
  processed_chunks: number;
  extracted_entities: number;
  extracted_relations: number;
  error: string | null;
}

export interface GraphBuildRequest {
  collection_id: string;
  entity_types?: string[];
  relationship_types?: string[];
}

export interface GraphBuildResponse {
  collection_id: string;
  status: BuildStatusType;
  message: string;
}

// ============================================================================
// Search
// ============================================================================

export interface GraphSearchQuery {
  query: string;
  collection_id: string;
  limit?: number;
  search_type?: "entity" | "cypher" | "hybrid";
  vector_weight?: number;
  graph_weight?: number;
}

export interface GraphSearchResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  context: string;
  score: number;
}

/** Individual result item returned in hybrid search results array */
export interface GraphSearchResultItem {
  content: string;
  score: number;
  source: string;
  metadata: Record<string, unknown>;
}

/** Wrapper for hybrid search response containing multiple result items */
export interface GraphSearchResponse {
  results: GraphSearchResultItem[];
  graph: GraphData | null;
}

// ============================================================================
// Cypher
// ============================================================================

export interface CypherQueryRequest {
  query: string;
  collection_id: string;
  parameters?: Record<string, unknown>;
}

export interface CypherQueryResult {
  results: Record<string, unknown>[];
  count: number;
}

// ============================================================================
// Force Graph (react-force-graph) compatible types
// ============================================================================

export interface ForceGraphNode {
  id: string;
  name: string;
  label: string;
  val?: number;
  color?: string;
  properties?: Record<string, unknown>;
}

export interface ForceGraphLink {
  source: string;
  target: string;
  type: string;
  color?: string;
}

export interface ForceGraphData {
  nodes: ForceGraphNode[];
  links: ForceGraphLink[];
}
