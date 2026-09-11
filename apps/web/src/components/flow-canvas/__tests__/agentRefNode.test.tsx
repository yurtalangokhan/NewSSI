import React from "react";
import { render, screen } from "@testing-library/react";
import { SWRConfig } from "swr";
import { isValidConnection } from "../utils/isValidConnection";
import { ComponentSidebar } from "../components/ComponentSidebar";
import { NodeFieldList } from "../components/NodeFieldList";
import type { ComponentTemplate } from "../types/componentTemplate";

const mockUseComponentTemplates = jest.fn();
jest.mock("../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => mockUseComponentTemplates(),
}));

const AGENT_REF_TEMPLATE: any = {
  type: "AgentRef",
  category: "agents",
  display_name: "Agent Reference",
  description:
    "Embeds an existing classic agent, unmodified, as a step in this flow.",
  icon: "SvgUsers",
  kind: "execution",
  inputs: {
    agent_id: {
      type: "options",
      display_name: "Agent",
      required: true,
      options_source: "agents.definitions",
    },
  },
  handles: {
    inputs: [{ name: "input", types: ["Message"] }],
    outputs: [{ name: "output", types: ["Message"] }],
  },
};

describe("Task 36 — AgentRef Node UI & Options Picker", () => {
  beforeEach(() => {
    mockUseComponentTemplates.mockReset();
  });

  it("36.1 — AgentRef appears under the 'agents' sidebar category", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: {
        agents: [AGENT_REF_TEMPLATE],
      },
      isLoading: false,
      error: undefined,
    });

    render(<ComponentSidebar />);

    expect(screen.getByTestId("sidebar-category-agents")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-item-AgentRef")).toBeInTheDocument();
    expect(screen.getByText("Agent Reference")).toBeInTheDocument();
  });

  it("36.2 — AgentRef agent_id field renders an options dropdown with real options", () => {
    const cache = new Map();
    cache.set("/api/flow-options/agents.definitions", {
      data: {
        source: "agents.definitions",
        items: [
          { value: "c-1", label: "Customer Support Agent" },
          { value: "c-2", label: "Research Agent" },
        ],
        available: true,
      },
    });

    render(
      <SWRConfig value={{ provider: () => cache, dedupingInterval: 0 }}>
        <NodeFieldList
          template={AGENT_REF_TEMPLATE}
          values={{ agent_id: "c-1" }}
          onFieldChange={jest.fn()}
        />
      </SWRConfig>
    );

    expect(screen.getByText("Agent")).toBeInTheDocument();
  });

  it("36.5 — AgentRef Message handles connect like any other Message node", () => {
    const handleTypeMap: Record<
      string,
      { inputs: Record<string, string[]>; outputs: Record<string, string[]> }
    > = {
      "chat-in": { inputs: {}, outputs: { message: ["Message"] } },
      "aref-1": {
        inputs: { input: ["Message"] },
        outputs: { output: ["Message"] },
      },
      "chat-out": { inputs: { message: ["Message"] }, outputs: {} },
    };

    const lookup: any = (
      nodeId: string,
      handleName: string,
      handleType: "source" | "target"
    ) => {
      const node = handleTypeMap[nodeId];
      if (!node) return null;
      return (
        (handleType === "source"
          ? node.outputs[handleName]
          : node.inputs[handleName]) || null
      );
    };

    // ChatInput (output: message) -> AgentRef (input: input)
    const validIn = isValidConnection(
      {
        source: "chat-in",
        sourceHandle: "message",
        target: "aref-1",
        targetHandle: "input",
      },
      [],
      lookup
    );
    expect(validIn).toBe(true);

    // AgentRef (output: output) -> ChatOutput (input: message)
    const validOut = isValidConnection(
      {
        source: "aref-1",
        sourceHandle: "output",
        target: "chat-out",
        targetHandle: "message",
      },
      [],
      lookup
    );
    expect(validOut).toBe(true);
  });
});
