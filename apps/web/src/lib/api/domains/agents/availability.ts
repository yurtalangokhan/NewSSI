import {
  AgentAvailability,
  AgentAvailabilityCheck,
  MinimalPersonaSnapshot,
} from "@/lib/api/domains/agents/types";

export function getAgentAvailabilityIssues(
  availability: AgentAvailability | undefined
): AgentAvailabilityCheck[] {
  return availability?.checks?.filter((check) => check.status !== "ok") ?? [];
}

export function isAgentAvailableForSelection(
  agent: Pick<MinimalPersonaSnapshot, "availability">
): boolean {
  return agent.availability?.status !== "unavailable";
}
