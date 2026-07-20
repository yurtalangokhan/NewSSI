import {
  AgentAvailability,
  AgentAvailabilityCheck,
  MinimalPersonaSnapshot,
} from "@/app/admin/agents/interfaces";

export function getAgentAvailabilityIssues(
  availability: AgentAvailability | undefined
): AgentAvailabilityCheck[] {
  return availability?.checks.filter((check) => check.status !== "ok") ?? [];
}

export function isAgentAvailableForSelection(
  agent: Pick<MinimalPersonaSnapshot, "availability">
): boolean {
  return agent.availability?.status !== "unavailable";
}
