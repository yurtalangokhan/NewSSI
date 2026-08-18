import {
  getDocumentChunksPageKey,
  type RagDocumentChunksResponse,
} from "@/lib/langconnect";

describe("getDocumentChunksPageKey", () => {
  it("returns null when there is no collection or document selected", () => {
    expect(getDocumentChunksPageKey(0, null, null, "doc-1")).toBeNull();
    expect(getDocumentChunksPageKey(0, null, "col-1", null)).toBeNull();
  });

  it("builds the first page key with limit and offset 0", () => {
    expect(getDocumentChunksPageKey(0, null, "col-1", "doc-1")).toBe(
      "/api/rag/collections/col-1/documents/doc-1/chunks?limit=20&offset=0"
    );
  });

  it("builds subsequent page keys with an incrementing offset", () => {
    const previousPage: RagDocumentChunksResponse = {
      stats: { total_chunks: 100, avg_chars: 10, avg_tokens: 3 },
      chunks: [],
      total_chunks: 100,
      has_more: true,
    };

    expect(getDocumentChunksPageKey(2, previousPage, "col-1", "doc-1")).toBe(
      "/api/rag/collections/col-1/documents/doc-1/chunks?limit=20&offset=40"
    );
  });

  it("returns null once the previous page reports no more chunks", () => {
    const previousPage: RagDocumentChunksResponse = {
      stats: { total_chunks: 5, avg_chars: 10, avg_tokens: 3 },
      chunks: [],
      total_chunks: 5,
      has_more: false,
    };

    expect(
      getDocumentChunksPageKey(1, previousPage, "col-1", "doc-1")
    ).toBeNull();
  });
});
