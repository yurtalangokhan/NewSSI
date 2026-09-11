import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import {
  filterChatReadyAgents,
  isFlowAgent,
  isFlowChatReady,
} from "@/lib/flows/flowAgent";

function agent(
  overrides: Partial<MinimalPersonaSnapshot>
): MinimalPersonaSnapshot {
  return {
    id: 1,
    name: "A",
    description: "",
    tools: [],
    ...overrides,
  } as MinimalPersonaSnapshot;
}

describe("flowAgent helpers", () => {
  it("identifies flow-backed agents by graph_schema", () => {
    expect(isFlowAgent(agent({ graph_schema: "flow" }))).toBe(true);
    expect(isFlowAgent(agent({ graph_schema: "zero_shot" }))).toBe(false);
    expect(isFlowAgent(agent({}))).toBe(false);
  });

  it("treats a non-flow agent as always chat ready", () => {
    expect(isFlowChatReady(agent({ graph_schema: "zero_shot" }))).toBe(true);
  });

  it("treats an unpublished flow as not chat ready", () => {
    expect(
      isFlowChatReady(
        agent({ graph_schema: "flow", flow_published_version_no: null })
      )
    ).toBe(false);
  });

  it("treats a published flow as chat ready", () => {
    expect(
      isFlowChatReady(
        agent({ graph_schema: "flow", flow_published_version_no: 2 })
      )
    ).toBe(true);
  });

  it("drops unpublished flows from a chat-surface list", () => {
    const list = [
      agent({ id: 1, graph_schema: "zero_shot" }),
      agent({ id: 2, graph_schema: "flow", flow_published_version_no: null }),
      agent({ id: 3, graph_schema: "flow", flow_published_version_no: 1 }),
    ];

    expect(filterChatReadyAgents(list).map((a) => a.id)).toEqual([1, 3]);
  });
});
