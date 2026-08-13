import { AGENT_CATALOG_API_PATH, buildAgentDetailApiPath } from "./apiPaths";

describe("agent API paths", () => {
  it("uses the lightweight product agent catalog endpoint for lists", () => {
    expect(AGENT_CATALOG_API_PATH).toBe("/api/agents/catalog");
  });

  it("builds product agent detail paths", () => {
    expect(buildAgentDetailApiPath(42)).toBe("/api/agents/42");
    expect(buildAgentDetailApiPath("dynamic-agent-id")).toBe(
      "/api/agents/dynamic-agent-id"
    );
  });
});
