/** Backend mapping for the existing /api/rag catch-all route. */

// ============================================================================
// Endpoint descriptors
// ============================================================================

// ============================================================================
// Path builder functions
// ============================================================================

// ── Collection endpoints ──────────────────────────────────────────────────────

// ── Document endpoints ────────────────────────────────────────────────────────

// ── Graph endpoints ──────────────────────────────────────────────────────────

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const knowledgeEndpoints = {
  webSearchProxyTarget: (segments: string[]) =>
    ({
      backend: {
        service: "agent",
        path: `/api/v1/admin/web-search/${segments.join("/")}`,
      },
    }) as const,
  listStandardAnswerCategories: {
    method: "GET",
    browserPath: "/api/manage/admin/standard-answer/category",
    backend: {
      service: "agent",
      path: "/api/v1/manage/admin/standard-answer/category",
    },
  },
  listStandardAnswers: {
    method: "GET",
    browserPath: "/api/manage/admin/standard-answer",
    backend: { service: "agent", path: "/api/v1/manage/admin/standard-answer" },
  },
  documentSets: {
    method: "GET",
    browserPath: "/api/manage/document-set",
    backend: { service: "agent", path: "/api/v1/manage/document-set" },
  },
  rag: { browserPath: "/api/rag" },
  ragCollections: { browserPath: "/api/rag/collections" },
  ragProxyTarget: (
    segments: string[]
  ): { backend: import("@/lib/api/http/types").BackendTarget } => {
    const relative = segments.join("/");
    const path =
      relative === "api/v1" || relative.startsWith("api/v1/")
        ? `/${relative}`
        : `/api/v1/${relative.replace(/^api\//, "")}`;
    return { backend: { service: "rag", path } as const };
  },
  ragCollection: (collectionId: string): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.ragCollections.browserPath}/${collectionId}`,
    };
  },
  ragCollectionDocuments: (collectionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragCollection(collectionId).browserPath
      }/documents`,
    };
  },
  ragCollectionDocumentUploadJobs: (
    collectionId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragCollectionDocuments(collectionId).browserPath
      }/upload-jobs`,
    };
  },
  ragCollectionDocument: (
    collectionId: string,
    documentId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragCollectionDocuments(collectionId).browserPath
      }/${documentId}`,
    };
  },
  ragCollectionDocumentSearch: (
    collectionId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragCollectionDocuments(collectionId).browserPath
      }/search`,
    };
  },
  validTags: { browserPath: "/api/query/valid-tags" },
  ragCollectionDocumentUploadJobsStatus: (
    collectionId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragCollectionDocumentUploadJobs(collectionId)
          .browserPath
      }/status`,
    };
  },
  ragGraphBuildStatus: (collectionId: string): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.rag.browserPath}/graph/build/${collectionId}/status`,
    };
  },
  ragGraphBuild: { browserPath: "/api/rag/graph/build" },
  ragGraphSearch: { browserPath: "/api/rag/graph/search" },
  ragSearch: { browserPath: "/api/rag/search" },
  ragSearchSources: { browserPath: "/api/rag/search/sources" },
  ragSearchNeighborhood: { browserPath: "/api/rag/search/graph/neighborhood" },
  ragGraphBuildControl: (
    collectionId: string,
    action: "pause" | "resume" | "stop"
  ): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.ragGraphBuild.browserPath}/${collectionId}/${action}`,
    };
  },
  ragGraphCollection: (collectionId: string): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.rag.browserPath}/graph/collections/${collectionId}`,
    };
  },
  ragGraphCollectionData: (
    collectionId: string,
    query: string | URLSearchParams,
    scalable = false
  ): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragGraphCollection(collectionId).browserPath
      }/data${scalable ? "/scalable" : ""}?${query}`,
    };
  },
  ragGraphCollectionEntityClusters: (
    collectionId: string,
    query: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        knowledgeEndpoints.ragGraphCollection(collectionId).browserPath
      }/search/entity-clusters?${query}`,
    };
  },
  ragGraphCollections: (): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.rag.browserPath}/graph/collections`,
    };
  },
  ragGraphCollectionStats: (collectionId: string): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.rag.browserPath}/graph/collections/${collectionId}/stats`,
    };
  },
  adminSearch: { browserPath: "/api/admin/search" },
  updateBoost: { browserPath: "/api/manage/admin/doc-boosts" },
  updateDocumentBoost: (
    ascending: boolean,
    limit: number
  ): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.updateBoost.browserPath}?ascending=${ascending}&limit=${limit}`,
    };
  },
  updateHiddenStatus: { browserPath: "/api/manage/admin/doc-hidden" },
  createDocumentSet: { browserPath: "/api/manage/admin/document-set" },
  editableDocumentSets: {
    browserPath: "/api/manage/document-set?get_editable=true",
  },
  deleteDocumentSet: (id: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/document-set/${id}` };
  },
  deleteSearchSettings: {
    browserPath: "/api/search-settings/delete-search-settings",
  },
  testEmbedding: { browserPath: "/api/admin/embedding/test-embedding" },
  crawlDocumentEntry: {
    browserPath: "/api/admin/web-search/content-providers/crawl",
  },
  cancelEmbeddingUpgrade: {
    browserPath: "/api/search-settings/cancel-new-embedding",
  },
  activateSearchProvider: (providerId: number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/web-search/search-providers/${providerId}/activate`,
    };
  },
  deactivateSearchProvider: (providerId: number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/web-search/search-providers/${providerId}/deactivate`,
    };
  },
  resetContentProvider: {
    browserPath: "/api/admin/web-search/content-providers/reset-default",
  },
  activateContentProvider: (id: number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/web-search/content-providers/${id}/activate`,
    };
  },
  deactivateContentProvider: (id: number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/web-search/content-providers/${id}/deactivate`,
    };
  },
  createContentProvider: {
    browserPath: "/api/admin/web-search/content-providers",
  },
  searchProviders: { browserPath: "/api/admin/web-search/search-providers" },
  updateMigrationRetrieval: {
    browserPath: "/api/admin/opensearch-migration/retrieval",
  },
  migrationStatus: { browserPath: "/api/admin/opensearch-migration/status" },
  updateInferenceSettings: {
    browserPath: "/api/search-settings/update-inference-settings",
  },
  reindexSearchSettings: {
    browserPath: "/api/search-settings/set-new-search-settings",
  },
  toggleKnowledgeEntityType: { browserPath: "/api/admin/kg/entity-types" },
  knowledgeGraphExposed: { browserPath: "/api/admin/kg/exposed" },
  deleteEmbeddingCredential: (pathValue: string): { browserPath: string } => {
    return {
      browserPath: `${"/api/admin/embedding/embedding-provider"}/${pathValue}`,
    };
  },
  saveEmbeddingCredential: {
    browserPath: "/api/admin/embedding/embedding-provider",
  },
  embeddingModels: { browserPath: "/api/admin/embedding" },
  testWebProvider: (
    category: "search" | "content"
  ): { browserPath: string } => {
    return {
      browserPath: `/api/admin/web-search/${
        category === "search" ? "search-providers" : "content-providers"
      }/test`,
    };
  },
  upsertWebProvider: (
    category: "search" | "content"
  ): { browserPath: string } => {
    return {
      browserPath: `/api/admin/web-search/${
        category === "search" ? "search-providers" : "content-providers"
      }`,
    };
  },
  knowledgeDocuments: (
    id: string,
    limit: number,
    offset: number
  ): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.ragCollections.browserPath}/${id}/documents?limit=${limit}&offset=${offset}`,
    };
  },
  knowledgeChunks: (
    id: string,
    documentId: string,
    offset: number
  ): { browserPath: string } => {
    return {
      browserPath: `${knowledgeEndpoints.ragCollections.browserPath}/${id}/documents/${documentId}/chunks?limit=20&offset=${offset}`,
    };
  },
  searchProviderTest: {
    browserPath: "/api/admin/web-search/search-providers/test",
  },
  contentProviderTest: {
    browserPath: "/api/admin/web-search/content-providers/test",
  },
  editableDocumentSetsKey: {
    browserPath: "/api/manage/document-set?get_editable=true",
  },
} as const;
