import {
  buildGraph,
  createCollection,
  deleteGraph,
  pauseGraphBuild,
  uploadDocuments,
} from "@/lib/api/domains/knowledge/api";
import { envelopeResponse } from "@tests/setup/responseModel";

function mockJsonResponse(body: unknown = {}, init: ResponseInit = {}) {
  return Promise.resolve(envelopeResponse(body, init));
}

function expectIdempotencyKey(): void {
  const [, init] = (global.fetch as jest.MockedFunction<typeof fetch>).mock
    .calls[0]!;
  expect(new Headers(init?.headers).get("Idempotency-Key")).toEqual(
    expect.any(String)
  );
}

describe("RAG service idempotency", () => {
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
      })
    );
    expectIdempotencyKey();
  });

  it("sends idempotency keys for RAG document upload", async () => {
    const file = new File(["hello"], "hello.txt", { type: "text/plain" });

    await uploadDocuments("collection-1", [file]);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/rag/collections/collection-1/documents",
      expect.objectContaining({
        method: "POST",
      })
    );
    expectIdempotencyKey();
  });

  it.each([
    ["build", () => buildGraph({ collection_id: "collection-1" })],
    ["pause", () => pauseGraphBuild("collection-1")],
    ["delete", () => deleteGraph("collection-1")],
  ])(
    "sends idempotency keys for graph %s operations",
    async (_name, action) => {
      await action();

      expect(global.fetch).toHaveBeenCalledTimes(1);
      expectIdempotencyKey();
    }
  );
});
