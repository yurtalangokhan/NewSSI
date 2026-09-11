/**
 * Tests for TemplateNode — the ported `GenericNode`. Mounted through the
 * real `FlowCanvas` (Task 24) rather than hand-built `NodeProps`, since
 * that's how it will actually be used (`nodeTypes={{ templateNode:
 * createTemplateNode(store) }}`, `type: "templateNode"` on the node) and
 * avoids fabricating xyflow's internal NodeProps shape by hand.
 *
 * `useComponentTemplates` is mocked directly (Task 25's pattern) — the
 * real proxy route doesn't exist yet (Task 28).
 *
 * Brief: .tmp/flow-canvas-task-26-brief.md
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { FlowCanvas } from "../FlowCanvas";
import { createTemplateNode } from "../nodes/TemplateNode";
import type { CanvasNode, PortType } from "../types/flow";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const mockUpdateNodeInternals = jest.fn();
jest.mock("@xyflow/react", () => {
  const actual = jest.requireActual("@xyflow/react");
  return { ...actual, useUpdateNodeInternals: () => mockUpdateNodeInternals };
});

const mockUseComponentTemplates = jest.fn();
jest.mock("../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => mockUseComponentTemplates(),
}));

function lookupAlwaysMessage(): PortType[] | null {
  return ["Message"];
}

const AGENT_TEMPLATE: GroupedComponentTemplates = {
  agents: [
    {
      type: "ZeroShotAgent",
      category: "agents",
      display_name: "Zero-Shot Agent",
      description: "",
      icon: null,
      template_version: 1,
      lifecycle: "stable",
      kind: "execution",
      inputs: {
        system_prompt: {
          type: "prompt",
          display_name: "System prompt",
          required: true,
          value: "You are helpful.",
          options: null,
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
        max_iterations: {
          type: "int",
          display_name: "Max iterations",
          required: false,
          value: 5,
          options: null,
          options_source: null,
          info: "Advanced tuning.",
          advanced: true,
          min: 1,
          max: 20,
        },
      },
      handles: {
        inputs: [{ name: "message", types: ["Message"] }],
        outputs: [{ name: "message", types: ["Message"] }],
      },
    },
  ],
};

const ROUTER_TEMPLATE: GroupedComponentTemplates = {
  logic: [
    {
      type: "Router",
      category: "logic",
      display_name: "Router",
      description: "",
      icon: null,
      template_version: 1,
      lifecycle: "stable",
      kind: "execution",
      inputs: {
        routes: {
          type: "table",
          display_name: "Routes",
          required: true,
          value: null,
          options: null,
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
      },
      handles: {
        inputs: [{ name: "message", types: ["Message"] }],
        outputs: [
          {
            name: "routes",
            types: ["Trigger"],
            expands_from: "routes",
            expands_label_key: "route",
          },
        ],
      },
    },
  ],
};

function node(
  id: string,
  type: string,
  values: Record<string, unknown>
): CanvasNode {
  return {
    id,
    type: "templateNode",
    position: { x: 0, y: 0 },
    data: { type, templateVersion: 1, values },
  };
}

function renderWithNode(canvasNode: CanvasNode) {
  const store = createFlowStore();
  store.getState().setNodes([canvasNode]);
  store.getState().resetDirty();
  const nodeTypes = { templateNode: createTemplateNode(store) };
  render(
    <div style={{ width: 800, height: 600 }}>
      <FlowCanvas
        store={store}
        lookupHandleTypes={lookupAlwaysMessage}
        nodeTypes={nodeTypes}
      />
    </div>
  );
  return store;
}

beforeEach(() => {
  mockUseComponentTemplates.mockReset();
});

describe("TemplateNode — 26.2, reads from node.values, not the template default", () => {
  it("shows the node's own value even when it differs from the template default", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", { system_prompt: "Be terse." }));

    expect(screen.getByDisplayValue("Be terse.")).toBeInTheDocument();
    expect(
      screen.queryByDisplayValue("You are helpful.")
    ).not.toBeInTheDocument();
  });

  it("falls back to the template default only when the node has no value for that key", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", {}));

    expect(screen.getByDisplayValue("You are helpful.")).toBeInTheDocument();
  });
});

describe("TemplateNode — 26.3, editing writes only that key", () => {
  it("does not bake other fields' defaults into node.values on edit", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    const store = renderWithNode(
      node("n1", "ZeroShotAgent", { system_prompt: "Be terse." })
    );

    fireEvent.change(screen.getByDisplayValue("Be terse."), {
      target: { value: "Be terser." },
    });

    const values = store.getState().nodes[0]!.data.values;
    expect(values).toEqual({ system_prompt: "Be terser." });
  });
});

describe("TemplateNode — 26.4, advanced fields collapsed by default", () => {
  it("hides the advanced field until the disclosure is opened", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", {}));

    expect(screen.queryByDisplayValue("5")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/advanced/i));

    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
  });
});

describe("TemplateNode — 26.8, unknown component type", () => {
  it("renders a placeholder instead of crashing, and preserves the node's values", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    const store = renderWithNode(
      node("n1", "SomeRemovedComponent", { kept: "value" })
    );

    expect(screen.getByText(/unknown component/i)).toBeInTheDocument();
    expect(store.getState().nodes[0]!.data.values).toEqual({ kept: "value" });
  });
});

describe("TemplateNode — 26.9, Router handle expansion", () => {
  it("expands the declared 'routes' handle into one per configured route", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: ROUTER_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(
      node("n1", "Router", {
        routes: [
          { condition: "a", route: "high" },
          { condition: "b", route: "low" },
        ],
      })
    );

    expect(screen.getByTestId("handle-source-high")).toBeInTheDocument();
    expect(screen.getByTestId("handle-source-low")).toBeInTheDocument();
    expect(
      screen.queryByTestId("handle-source-routes")
    ).not.toBeInTheDocument();
  });
});

describe("TemplateNode — 26.10, handles render one per declared port", () => {
  it("renders one handle per input and output with a tooltip", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", {}));

    expect(screen.getByTestId("handle-target-message")).toBeInTheDocument();
    expect(screen.getByTestId("handle-source-message")).toBeInTheDocument();
  });
});

describe("TemplateNode — loading state", () => {
  it("does not render the unknown-component placeholder while templates are still loading", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", {}));

    expect(screen.queryByText(/unknown component/i)).not.toBeInTheDocument();
  });
});

describe("TemplateNode — handle re-measurement (xyflow updateNodeInternals)", () => {
  beforeEach(() => mockUpdateNodeInternals.mockClear());

  it("nudges xyflow to re-measure the node's handles once its template resolves", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", {}));

    // Without this, the output/source handle keeps the stale (skeleton-era)
    // anchor bounds and the port renders detached until the node is dragged.
    expect(mockUpdateNodeInternals).toHaveBeenCalledWith("n1");
  });

  it("does not call updateNodeInternals while the template is still loading (no handles to measure yet)", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", {}));

    expect(mockUpdateNodeInternals).not.toHaveBeenCalledWith("n1");
  });
});

jest.mock("../utils/expandAgentIntoFlow", () => ({
  expandAgentIntoFlow: jest.fn().mockResolvedValue(undefined),
}));

import { expandAgentIntoFlow } from "../utils/expandAgentIntoFlow";

const AGENT_REF_TEMPLATE: GroupedComponentTemplates = {
  agents: [
    {
      type: "AgentRef",
      category: "agents",
      display_name: "Agent Reference",
      description:
        "Embeds an existing classic agent, unmodified, as a step in this flow.",
      icon: null,
      template_version: 1,
      lifecycle: "stable",
      kind: "execution",
      inputs: {
        agent_id: {
          type: "options",
          display_name: "Agent",
          required: true,
          value: null,
          options: null,
          options_source: "agents.definitions",
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
      },
      handles: {
        inputs: [{ name: "input", types: ["Message"] }],
        outputs: [{ name: "output", types: ["Message"] }],
      },
    },
  ],
};

describe("TemplateNode — AgentRef expand action", () => {
  beforeEach(() => {
    (expandAgentIntoFlow as jest.Mock).mockClear();
  });

  // getByLabelText, not getByRole: this harness's shared ResizeObserver
  // mock (tests/setup/jest.setup.ts) never fires, so @xyflow/react leaves
  // every node `visibility: hidden` until it measures dimensions — getByRole
  // excludes CSS-hidden elements by default, getByLabelText does not.
  it("shows an 'Expand into flow' button once an agent is selected on an AgentRef node", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_REF_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "AgentRef", { agent_id: "agent-1" }));

    expect(screen.getByLabelText(/expand into flow/i)).toBeInTheDocument();
  });

  it("does not show the button for an AgentRef node with no agent selected yet", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_REF_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "AgentRef", {}));

    expect(
      screen.queryByLabelText(/expand into flow/i)
    ).not.toBeInTheDocument();
  });

  it("does not show the button on non-AgentRef nodes", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "ZeroShotAgent", { system_prompt: "hi" }));

    expect(
      screen.queryByLabelText(/expand into flow/i)
    ).not.toBeInTheDocument();
  });

  it("calls expandAgentIntoFlow with the node's own agent_id and an offset canvas position on click", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: AGENT_REF_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    const store = renderWithNode(
      node("n1", "AgentRef", { agent_id: "agent-1" })
    );

    fireEvent.click(screen.getByLabelText(/expand into flow/i));

    expect(expandAgentIntoFlow).toHaveBeenCalledWith(
      "agent-1",
      store,
      { x: 280, y: 0 } // renderWithNode's node() helper places every node at {x:0,y:0}
    );
  });
});

describe("TemplateNode — Field and Handle i18n localization", () => {
  it("translates field names like condition and max_iterations using i18n", () => {
    const LOOP_TEMPLATE: GroupedComponentTemplates = {
      core: [
        {
          type: "Loop",
          category: "core",
          display_name: "Loop",
          description: "",
          icon: null,
          template_version: 1,
          lifecycle: "stable",
          kind: "execution",
          inputs: {
            condition: {
              type: "str",
              display_name: "Continue while",
              required: true,
              value: "x > 0",
              options: null,
              options_source: null,
              info: "The loop repeats while this holds.",
              advanced: false,
              min: null,
              max: null,
            },
            max_iterations: {
              type: "int",
              display_name: "Max iterations",
              required: true,
              value: 5,
              options: null,
              options_source: null,
              info: "Hard bound.",
              advanced: false,
              min: null,
              max: null,
            },
          },
          handles: { inputs: [], outputs: [] },
        },
      ],
    };

    mockUseComponentTemplates.mockReturnValue({
      data: LOOP_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(
      node("n1", "Loop", { condition: "x > 0", max_iterations: 5 })
    );

    expect(
      screen.getByText(/continue while|devam koşulu/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/max iterations|maksimum yineleme/i)
    ).toBeInTheDocument();
  });
});

const CONDITIONAL_ROUTER_TEMPLATE: GroupedComponentTemplates = {
  logic: [
    {
      type: "ConditionalRouter",
      category: "logic",
      display_name: "If-Else",
      description: "",
      icon: null,
      template_version: 1,
      lifecycle: "stable",
      kind: "execution",
      inputs: {
        operator: {
          type: "options",
          display_name: "Operator",
          required: true,
          value: "contains",
          options: ["equals", "contains", "regex"],
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
        match_text: {
          type: "str",
          display_name: "Match text",
          required: true,
          value: "",
          options: null,
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
      },
      handles: {
        inputs: [{ name: "input", types: ["Message"] }],
        outputs: [
          { name: "true_result", types: ["Message"] },
          { name: "false_result", types: ["Message"] },
        ],
      },
    },
  ],
};

describe("TemplateNode — ConditionalRouter (If-Else)", () => {
  it("renders the static true_result / false_result source handles and the input target handle", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: CONDITIONAL_ROUTER_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(
      node("n1", "ConditionalRouter", {
        operator: "contains",
        match_text: "DONE",
      })
    );

    expect(screen.getByTestId("handle-source-true_result")).toBeInTheDocument();
    expect(
      screen.getByTestId("handle-source-false_result")
    ).toBeInTheDocument();
    expect(screen.getByTestId("handle-target-input")).toBeInTheDocument();
  });

  it("localizes the operator field label", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: CONDITIONAL_ROUTER_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(
      node("n1", "ConditionalRouter", {
        operator: "contains",
        match_text: "DONE",
      })
    );

    expect(screen.getByText(/operator|işleç/i)).toBeInTheDocument();
    expect(screen.getByText(/match text|eşleşme metni/i)).toBeInTheDocument();
  });
});

/**
 * Phase 4.5 — input ports.
 *
 * Two things the canvas must now do: hide an input handle whose `show_when`
 * is off (the mirror of the output resolver), and render a port's
 * `fallback_field` inline on its row. The second is what makes "wired port
 * wins, otherwise the field" visible: the row shows the editable field until
 * an edge lands on it.
 */
