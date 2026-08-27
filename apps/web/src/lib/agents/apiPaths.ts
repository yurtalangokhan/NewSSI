import { AgentId } from "@/app/admin/agents/interfaces";

export const AGENT_CATALOG_API_PATH = "/api/agents/catalog";
export const COMPOSITION_CATALOG_API_PATH = "/api/agents/composition/catalog";

export function buildAgentDetailApiPath(agentId: AgentId) {
  return `/api/agents/${encodeURIComponent(String(agentId))}`;
}
