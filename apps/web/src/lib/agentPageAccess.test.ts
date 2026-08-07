import { getAgentPageAccess } from "@/lib/agentPageAccess";

describe("getAgentPageAccess", () => {
  it("hides creation controls and personal tab from end users", () => {
    expect(getAgentPageAccess(false)).toEqual({
      canCreateAgent: false,
      canViewPersonalTab: false,
    });
  });

  it("shows creation controls and personal tab to admins", () => {
    expect(getAgentPageAccess(true)).toEqual({
      canCreateAgent: true,
      canViewPersonalTab: true,
    });
  });
});
