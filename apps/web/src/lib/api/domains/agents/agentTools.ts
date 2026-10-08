import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";

/** `base_agent` / `brain_type` value of agents driven by MCP and knowledge tools. */
export const MCP_AGENT_BASE = "configurable-mcp-agent";

export type KnowledgeSourceKind = "RAG" | "GraphRAG";

// The backend emits one tool snapshot per assigned collection, named after
// the retrieval tool that searches it and labeled with the collection's name.
const KNOWLEDGE_SOURCE_KINDS: ReadonlyMap<string, KnowledgeSourceKind> =
  new Map([
    ["database_search", "RAG"],
    ["document_search", "RAG"],
    ["graph_search", "GraphRAG"],
  ]);

/** The RAG flavour of a collection-backed retrieval tool, if it is one. */
export function knowledgeSourceKind(
  toolName: string
): KnowledgeSourceKind | undefined {
  return KNOWLEDGE_SOURCE_KINDS.get(toolName);
}

export function isMcpAgent(
  agent:
    | Pick<MinimalPersonaSnapshot, "base_agent" | "brain_type" | "mcp_tools">
    | null
    | undefined
): boolean {
  if (!agent) return false;
  return (
    agent.base_agent === MCP_AGENT_BASE ||
    agent.brain_type === MCP_AGENT_BASE ||
    (Array.isArray(agent.mcp_tools) && agent.mcp_tools.length > 0)
  );
}

/** "fetch_web_page" -> "Fetch Web Page". */
export function humanizeToolName(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface AgentToolEntry {
  /** Stable list key; snapshot ids are unique, MCP names are namespaced. */
  key: string;
  name: string;
  displayName: string;
  description: string;
}

/**
 * The tools an agent exposes for display: its tool snapshots, or, when it has
 * none, its bare `mcp_tools` names.
 */
export function resolveAgentTools(
  agent: Pick<MinimalPersonaSnapshot, "tools" | "mcp_tools"> | null | undefined
): AgentToolEntry[] {
  if (!agent) return [];
  if (agent.tools && agent.tools.length > 0) {
    return agent.tools.map((tool) => ({
      key: String(tool.id),
      name: tool.name,
      displayName: tool.display_name || tool.name,
      description: tool.description,
    }));
  }
  if (Array.isArray(agent.mcp_tools) && agent.mcp_tools.length > 0) {
    return agent.mcp_tools.map((name) => ({
      key: `mcp:${name}`,
      name,
      displayName: humanizeToolName(name),
      description: "",
    }));
  }
  return [];
}
