import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import { parseResponseModel } from "@/lib/api/responseModel";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

import { Tag } from "@/lib/types";
import type {
  RagCollection,
  CreateCollectionInput,
  RagDocument,
  RagDocumentChunksResponse,
  UploadDocumentsResponse,
  UploadJobStartResponse,
  UploadProgress,
  SearchResult,
  SearchInput,
  GraphBuildStatusResponse,
  GraphStats,
  GraphBuildInput,
  GraphSearchInput,
  GraphData,
  ClusteredGraphData,
  GraphSearchResult,
} from "@/lib/api/domains/knowledge/types";
import type {
  EmbeddingCredentialPayload,
  KnowledgeEntityTypeUpdate,
} from "@/lib/api/domains/knowledge/types";
import type { SavedSearchSettings } from "@/lib/api/domains/knowledge/search-settings-types";
import {
  knowledgeGraphSchema,
  knowledgeSearchResponseSchema,
  knowledgeSearchSourcesSchema,
} from "@/lib/api/domains/knowledge/knowledge-search-types";
import type {
  KnowledgeGraph,
  KnowledgeNeighborhoodRequest,
  KnowledgeSearchRequest,
  KnowledgeSearchResponse,
  KnowledgeSearchSource,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

// ============================================================================
// SWR Hooks
// ============================================================================

async function throwKnowledgeFetchError(response: Response): Promise<never> {
  const parsedError = await parseApiErrorResponse(response);
  throw new FetchError(
    parsedError.userMessage,
    response.status,
    parsedError.raw,
    parsedError
  );
}

async function fetchKnowledgeSWRJson<T>(path: string): Promise<T> {
  const response = await apiRequest(path, {
    headers: { "X-Language": i18n.language },
  });
  if (!response.ok) return throwKnowledgeFetchError(response);
  try {
    return (await response.json()) as T;
  } catch {
    return {} as T;
  }
}

async function fetchAgentKnowledgeJson<T>(path: string): Promise<T> {
  const response = await apiRequest(path, {
    headers: { "X-Language": i18n.language },
  });
  return parseResponseModel<T>(response);
}

export const fetchSearchProviders = <T>() =>
  fetchAgentKnowledgeJson<T>(knowledgeEndpoints.searchProviders.browserPath);
export const fetchContentProviders = <T>() =>
  fetchAgentKnowledgeJson<T>(
    knowledgeEndpoints.createContentProvider.browserPath
  );
export const fetchMigrationStatus = <T>() =>
  fetchKnowledgeSWRJson<T>(knowledgeEndpoints.migrationStatus.browserPath);
export const fetchMigrationRetrievalStatus = <T>() =>
  fetchKnowledgeSWRJson<T>(
    knowledgeEndpoints.updateMigrationRetrieval.browserPath
  );
export const fetchMostReactedDocuments = <T>(
  ascending: boolean,
  limit: number
) =>
  fetchKnowledgeSWRJson<T>(
    knowledgeEndpoints.updateDocumentBoost(ascending, limit).browserPath
  );

// ============================================================================
// API Functions — Collections
// ============================================================================

export async function createCollection(
  input: CreateCollectionInput
): Promise<RagCollection> {
  const res = await apiRequest(knowledgeEndpoints.ragCollections.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseResponseModel<RagCollection>(res) as Promise<RagCollection>;
}

export async function updateCollection(
  id: string,
  input: Partial<CreateCollectionInput>
): Promise<RagCollection> {
  const res = await apiRequest(
    knowledgeEndpoints.ragCollection(id).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
  return parseResponseModel<RagCollection>(res) as Promise<RagCollection>;
}

export async function deleteCollection(id: string): Promise<void> {
  const res = await apiRequest(
    knowledgeEndpoints.ragCollection(id).browserPath,
    {
      method: "DELETE",
    }
  );
  await parseResponseModel<unknown>(res);
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
  const res = await apiRequest(
    knowledgeEndpoints.ragCollectionDocuments(collectionId).browserPath,
    {
      method: "POST",
      body: formData,
    }
  );
  return parseResponseModel<UploadDocumentsResponse>(
    res
  ) as Promise<UploadDocumentsResponse>;
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
  const res = await apiRequest(
    knowledgeEndpoints.ragCollectionDocumentUploadJobs(collectionId)
      .browserPath,
    { method: "POST", body: formData }
  );
  return parseResponseModel<UploadJobStartResponse>(
    res
  ) as Promise<UploadJobStartResponse>;
}

export async function fetchUploadStatus(
  collectionId: string
): Promise<UploadProgress | null> {
  const res = await apiRequest(
    knowledgeEndpoints.ragCollectionDocumentUploadJobsStatus(collectionId)
      .browserPath
  );
  return parseResponseModel<UploadProgress | null>(
    res
  ) as Promise<UploadProgress | null>;
}

export async function deleteDocument(
  collectionId: string,
  documentId: string
): Promise<void> {
  const res = await apiRequest(
    knowledgeEndpoints.ragCollectionDocument(collectionId, documentId)
      .browserPath,
    { method: "DELETE" }
  );
  await parseResponseModel<unknown>(res);
}

export async function searchDocuments(
  collectionId: string,
  input: SearchInput
): Promise<SearchResult[]> {
  const res = await apiRequest(
    knowledgeEndpoints.ragCollectionDocumentSearch(collectionId).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }
  );
  return parseResponseModel<SearchResult[]>(res) as Promise<SearchResult[]>;
}

import type {
  DocumentSetSummary,
  StandardAnswer,
  StandardAnswerCategory,
} from "@/lib/types";

export function fetchDocumentSets(
  editable = false
): Promise<DocumentSetSummary[]> {
  return fetchKnowledgeSWRJson<DocumentSetSummary[]>(
    editable
      ? knowledgeEndpoints.editableDocumentSets.browserPath
      : knowledgeEndpoints.documentSets.browserPath
  );
}

export function fetchStandardAnswerCategories(): Promise<
  StandardAnswerCategory[]
> {
  return fetchKnowledgeSWRJson<StandardAnswerCategory[]>(
    knowledgeEndpoints.listStandardAnswerCategories.browserPath
  );
}

export function fetchStandardAnswers(): Promise<StandardAnswer[]> {
  return fetchKnowledgeSWRJson<StandardAnswer[]>(
    knowledgeEndpoints.listStandardAnswers.browserPath
  );
}

export function fetchKnowledgeGraphExposed(): Promise<boolean> {
  return fetchKnowledgeSWRJson<boolean>(
    knowledgeEndpoints.knowledgeGraphExposed.browserPath
  );
}

export function fetchEmbeddingModels<T>(): Promise<T> {
  return fetchKnowledgeSWRJson<T>(
    knowledgeEndpoints.embeddingModels.browserPath
  );
}
export function fetchEmbeddingProviders<T>(): Promise<T> {
  return fetchKnowledgeSWRJson<T>(
    knowledgeEndpoints.saveEmbeddingCredential.browserPath
  );
}

// ============================================================================
// API Functions — Graph RAG
// ============================================================================

export async function buildGraph(input: GraphBuildInput): Promise<void> {
  const res = await apiRequest(knowledgeEndpoints.ragGraphBuild.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  await parseResponseModel<unknown>(res);
}

export async function pauseGraphBuild(collectionId: string): Promise<void> {
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphBuildControl(collectionId, "pause").browserPath,
    { method: "POST" }
  );
  await parseResponseModel<unknown>(res);
}

export async function resumeGraphBuild(collectionId: string): Promise<void> {
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphBuildControl(collectionId, "resume").browserPath,
    { method: "POST" }
  );
  await parseResponseModel<unknown>(res);
}

export async function stopGraphBuild(collectionId: string): Promise<void> {
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphBuildControl(collectionId, "stop").browserPath,
    {
      method: "POST",
    }
  );
  await parseResponseModel<unknown>(res);
}

