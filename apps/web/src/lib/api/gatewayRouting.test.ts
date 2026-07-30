import { buildServiceUrl, canonicalServicePath } from "@/lib/api/gatewayRouting";

describe("gateway service routing", () => {
  it("normalizes legacy api paths to api v1", () => {
    expect(canonicalServicePath("agent", "/api/chat/send-chat-message")).toBe(
      "/api/v1/chat/send-chat-message"
    );
    expect(canonicalServicePath("user", "/api/auth/type")).toBe(
      "/api/v1/auth/type"
    );
  });

  it("adds service scope when the base URL points at Kong", () => {
    expect(
      buildServiceUrl(
        "http://kong:8000",
        "rag",
        "/collections"
      ).toString()
    ).toBe("http://kong:8000/rag-service/api/v1/collections");
  });

  it("does not add service scope for direct service URLs", () => {
    expect(
      buildServiceUrl(
        "http://rag-service:8083",
        "rag",
        "/collections"
      ).toString()
    ).toBe("http://rag-service:8083/api/v1/collections");
  });

  it("keeps already service-scoped gateway bases stable", () => {
    expect(
      buildServiceUrl(
        "http://kong:8000/user-service",
        "user",
        "/api/users/me"
      ).toString()
    ).toBe("http://kong:8000/user-service/api/v1/users/me");
  });
});
