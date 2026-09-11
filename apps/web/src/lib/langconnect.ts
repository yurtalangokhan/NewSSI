/**
 * LangConnect RAG service types, SWR hooks, and API functions.
 *
 * All calls go through /api/rag/[...path] (Next.js API route proxy).
 * That proxy forwards the user's auth cookie or bearer token to RAG.
 *
 * Pattern mirrors lib/airbyte.ts from the Onyx codebase.
 */
import { useMemo } from "react";
import useSWR from "swr";
import useSWRInfinite from "swr/infinite";
import {
  createIdempotencyKey,
  withIdempotencyKey,
} from "@/lib/api/idempotency";
import { errorHandlingFetcher, authenticatedFetch } from "@/lib/fetcher";

const RAG = "/api/rag";
const CHUNKS_PAGE_SIZE = 20;

function withRagIdempotency(headers: HeadersInit = {}): HeadersInit {
  return withIdempotencyKey(headers, createIdempotencyKey());
}

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

export function useCollections() {
  const { data, error, isLoading, mutate } = useSWR<RagCollection[]>(
    `${RAG}/collections`,
    errorHandlingFetcher
  );
  return { collections: data ?? [], isLoading, error, mutate };
}

export function useDocuments(
  collectionId: string | null,
  limit = 20,
  offset = 0
) {
  const { data, error, isLoading, mutate } = useSWR<RagDocument[]>(
    collectionId
      ? `${RAG}/collections/${collectionId}/documents?limit=${limit}&offset=${offset}`
      : null,
    errorHandlingFetcher
  );
  return { documents: data ?? [], isLoading, error, mutate };
}

/**
 * Build the SWRInfinite key for one page of a document's chunks, or null to
 * stop paginating (no collection/document selected, or the previous page
 * already reported has_more: false).
 */
export function getDocumentChunksPageKey(
  pageIndex: number,
  previousPageData: RagDocumentChunksResponse | null,
  collectionId: string | null,
  documentId: string | null
): string | null {
  if (!collectionId || !documentId) return null;
  if (previousPageData && !previousPageData.has_more) return null;
  const offset = pageIndex * CHUNKS_PAGE_SIZE;
  return `${RAG}/collections/${collectionId}/documents/${documentId}/chunks?limit=${CHUNKS_PAGE_SIZE}&offset=${offset}`;
}

export function useDocumentChunks(
  collectionId: string | null,
  documentId: string | null
) {
  const { data, error, isLoading, size, setSize, mutate } =
    useSWRInfinite<RagDocumentChunksResponse>(
      (pageIndex, previousPageData) =>
        getDocumentChunksPageKey(
          pageIndex,
          previousPageData,
          collectionId,
          documentId
        ),
      errorHandlingFetcher
    );

  const chunks = useMemo(
    () => data?.flatMap((page) => page.chunks) ?? [],
    [data]
  );
  const stats = data?.[0]?.stats ?? null;
  const hasMore = data ? data[data.length - 1]?.has_more ?? false : false;
  const isLoadingMore =
    isLoading ||
    (size > 0 && data !== undefined && data[size - 1] === undefined);

  return {
    chunks,
    stats,
    isLoading,
    isLoadingMore,
    hasMore,
    loadMore: () => setSize(size + 1),
    error,
    mutate,
  };
}

export function useGraphBuildStatus(
  collectionId: string | null,
  active: boolean
) {
  const { data, error, isLoading, mutate } = useSWR<GraphBuildStatusResponse>(
    active && collectionId ? `${RAG}/graph/build/${collectionId}/status` : null,
    errorHandlingFetcher,
    { refreshInterval: 2_000 }
  );
  return { status: data ?? null, isLoading, error, mutate };
}

export function useUploadStatus(collectionId: string | null, active: boolean) {
  const { data, error, isLoading, mutate } = useSWR<UploadProgress>(
    active && collectionId
      ? `${RAG}/collections/${collectionId}/documents/upload-jobs/status`
      : null,
    errorHandlingFetcher,
    { refreshInterval: 2_000 }
  );
  return { progress: data ?? null, isLoading, error, mutate };
}

export function useGraphStats(collectionId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<GraphStats>(
    collectionId ? `${RAG}/graph/collections/${collectionId}/stats` : null,
    errorHandlingFetcher
  );
  return { stats: data ?? null, isLoading, error, mutate };
}

export function useGraphCollections() {
  const { data, error, isLoading, mutate } = useSWR<string[]>(
    `${RAG}/graph/collections`,
    errorHandlingFetcher
  );
  return { graphCollections: data ?? [], isLoading, error, mutate };
}

