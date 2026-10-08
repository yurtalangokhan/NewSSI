interface AgentPageAccess {
  canCreateAgent: boolean;
  canViewPersonalTab: boolean;
}

export function getAgentPageAccess({
  canCreateAgent,
  canListAgents,
}: {
  canCreateAgent: boolean;
  canListAgents: boolean;
}): AgentPageAccess {
  return {
    canCreateAgent,
    canViewPersonalTab: canListAgents,
  };
}
