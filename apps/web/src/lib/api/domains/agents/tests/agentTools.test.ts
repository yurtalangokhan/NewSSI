import {
  humanizeToolName,
  isMcpAgent,
  knowledgeSourceKind,
  MCP_AGENT_BASE,
  resolveAgentTools,
} from "@/lib/api/domains/agents/agentTools";
import { KNOWLEDGE_TOOL_NAMES } from "@/lib/tools/knowledgeToolNames";
import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";

function agent(partial: Record<string, unknown>): MinimalPersonaSnapshot {
  return {
    id: 1,
    name: "A",
    tools: [],
    ...partial,
  } as unknown as MinimalPersonaSnapshot;
}

describe("isMcpAgent", () => {
  it("is false without an agent", () => {
    expect(isMcpAgent(undefined)).toBe(false);
    expect(isMcpAgent(null)).toBe(false);
  });

  it("matches on base_agent", () => {
    expect(isMcpAgent(agent({ base_agent: MCP_AGENT_BASE }))).toBe(true);
  });

  it("matches on brain_type", () => {
    expect(isMcpAgent(agent({ brain_type: MCP_AGENT_BASE }))).toBe(true);
  });

  it("matches on a non-empty mcp_tools list", () => {
    expect(isMcpAgent(agent({ mcp_tools: ["fetch_page"] }))).toBe(true);
  });

  it("is false for a plain chatbot with an empty mcp_tools list", () => {
    expect(isMcpAgent(agent({ base_agent: "chatbot", mcp_tools: [] }))).toBe(
      false
    );
  });
});

describe("knowledgeSourceKind", () => {
  it("maps retrieval tools to their RAG flavour", () => {
    expect(knowledgeSourceKind("database_search")).toBe("RAG");
    expect(knowledgeSourceKind("document_search")).toBe("RAG");
    expect(knowledgeSourceKind("graph_search")).toBe("GraphRAG");
  });

  it("returns undefined for other tools", () => {
    expect(knowledgeSourceKind("web_search")).toBeUndefined();
    expect(knowledgeSourceKind("toString")).toBeUndefined();
  });

  it("only maps names the shared knowledge tool list knows", () => {
    for (const name of ["database_search", "document_search", "graph_search"]) {
      expect(KNOWLEDGE_TOOL_NAMES.has(name)).toBe(true);
    }
  });
});

describe("humanizeToolName", () => {
  it("title-cases snake_case names", () => {
    expect(humanizeToolName("fetch_web_page")).toBe("Fetch Web Page");
  });
});

describe("resolveAgentTools", () => {
  it("returns nothing without an agent", () => {
    expect(resolveAgentTools(undefined)).toEqual([]);
  });

  it("prefers the agent's tool snapshots, keyed by id", () => {
    const entries = resolveAgentTools(
      agent({
        tools: [
          {
            id: 4,
            name: "database_search",
            display_name: "Physics",
            description: "d",
          },
          {
            id: 9,
            name: "database_search",
            display_name: "Chem",
            description: "",
          },
        ],
        mcp_tools: ["ignored"],
      })
    );
    expect(entries.map((e) => e.key)).toEqual(["4", "9"]);
    expect(entries[0]).toMatchObject({
      name: "database_search",
      displayName: "Physics",
      description: "d",
    });
  });

  it("falls back to mcp_tools with humanized titles and name-based keys", () => {
    const entries = resolveAgentTools(
      agent({ mcp_tools: ["fetch_page", "web_search"] })
    );
    expect(entries).toEqual([
      {
        key: "mcp:fetch_page",
        name: "fetch_page",
        displayName: "Fetch Page",
        description: "",
      },
      {
        key: "mcp:web_search",
        name: "web_search",
        displayName: "Web Search",
        description: "",
      },
    ]);
  });

  it("is empty when the agent has neither tools nor mcp_tools", () => {
    expect(resolveAgentTools(agent({ mcp_tools: [] }))).toEqual([]);
  });
});
