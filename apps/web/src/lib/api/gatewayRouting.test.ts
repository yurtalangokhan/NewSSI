import {
  buildServiceUrl,
  canonicalServicePath,
} from "@/lib/api/gatewayRouting";

describe("gateway service routing", () => {
  it("normalizes legacy api paths to api v1", () => {
    expect(canonicalServicePath("agent", "/api/chat/send-chat-message")).toBe(
      "/api/v1/chat/send-chat-message"
    );
    expect(canonicalServicePath("user", "/api/auth/type")).toBe(
      "/api/v1/auth/type"
    );
  });

  it("maps legacy agent MCP helper paths through the proxy resource", () => {
    expect(canonicalServicePath("agent", "/mcp/tools-builtin")).toBe(
      "/api/v1/proxy/mcp/tools-builtin"
    );
  });

  it("adds service scope when the base URL points at apisix", () => {
    expect(
      buildServiceUrl("http://apisix:8000", "rag", "/collections").toString()
    ).toBe("http://apisix:8000/rag-service/api/v1/collections");
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
        "http://apisix:8000/user-service",
        "user",
        "/api/users/me"
      ).toString()
    ).toBe("http://apisix:8000/user-service/api/v1/users/me");
  });

  it("does not duplicate the MCP mount in a tools service base", () => {
    expect(
      buildServiceUrl(
        "http://apisix:8000/tools-service/mcp",
        "tools",
        "/mcp"
      ).toString()
    ).toBe("http://apisix:8000/tools-service/mcp");
  });
});
