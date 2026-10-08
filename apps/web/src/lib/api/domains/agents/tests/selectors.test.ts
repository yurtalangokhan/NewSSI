import { checkUserIdOwnsAgent } from "@/lib/api/domains/agents/selectors";
import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";

function agentOwnedBy(ownerId: string): MinimalPersonaSnapshot {
  return {
    id: 10,
    owner: { id: ownerId, email: "owner@example.com" },
    builtin_persona: false,
  } as MinimalPersonaSnapshot;
}

describe("checkUserIdOwnsAgent", () => {
  it("requires an exact owner match for the local no-auth user", () => {
    expect(
      checkUserIdOwnsAgent("__no_auth_user__", agentOwnedBy("creator-1"))
    ).toBe(false);
  });

  it("returns true when the current user owns the custom agent", () => {
    expect(checkUserIdOwnsAgent("creator-1", agentOwnedBy("creator-1"))).toBe(
      true
    );
  });
});