export async function deleteGraph(collectionId: string): Promise<void> {
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphCollection(collectionId).browserPath,
    {
      method: "DELETE",
    }
  );
  await parseResponseModel<unknown>(res);
}

export async function fetchGraphBuildStatus(
  collectionId: string
): Promise<GraphBuildStatusResponse | null> {
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphBuildStatus(collectionId).browserPath
  );
  return parseResponseModel<GraphBuildStatusResponse | null>(
    res
  ) as Promise<GraphBuildStatusResponse | null>;
}

export async function searchGraph(
  input: GraphSearchInput
): Promise<GraphSearchResult> {
  const res = await apiRequest(knowledgeEndpoints.ragGraphSearch.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseResponseModel<GraphSearchResult>(
    res
  ) as Promise<GraphSearchResult>;
}

// ============================================================================
// API Functions — Knowledge Search
// ============================================================================

async function postKnowledgeJson(
  path: string,
  body: unknown,
  signal?: AbortSignal
): Promise<unknown> {
  const response = await apiRequest(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Language": i18n.language,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) return throwKnowledgeFetchError(response);
  return response.json();
}

/** Search documents and knowledge graphs of every readable collection. */
export async function searchKnowledge(
  request: KnowledgeSearchRequest,
  signal?: AbortSignal
): Promise<KnowledgeSearchResponse> {
  const body = await postKnowledgeJson(
    knowledgeEndpoints.ragSearch.browserPath,
    {
      query: request.query,
      kind: request.kind,
      limit: request.limit,
      ...(request.collectionIds && { collection_ids: request.collectionIds }),
      ...(request.fileTypes && { file_types: request.fileTypes }),
      ...(request.entityLabels && { entity_labels: request.entityLabels }),
    },
    signal
  );
  return knowledgeSearchResponseSchema.parse(body);
}

/** Collections the knowledge search page can search. */
export async function fetchKnowledgeSearchSources(): Promise<
  KnowledgeSearchSource[]
> {
  const body = await fetchKnowledgeSWRJson<unknown>(
    knowledgeEndpoints.ragSearchSources.browserPath
  );
  return knowledgeSearchSourcesSchema.parse(body);
}

/** Merged ego graph around nodes of one collection. */
export async function fetchKnowledgeNeighborhood(
  request: KnowledgeNeighborhoodRequest,
  signal?: AbortSignal
): Promise<KnowledgeGraph> {
  const body = await postKnowledgeJson(
    knowledgeEndpoints.ragSearchNeighborhood.browserPath,
    {
      collection_id: request.collectionId,
      node_ids: request.nodeIds,
      depth: request.depth,
      limit: request.limit,
    },
    signal
  );
  return knowledgeGraphSchema.parse(body);
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
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphCollectionData(collectionId, query, true)
      .browserPath
  );
  return parseResponseModel<ClusteredGraphData>(
    res
  ) as Promise<ClusteredGraphData>;
}

export async function fetchFlatGraphData(
  collectionId: string,
  params: { nodeLimit?: number; edgeLimit?: number } = {}
): Promise<GraphData> {
  const query = new URLSearchParams({
    node_limit: String(params.nodeLimit ?? 200),
    edge_limit: String(params.edgeLimit ?? 500),
  });
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphCollectionData(collectionId, query).browserPath
  );
  return parseResponseModel<GraphData>(res) as Promise<GraphData>;
}

