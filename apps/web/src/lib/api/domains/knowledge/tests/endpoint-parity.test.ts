import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

describe("knowledge endpoint parity", () => {
  it("preserves raw collection and document identifiers", () => {
    const collectionId = "collection/ space/ç";
    const documentId = "document/ space/ü";

    expect(knowledgeEndpoints.ragCollections.browserPath).toBe(
      "/api/rag/collections"
    );
    expect(knowledgeEndpoints.ragCollection(collectionId).browserPath).toBe(
      `/api/rag/collections/${collectionId}`
    );
    expect(
      knowledgeEndpoints.ragCollectionDocuments(collectionId).browserPath
    ).toBe(`/api/rag/collections/${collectionId}/documents`);
    expect(
      knowledgeEndpoints.ragCollectionDocumentUploadJobs(collectionId)
        .browserPath
    ).toBe(`/api/rag/collections/${collectionId}/documents/upload-jobs`);
    expect(
      knowledgeEndpoints.ragCollectionDocumentUploadJobsStatus(collectionId)
        .browserPath
    ).toBe(`/api/rag/collections/${collectionId}/documents/upload-jobs/status`);
    expect(
      knowledgeEndpoints.ragCollectionDocument(collectionId, documentId)
        .browserPath
    ).toBe(`/api/rag/collections/${collectionId}/documents/${documentId}`);
    expect(
      knowledgeEndpoints.ragCollectionDocumentSearch(collectionId).browserPath
    ).toBe(`/api/rag/collections/${collectionId}/documents/search`);
  });

  it("preserves graph paths and ordered queries", () => {
    const collectionId = "collection/ space/ç";
    expect(knowledgeEndpoints.ragGraphBuild.browserPath).toBe(
      "/api/rag/graph/build"
    );
    expect(knowledgeEndpoints.ragGraphSearch.browserPath).toBe(
      "/api/rag/graph/search"
    );
    expect(
      knowledgeEndpoints.ragGraphBuildControl(collectionId, "pause").browserPath
    ).toBe(`/api/rag/graph/build/${collectionId}/pause`);
    expect(
      knowledgeEndpoints.ragGraphBuildStatus(collectionId).browserPath
    ).toBe(`/api/rag/graph/build/${collectionId}/status`);
    expect(
      knowledgeEndpoints.ragGraphCollection(collectionId).browserPath
    ).toBe(`/api/rag/graph/collections/${collectionId}`);
    expect(
      knowledgeEndpoints.ragGraphCollectionData(collectionId, "a=1&b=slash%2F")
        .browserPath
    ).toBe(`/api/rag/graph/collections/${collectionId}/data?a=1&b=slash%2F`);
    expect(
      knowledgeEndpoints.ragGraphCollectionData(
        collectionId,
        "a=1&b=slash%2F",
        true
      ).browserPath
    ).toBe(
      `/api/rag/graph/collections/${collectionId}/data/scalable?a=1&b=slash%2F`
    );
    expect(
      knowledgeEndpoints.ragGraphCollectionEntityClusters(
        collectionId,
        "q=space+%C3%A7"
      ).browserPath
    ).toBe(
      `/api/rag/graph/collections/${collectionId}/search/entity-clusters?q=space+%C3%A7`
    );
    expect(knowledgeEndpoints.updateDocumentBoost(true, 20).browserPath).toBe(
      "/api/manage/admin/doc-boosts?ascending=true&limit=20"
    );
  });
});