const PORTED_TEMPLATE: GroupedComponentTemplates = {
  logic: [
    {
      type: "Loop",
      category: "logic",
      display_name: "Loop",
      description: "",
      icon: null,
      template_version: 2,
      lifecycle: "stable",
      kind: "execution",
      inputs: {
        items_source: {
          type: "str",
          display_name: "Items",
          required: false,
          value: "",
          options: null,
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
        show_extra: {
          type: "bool",
          display_name: "Show extra",
          required: false,
          value: false,
          options: null,
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
      },
      handles: {
        inputs: [
          { name: "input", types: ["Message"] },
          { name: "items", types: ["Data"], fallback_field: "items_source" },
          {
            name: "extra",
            types: ["Message"],
            show_when: { field: "show_extra", equals: true },
          },
        ],
        outputs: [{ name: "done", types: ["Message"] }],
      },
    },
  ],
};

describe("TemplateNode — Phase 4.5 input ports", () => {
  it("hides an input handle whose show_when is off, and shows it when on", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: PORTED_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "Loop", { show_extra: false }));
    expect(screen.queryByTestId("port-state-extra")).not.toBeInTheDocument();
  });

  it("shows a conditional input handle once its field turns it on", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: PORTED_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "Loop", { show_extra: true }));
    expect(screen.getByTestId("port-state-extra")).toBeInTheDocument();
  });

  it("renders a port's fallback_field inline on its row", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: PORTED_TEMPLATE,
      isLoading: false,
      error: undefined,
    });
    renderWithNode(node("n1", "Loop", { items_source: "belgeler" }));
    // The field is editable on the port row, not stranded in the list below.
    expect(screen.getByDisplayValue("belgeler")).toBeInTheDocument();
    expect(screen.queryByTestId("port-state-items")).not.toBeInTheDocument();
  });
});
