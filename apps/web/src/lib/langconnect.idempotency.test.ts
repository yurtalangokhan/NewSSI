import {
  buildGraph,
  createCollection,
  deleteGraph,
  pauseGraphBuild,
  uploadDocuments,
} from "@/lib/langconnect";

jest.mock("@/lib/api/idempotency", () => ({
  ...jest.requireActual("@/lib/api/idempotency"),
  createIdempotencyKey: jest.fn(() => "rag-operation-key"),
}));

function mockJsonResponse(body: unknown = {}, init: ResponseInit = {}) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
      ...init,
    })
  );
}

describe("LangConnect idempotency", () => {
  beforeEach(() => {
    jest.spyOn(global, "fetch").mockImplementation(() =>
      mockJsonResponse({
        uuid: "collection-1",
        name: "Knowledge",
        success: true,
      })
    );
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("sends idempotency keys for RAG collection creation", async () => {
    await createCollection({ name: "Knowledge" });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/rag/collections",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Idempotency-Key": "rag-operation-key",
        }),
      })
    );
  });

  it("sends idempotency keys for RAG document upload", async () => {
    const file = new File(["hello"], "hello.txt", { type: "text/plain" });

    await uploadDocuments("collection-1", [file]);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/rag/collections/collection-1/documents",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Idempotency-Key": "rag-operation-key",
        }),
      })
    );
  });

  it.each([
    ["build", () => buildGraph({ collection_id: "collection-1" })],
    ["pause", () => pauseGraphBuild("collection-1")],
    ["delete", () => deleteGraph("collection-1")],
  ])(
    "sends idempotency keys for graph %s operations",
    async (_name, action) => {
      await action();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            "Idempotency-Key": "rag-operation-key",
          }),
        })
      );
    }
  );
});
