import { assertGatewayRouted, GATEWAY_ROUTE_PREFIXES } from "./gateway";

const GATEWAY = "http://localhost:8000";

describe("assertGatewayRouted", () => {
  it("accepts a URL on the Gateway origin carrying a known route prefix", () => {
    expect(() =>
      assertGatewayRouted(
        "AGENT_SERVICE_URL",
        "http://localhost:8000/agent-service",
        GATEWAY
      )
    ).not.toThrow();
  });

  it("accepts a nested path under a known prefix", () => {
    expect(() =>
      assertGatewayRouted(
        "MCP_INTERNAL_URL",
        "http://localhost:8000/internal/tools-service/mcp",
        GATEWAY
      )
    ).not.toThrow();
  });

  it("names the variable when the value is not an absolute URL", () => {
    expect(() =>
      assertGatewayRouted("AGENT_SERVICE_URL", "/agent-service", GATEWAY)
    ).toThrow(/AGENT_SERVICE_URL must be an absolute URL/);
  });

  it("rejects a URL pointing straight at a service host", () => {
    expect(() =>
      assertGatewayRouted(
        "USER_SERVICE_URL",
        "http://user-service:8001/user-service",
        GATEWAY
      )
    ).toThrow(/does not point at Gateway/);
  });

  it("rejects a Gateway URL with no route prefix", () => {
    expect(() =>
      assertGatewayRouted(
        "AGENT_SERVICE_URL",
        "http://localhost:8000/",
        GATEWAY
      )
    ).toThrow(/is missing a Gateway route prefix/);
  });

  it("rejects a prefix that only shares a leading substring", () => {
    expect(() =>
      assertGatewayRouted(
        "AGENT_SERVICE_URL",
        "http://localhost:8000/agent-service-admin",
        GATEWAY
      )
    ).toThrow(/is missing a Gateway route prefix/);
  });

  it("covers every service the web app calls", () => {
    expect(GATEWAY_ROUTE_PREFIXES).toEqual(
      expect.arrayContaining([
        "/agent-service",
        "/user-service",
        "/rag-service",
        "/tools-service",
        "/internal/agent-service",
        "/internal/user-service",
        "/internal/rag-service",
        "/internal/tools-service",
      ])
    );
  });
});
