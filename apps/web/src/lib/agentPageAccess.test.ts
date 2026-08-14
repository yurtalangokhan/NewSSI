import { getAgentPageAccess } from "@/lib/agentPageAccess";

describe("getAgentPageAccess", () => {
  it("hides creation controls and personal tab from end users", () => {
    expect(
      getAgentPageAccess({ canCreateAgent: false, canListAgents: false })
    ).toEqual({
      canCreateAgent: false,
      canViewPersonalTab: false,
    });
  });

  it("uses explicit permissions for creation controls and personal tab", () => {
    expect(
      getAgentPageAccess({ canCreateAgent: true, canListAgents: true })
    ).toEqual({
      canCreateAgent: true,
      canViewPersonalTab: true,
    });
  });

  it("does not infer create access from list access", () => {
    expect(
      getAgentPageAccess({ canCreateAgent: false, canListAgents: true })
    ).toEqual({
      canCreateAgent: false,
      canViewPersonalTab: true,
    });
  });
});