// ============================================================================
// API Functions — Collections
// ============================================================================

export async function createCollection(
  input: CreateCollectionInput
): Promise<RagCollection> {
  const res = await authenticatedFetch(`${RAG}/collections`, {
    method: "POST",
    headers: withRagIdempotency({ "Content-Type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to create collection");
  }
  return res.json();
}

export async function updateCollection(
  id: string,
  input: Partial<CreateCollectionInput>
): Promise<RagCollection> {
  const res = await authenticatedFetch(`${RAG}/collections/${id}`, {
    method: "PATCH",
    headers: withRagIdempotency({ "Content-Type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to update collection");
  }
  return res.json();
}

export async function deleteCollection(id: string): Promise<void> {
  const res = await authenticatedFetch(`${RAG}/collections/${id}`, {
    method: "DELETE",
    headers: withRagIdempotency(),
  });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to delete collection");
  }
}

// ============================================================================
// API Functions — Documents
// ============================================================================

/**
 * Upload files to a collection via multipart/form-data.
 * Do NOT set Content-Type — the browser sets it automatically with boundary.
 */
export async function uploadDocuments(
  collectionId: string,
  files: File[],
  metadatas?: Record<string, unknown>[]
): Promise<UploadDocumentsResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (metadatas && metadatas.length > 0) {
    formData.append("metadatas_json", JSON.stringify(metadatas));
  }
  const res = await authenticatedFetch(
    `${RAG}/collections/${collectionId}/documents`,
    {
      method: "POST",
      headers: withRagIdempotency(),
      body: formData,
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to upload documents");
  }
  return res.json();
}

/**
 * Start an async upload/embedding job for a collection and return immediately.
 * Progress is tracked server-side (keyed by collection_id) — poll it with
 * useUploadStatus, which survives navigating away from and back to the page.
 */
export async function startUploadJob(
  collectionId: string,
  files: File[],
  metadatas?: Record<string, unknown>[]
): Promise<UploadJobStartResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (metadatas && metadatas.length > 0) {
    formData.append("metadatas_json", JSON.stringify(metadatas));
  }
  const res = await authenticatedFetch(
    `${RAG}/collections/${collectionId}/documents/upload-jobs`,
    { method: "POST", headers: withRagIdempotency(), body: formData }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to start upload job");
  }
  return res.json();
}

export async function fetchUploadStatus(
  collectionId: string
): Promise<UploadProgress | null> {
  const res = await fetch(
    `${RAG}/collections/${collectionId}/documents/upload-jobs/status`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to fetch upload status");
  }
  return res.json();
}

export async function deleteDocument(
  collectionId: string,
  documentId: string
): Promise<void> {
  const res = await authenticatedFetch(
    `${RAG}/collections/${collectionId}/documents/${documentId}`,
    { method: "DELETE", headers: withRagIdempotency() }
  );
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to delete document");
  }
}

export async function searchDocuments(
  collectionId: string,
  input: SearchInput
): Promise<SearchResult[]> {
  const res = await authenticatedFetch(
    `${RAG}/collections/${collectionId}/documents/search`,
    {
      method: "POST",
      headers: withRagIdempotency({ "Content-Type": "application/json" }),
      body: JSON.stringify(input),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Search failed");
  }
  return res.json();
}

// ============================================================================
// API Functions — Graph RAG
// ============================================================================

export async function buildGraph(input: GraphBuildInput): Promise<void> {
  const res = await authenticatedFetch(`${RAG}/graph/build`, {
    method: "POST",
    headers: withRagIdempotency({ "Content-Type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to start graph build");
  }
}

export async function pauseGraphBuild(collectionId: string): Promise<void> {
  const res = await authenticatedFetch(
    `${RAG}/graph/build/${collectionId}/pause`,
    {
      method: "POST",
      headers: withRagIdempotency(),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to pause graph build");
  }
}

export async function resumeGraphBuild(collectionId: string): Promise<void> {
  const res = await authenticatedFetch(
    `${RAG}/graph/build/${collectionId}/resume`,
    {
      method: "POST",
      headers: withRagIdempotency(),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to resume graph build");
  }
}

export async function stopGraphBuild(collectionId: string): Promise<void> {
  const res = await authenticatedFetch(
    `${RAG}/graph/build/${collectionId}/stop`,
    {
      method: "POST",
      headers: withRagIdempotency(),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to stop graph build");
  }
}

export async function deleteGraph(collectionId: string): Promise<void> {
  const res = await authenticatedFetch(
    `${RAG}/graph/collections/${collectionId}`,
    {
      method: "DELETE",
      headers: withRagIdempotency(),
    }
  );
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to delete graph");
  }
}

export async function fetchGraphBuildStatus(
  collectionId: string
): Promise<GraphBuildStatusResponse> {
  const res = await fetch(`${RAG}/graph/build/${collectionId}/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to fetch build status");
  }
  return res.json();
}

export async function searchGraph(
  input: GraphSearchInput
): Promise<GraphSearchResult> {
  const res = await authenticatedFetch(`${RAG}/graph/search`, {
    method: "POST",
    headers: withRagIdempotency({ "Content-Type": "application/json" }),
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Graph search failed");
  }
  return res.json();
}

export async function checkGraphHealth(): Promise<{ status: string }> {
  const res = await fetch(`${RAG}/graph/health`);
  if (!res.ok) {
    throw new Error("Graph service is unavailable");
  }
  return res.json();
}

// ============================================================================
// API Functions — Graph Visualization
// ============================================================================

export async function fetchScalableGraphData(
  collectionId: string,
  params: {
    mode?: string;
    nodeLimit?: number;
    edgeLimit?: number;
    clusterLabel?: string;
    nodeId?: string;
    depth?: number;
  } = {}
): Promise<ClusteredGraphData> {
  const query = new URLSearchParams({
    mode: params.mode ?? "auto",
    node_limit: String(params.nodeLimit ?? 500),
    edge_limit: String(params.edgeLimit ?? 1000),
  });
  if (params.clusterLabel) query.set("cluster_label", params.clusterLabel);
  if (params.nodeId) query.set("node_id", params.nodeId);
  if (params.depth != null) query.set("depth", String(params.depth));
  const res = await fetch(
    `${RAG}/graph/collections/${collectionId}/data/scalable?${query}`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to fetch graph data");
  }
  return res.json();
}

export async function fetchFlatGraphData(
  collectionId: string,
  params: { nodeLimit?: number; edgeLimit?: number } = {}
): Promise<GraphData> {
  const query = new URLSearchParams({
    node_limit: String(params.nodeLimit ?? 200),
    edge_limit: String(params.edgeLimit ?? 500),
  });
  const res = await fetch(
    `${RAG}/graph/collections/${collectionId}/data?${query}`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to fetch flat graph data");
  }
  return res.json();
}

export async function fetchGraphLabelsPaginated(
  collectionId: string,
  params: {
    page?: number;
    pageSize?: number;
    search?: string;
    scopeLabel?: string;
    relTypeFilter?: string[];
  } = {}
): Promise<PaginatedCounts> {
  const query = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 25),
  });
  if (params.search) query.set("search", params.search);
  if (params.scopeLabel) query.set("scope_label", params.scopeLabel);
  params.relTypeFilter?.forEach((rt) => query.append("rel_type_filter", rt));
  const res = await fetch(
    `${RAG}/graph/collections/${collectionId}/stats/labels?${query}`
  );
  if (!res.ok) throw new Error("Failed to fetch labels");
  return res.json();
}

export async function fetchGraphRelTypesPaginated(
  collectionId: string,
  params: {
    page?: number;
    pageSize?: number;
    search?: string;
    scopeLabel?: string;
    labelFilter?: string[];
    scopeSkip?: number;
    scopeLimit?: number;
  } = {}
): Promise<PaginatedCounts> {
  const query = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 25),
  });
  if (params.search) query.set("search", params.search);
  if (params.scopeLabel) query.set("scope_label", params.scopeLabel);
  params.labelFilter?.forEach((l) => query.append("label_filter", l));
  if (params.scopeSkip != null)
    query.set("scope_skip", String(params.scopeSkip));
  if (params.scopeLimit != null)
    query.set("scope_limit", String(params.scopeLimit));
  const res = await fetch(
    `${RAG}/graph/collections/${collectionId}/stats/relationship-types?${query}`
  );
  if (!res.ok) throw new Error("Failed to fetch relationship types");
  return res.json();
}

export async function searchGraphEntityClusters(
  collectionId: string,
  q: string,
  scopeLabel?: string
): Promise<Record<string, number>> {
  const params = new URLSearchParams({ q });
  if (scopeLabel) params.set("scope_label", scopeLabel);
  const res = await fetch(
    `${RAG}/graph/collections/${collectionId}/search/entity-clusters?${params}`
  );
  if (!res.ok) throw new Error("Failed to search entity clusters");
  return res.json();
}