export async function searchGraphEntityClusters(
  collectionId: string,
  q: string,
  scopeLabel?: string
): Promise<Record<string, number>> {
  const params = new URLSearchParams({ q });
  if (scopeLabel) params.set("scope_label", scopeLabel);
  const res = await apiRequest(
    knowledgeEndpoints.ragGraphCollectionEntityClusters(
      collectionId,
      params.toString()
    ).browserPath
  );
  return parseResponseModel<Record<string, number>>(res) as Promise<
    Record<string, number>
  >;
}

export async function fetchValidTags(): Promise<Tag[]> {
  const res = await apiRequest(knowledgeEndpoints.validTags.browserPath);
  const result = await parseJsonResponse<{ tags: Tag[] }>(res);
  return result?.tags ?? [];
}

// Re-export types and helpers for convenience
export type {
  RagCollection,
  CreateCollectionInput,
  RagDocument,
  RagChunk,
  RagChunkStats,
  RagDocumentChunksResponse,
  UploadDocumentsResponse,
  UploadJobStatus,
  UploadJobStartResponse,
  UploadProgress,
  SearchResult,
  SearchInput,
  GraphBuildStatus,
  GraphBuildStatusResponse,
  GraphStats,
  GraphBuildInput,
  SearchType,
  GraphSearchInput,
  GraphNode,
  GraphEdge,
  GraphData,
  ClusterNode,
  ClusterEdge,
  ScalableNode,
  ScalableEdge,
  GraphViewMode,
  ClusteredGraphData,
  ForceGraphNode,
  ForceGraphLink,
  ForceGraphData,
  PaginatedCountItem,
  PaginatedCounts,
  GraphSearchResult,
} from "@/lib/api/domains/knowledge/types";

