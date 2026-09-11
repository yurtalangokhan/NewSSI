import { isEmbeddingModel, isChatModel } from "./modelClassification";

describe("modelClassification", () => {
  it("detects embedding model from supports_embedding flag", () => {
    expect(isEmbeddingModel({ supports_embedding: true })).toBe(true);
    expect(isEmbeddingModel({ supports_embedding: false })).toBe(false);
    expect(isChatModel({ supports_embedding: false })).toBe(true);
  });

  it("detects embedding model from nested metadata supports_embedding", () => {
    expect(isEmbeddingModel({ metadata: { supports_embedding: true } })).toBe(
      true
    );
    expect(isEmbeddingModel({ metadata: { supports_embedding: false } })).toBe(
      false
    );
  });

  it("detects embedding model from model_type flag", () => {
    expect(isEmbeddingModel({ model_type: "embedding" })).toBe(true);
    expect(isEmbeddingModel({ model_type: "embeddings" })).toBe(true);
    expect(isEmbeddingModel({ model_type: "language" })).toBe(false);
    expect(isEmbeddingModel({ metadata: { model_type: "embedding" } })).toBe(
      true
    );
  });

  it("detects embedding model from capabilities list", () => {
    expect(isEmbeddingModel({ capabilities: ["embedding"] })).toBe(true);
    expect(isEmbeddingModel({ capabilities: ["completion", "vision"] })).toBe(
      false
    );
    expect(
      isEmbeddingModel({ metadata: { capabilities: ["embedding"] } })
    ).toBe(true);
  });

  it("returns false for null or undefined", () => {
    expect(isEmbeddingModel(null)).toBe(false);
    expect(isEmbeddingModel(undefined)).toBe(false);
    expect(isChatModel(null)).toBe(true);
  });
});
