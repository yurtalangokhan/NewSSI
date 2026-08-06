interface AgentPageAccess {
  canCreateAgent: boolean;
  canViewPersonalTab: boolean;
}

export function getAgentPageAccess(isAdmin: boolean): AgentPageAccess {
  return {
    canCreateAgent: isAdmin,
    canViewPersonalTab: isAdmin,
  };
}