export {
  isClusterNode,
  isClusterEdge,
  CHUNKS_PAGE_SIZE,
  getDocumentChunksPageKey,
} from "@/lib/api/domains/knowledge/types";

import { Filters } from "@/lib/search/interfaces";

export const adminSearch = async (query: string, filters: Filters) => {
  const response = await apiRequest(
    knowledgeEndpoints.adminSearch.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        filters,
      }),
    }
  );
  return response;
};

export const updateBoost = async (documentId: string, boost: number) => {
  const response = await apiRequest(
    knowledgeEndpoints.updateBoost.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        document_id: documentId,
        boost,
      }),
    }
  );
  if (response.ok) {
    return null;
  }
  return (await parseApiErrorResponse(response)).userMessage;
};

export const updateHiddenStatus = async (
  documentId: string,
  isHidden: boolean
) => {
  const response = await apiRequest(
    knowledgeEndpoints.updateHiddenStatus.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        document_id: documentId,
        hidden: isHidden,
      }),
    }
  );
  return response;
};

import {
  DocumentSetCreationRequest,
  DocumentSetUpdateRequest,
} from "@/lib/api/domains/knowledge/document-set-types";
import i18n from "@/i18n/config";

export const createDocumentSet = async ({
  name,
  description,
  cc_pair_ids,
  is_public,
  users,
  groups,
  federated_connectors,
}: DocumentSetCreationRequest) => {
  return apiRequest(knowledgeEndpoints.createDocumentSet.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      description,
      cc_pair_ids,
      is_public,
      users,
      groups,
      federated_connectors,
    }),
  });
};

export const updateDocumentSet = async ({
  id,
  description,
  cc_pair_ids,
  is_public,
  users,
  groups,
  federated_connectors,
}: DocumentSetUpdateRequest) => {
  return apiRequest(knowledgeEndpoints.createDocumentSet.browserPath, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      id,
      description,
      cc_pair_ids,
      is_public,
      users,
      groups,
      federated_connectors,
    }),
  });
};

export const deleteDocumentSet = async (id: number) => {
  return apiRequest(knowledgeEndpoints.deleteDocumentSet(id).browserPath, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
  });
};

export const deleteSearchSettings = async (search_settings_id: number) => {
  const response = await apiRequest(
    knowledgeEndpoints.deleteSearchSettings.browserPath,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ search_settings_id }),
    }
  );
  return response;
};

export const testEmbedding = async ({
  provider_type,
  modelName,
  apiKey,
  apiUrl,
  apiVersion,
  deploymentName,
}: {
  provider_type: string;
  modelName: string;
  apiKey: string | null;
  apiUrl: string | null;
  apiVersion: string | null;
  deploymentName: string | null;
}) => {
  const testModelName =
    provider_type === "openai" ? "text-embedding-3-small" : modelName;

  const testResponse = await apiRequest(
    knowledgeEndpoints.testEmbedding.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider_type: provider_type,
        api_key: apiKey,
        api_url: apiUrl,
        model_name: testModelName,
        api_version: apiVersion,
        deployment_name: deploymentName,
      }),
    }
  );

  return testResponse;
};

