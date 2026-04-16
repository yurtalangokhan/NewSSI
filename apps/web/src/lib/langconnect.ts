/**
 * LangConnect RAG service types, SWR hooks, and API functions.
 *
 * All calls go through /api/rag/[...path] (Next.js API route proxy).
 * That proxy injects X-Internal-Service-Token so RAG auth passes.
 *
 * Pattern mirrors lib/airbyte.ts from the Onyx codebase.
 */
import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";

const RAG = "/api/rag";

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
}

export interface UploadDocumentsResponse {
  success: boolean;
  message: string;
  added_chunk_ids: string[];
  warnings?: string;
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

export interface GraphSearchInput {
  query: string;
  collection_id: string;
  limit?: number;
  search_type?: "entity" | "cypher" | "hybrid";
  vector_weight?: number;
  graph_weight?: number;
}

export interface GraphSearchResult {
  nodes: Array<{
    id: string;
    label: string;
    name: string;
    properties: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    type: string;
    properties: Record<string, unknown>;
  }>;
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

export function useDocumentChunks(
  collectionId: string | null,
  documentId: string | null
) {
  const { data, error, isLoading, mutate } =
    useSWR<RagDocumentChunksResponse>(
      collectionId && documentId
        ? `${RAG}/collections/${collectionId}/documents/${documentId}/chunks`
        : null,
      errorHandlingFetcher
    );
  return {
    chunks: data?.chunks ?? [],
    stats: data?.stats ?? null,
    isLoading,
    error,
    mutate,
  };
}

export function useGraphBuildStatus(
  collectionId: string | null,
  active: boolean
) {
  const { data, error, isLoading, mutate } =
    useSWR<GraphBuildStatusResponse>(
      active && collectionId
        ? `${RAG}/graph/build/${collectionId}/status`
        : null,
      errorHandlingFetcher,
      { refreshInterval: 2_000 }
    );
  return { status: data ?? null, isLoading, error, mutate };
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
  const res = await fetch(`${RAG}/collections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await fetch(`${RAG}/collections/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to update collection");
  }
  return res.json();
}

export async function deleteCollection(id: string): Promise<void> {
  const res = await fetch(`${RAG}/collections/${id}`, { method: "DELETE" });
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
  const res = await fetch(
    `${RAG}/collections/${collectionId}/documents`,
    { method: "POST", body: formData }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to upload documents");
  }
  return res.json();
}

export async function deleteDocument(
  collectionId: string,
  documentId: string
): Promise<void> {
  const res = await fetch(
    `${RAG}/collections/${collectionId}/documents/${documentId}`,
    { method: "DELETE" }
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
  const res = await fetch(
    `${RAG}/collections/${collectionId}/documents/search`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
  const res = await fetch(`${RAG}/graph/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to start graph build");
  }
}

export async function deleteGraph(collectionId: string): Promise<void> {
  const res = await fetch(`${RAG}/graph/collections/${collectionId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to delete graph");
  }
}

export async function searchGraph(
  input: GraphSearchInput
): Promise<GraphSearchResult> {
  const res = await fetch(`${RAG}/graph/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
