import { resolveActivePersonaId } from "@/hooks/useChatController";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";

function makeAgent(
  overrides: Partial<MinimalPersonaSnapshot> = {}
): MinimalPersonaSnapshot {
  return {
    id: 5,
    external_id: null,
    name: "Custom Agent",
    tools: [],
    ...overrides,
  } as MinimalPersonaSnapshot;
}

describe("resolveActivePersonaId", () => {
  it("uses the live agent when no forced persona id is given (normal send)", () => {
    expect(resolveActivePersonaId(makeAgent({ id: 5 }), undefined)).toBe(5);
  });

  it("prefers the live agent's external_id over its numeric id when both are set", () => {
    expect(
      resolveActivePersonaId(makeAgent({ id: 5, external_id: "ext-5" }), undefined)
    ).toBe("ext-5");
  });

  it("returns the forced persona id when a retry supplies one, ignoring the live agent", () => {
    // Retrying a message must resend to the agent that produced it, even if
    // the user has since switched to a different agent in the UI.
    expect(resolveActivePersonaId(makeAgent({ id: 99 }), 7)).toBe(7);
  });

  it("honors a forced persona id of 0 (default/model-chat persona)", () => {
    // 0 is falsy but a legitimate persona id (the default persona) — must
    // not be treated the same as "no override".
    expect(resolveActivePersonaId(makeAgent({ id: 99 }), 0)).toBe(0);
  });

  it("falls back to the live agent when forcedPersonaId is null", () => {
    expect(resolveActivePersonaId(makeAgent({ id: 5 }), null)).toBe(5);
  });

  it("returns undefined when there is no live agent and no forced persona id", () => {
    expect(resolveActivePersonaId(undefined, undefined)).toBeUndefined();
  });
});