export function crawlDocumentEntry(payload: {
  url: string;
}): Promise<Response> {
  return apiRequest(knowledgeEndpoints.crawlDocumentEntry.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function cancelEmbeddingUpgrade(): Promise<Response> {
  return apiRequest(knowledgeEndpoints.cancelEmbeddingUpgrade.browserPath, {
    method: "POST",
  });
}

export function activateSearchProvider(providerId: number): Promise<Response> {
  return apiRequest(
    knowledgeEndpoints.activateSearchProvider(providerId).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
}

export function deactivateSearchProvider(
  providerId: number
): Promise<Response> {
  return apiRequest(
    knowledgeEndpoints.deactivateSearchProvider(providerId).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
}

export function resetContentProvider(): Promise<Response> {
  return apiRequest(knowledgeEndpoints.resetContentProvider.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  }).then(agentServicePayloadResponse);
}

export function activateContentProvider(id: number): Promise<Response> {
  return apiRequest(
    knowledgeEndpoints.activateContentProvider(id).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  ).then(agentServicePayloadResponse);
}

export function deactivateContentProvider(id: number): Promise<Response> {
  return apiRequest(
    knowledgeEndpoints.deactivateContentProvider(id).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  ).then(agentServicePayloadResponse);
}

export function createContentProvider(payload: {
  id: null;
  name: string;
  provider_type: "firecrawl" | "exa" | (string & {});
  api_key: null;
  api_key_changed: boolean;
  config: Record<string, string> | null;
  activate: boolean;
}): Promise<Response> {
  return apiRequest(knowledgeEndpoints.createContentProvider.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function updateMigrationRetrieval(payload: {
  enable_opensearch_retrieval: boolean;
}): Promise<Response> {
  return apiRequest(knowledgeEndpoints.updateMigrationRetrieval.browserPath, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateInferenceSettings(
  payload: SavedSearchSettings
): Promise<Response> {
  return apiRequest(knowledgeEndpoints.updateInferenceSettings.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function reindexSearchSettings(
  payload: SavedSearchSettings
): Promise<Response> {
  return apiRequest(knowledgeEndpoints.reindexSearchSettings.browserPath, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export function updateKnowledgeEntityTypes(
  payload: KnowledgeEntityTypeUpdate[]
): Promise<Response> {
  return apiRequest(knowledgeEndpoints.toggleKnowledgeEntityType.browserPath, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteEmbeddingCredential(
  pathValue: string
): Promise<Response> {
  return apiRequest(
    knowledgeEndpoints.deleteEmbeddingCredential(pathValue).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function saveEmbeddingCredential(
  payload: EmbeddingCredentialPayload
): Promise<Response> {
  return apiRequest(knowledgeEndpoints.saveEmbeddingCredential.browserPath, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function testWebProvider(
  category: "search" | "content",
  payload: import("@/lib/api/domains/knowledge/provider-types").ProviderTestPayload
): Promise<Response> {
  const request = apiRequest(
    knowledgeEndpoints.testWebProvider(category).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return category === "content"
    ? request.then(agentServicePayloadResponse)
    : request;
}

export function upsertWebProvider(
  category: "search" | "content",
  payload: import("@/lib/api/domains/knowledge/provider-types").ProviderUpsertPayload
): Promise<Response> {
  return apiRequest(
    knowledgeEndpoints.upsertWebProvider(category).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function testEmbeddingConfiguration(
  payload: Record<string, unknown>
): Promise<Response> {
  return apiRequest(knowledgeEndpoints.testEmbedding.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function fetchRagSWRJson<T>(path: string): Promise<T> {
  const response = await apiRequest(path, {
    headers: { "X-Language": i18n.language },
  });
  return parseResponseModel<T>(response);
}

export function fetchCollectionList(): Promise<RagCollection[]> {
  return fetchRagSWRJson(knowledgeEndpoints.ragCollections.browserPath);
}
export function fetchCollectionDocuments(
  id: string,
  limit: number,
  offset: number
): Promise<RagDocument[]> {
  return fetchRagSWRJson(
    knowledgeEndpoints.knowledgeDocuments(id, limit, offset).browserPath
  );
}
export function fetchCollectionChunks(
  id: string,
  documentId: string,
  offset: number
): Promise<RagDocumentChunksResponse> {
  return fetchRagSWRJson(
    knowledgeEndpoints.knowledgeChunks(id, documentId, offset).browserPath
  );
}
export function fetchGraphBuildStatusForPolling(
  id: string
): Promise<GraphBuildStatusResponse | null> {
  return fetchRagSWRJson(
    knowledgeEndpoints.ragGraphBuildStatus(id).browserPath
  );
}
export function fetchUploadStatusForPolling(
  id: string
): Promise<UploadProgress | null> {
  return fetchRagSWRJson(
    knowledgeEndpoints.ragCollectionDocumentUploadJobsStatus(id).browserPath
  );
}
export function fetchCollectionGraphStats(id: string): Promise<GraphStats> {
  return fetchRagSWRJson(
    knowledgeEndpoints.ragGraphCollectionStats(id).browserPath
  );
}
export function fetchGraphCollectionList(): Promise<string[]> {
  return fetchRagSWRJson(knowledgeEndpoints.ragGraphCollections().browserPath);
}
