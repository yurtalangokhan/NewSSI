import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";

/** A persona backed by the visual canvas rather than the classic form. */
export function isFlowAgent(agent: MinimalPersonaSnapshot): boolean {
  return agent.graph_schema === "flow";
}

/**
 * Whether this agent may be chatted with.
 *
 * A flow with no published version has no graph to run — the backend
 * refuses it with 409 FLOW_NOT_PUBLISHED — so chat surfaces must not
 * offer it. Non-flow agents are never gated here.
 */
export function isFlowChatReady(agent: MinimalPersonaSnapshot): boolean {
  if (!isFlowAgent(agent)) return true;
  return (
    agent.flow_published_version_no !== null &&
    agent.flow_published_version_no !== undefined
  );
}

/** Chat-surface list filter: agent picker, sidebar/pinned, @mention. */
export function filterChatReadyAgents(
  agents: MinimalPersonaSnapshot[]
): MinimalPersonaSnapshot[] {
  return agents.filter(isFlowChatReady);
}
