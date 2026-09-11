/**
 * Tests for NodeInspector — the side panel for the selected node. Needs no
 * `ReactFlowProvider`: it reads only the zustand store, never
 * `@xyflow/react` directly (unlike TemplateNode, which renders real
 * xyflow handles/toolbar). `useComponentTemplates` is mocked (Task 25's
 * established pattern) since the real proxy route doesn't exist yet
 * (Task 28).
 *
 * Brief: .tmp/flow-canvas-task-27-brief.md
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { createNodeInspector } from "../components/NodeInspector";
import type { CanvasNode } from "../types/flow";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const mockUseComponentTemplates = jest.fn();
jest.mock("../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => mockUseComponentTemplates(),
}));

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
      },
      handles: { inputs: [], outputs: [] },
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

function seededStore() {
  const store = createFlowStore();
  store
    .getState()
    .setNodes([node("n1", "ZeroShotAgent", { system_prompt: "Be terse." })]);
  store.getState().resetDirty();
  // The inspector is a sticky preference toggled from the node toolbar,
  // not something selection opens (upstream's
  // `flowStore.inspectionPanelVisible`). Every test below is about what it
  // shows *once open*, so open it here rather than in each case.
  store.getState().setInspectorOpen(true);
  return store;
}

beforeEach(() => {
  mockUseComponentTemplates.mockReset();
  mockUseComponentTemplates.mockReturnValue({
    data: AGENT_TEMPLATE,
    isLoading: false,
    error: undefined,
  });
});

describe("NodeInspector — 27.2, closes when selection is cleared", () => {
  it("renders nothing when nothing is selected", () => {
    const store = seededStore();
    const NodeInspector = createNodeInspector(store);
    const { container } = render(<NodeInspector />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("NodeInspector — opens on request, not on selection", () => {
  it("stays closed when a node is selected but the panel was never opened", () => {
    const store = createFlowStore();
    store
      .getState()
      .setNodes([node("n1", "ZeroShotAgent", { system_prompt: "Be terse." })]);
    store
      .getState()
      .setLastSelection({ nodes: [{ id: "n1" } as never], edges: [] });

    const NodeInspector = createNodeInspector(store);
    const { container } = render(<NodeInspector />);

    // Selecting a card used to fly this panel in from the right on every
    // click; upstream keeps it a toggle. Fields stay editable on the card
    // itself, so nothing becomes unreachable.
    expect(container).toBeEmptyDOMElement();
  });

  it("appears once the toolbar toggle opens it", () => {
    const store = createFlowStore();
    store
      .getState()
      .setNodes([node("n1", "ZeroShotAgent", { system_prompt: "Be terse." })]);
    store
      .getState()
      .setLastSelection({ nodes: [{ id: "n1" } as never], edges: [] });
    store.getState().setInspectorOpen(true);

    const NodeInspector = createNodeInspector(store);
    render(<NodeInspector />);

    expect(screen.getByTestId("node-inspector")).toBeInTheDocument();
  });
});

describe("NodeInspector — 27.1, shows the selected node's fields", () => {
  it("renders the selected node's field values", () => {
    const store = seededStore();
    store
      .getState()
      .setLastSelection({ nodes: [{ id: "n1" } as never], edges: [] });
    const NodeInspector = createNodeInspector(store);
    render(<NodeInspector />);

    expect(screen.getByTestId("node-inspector")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Be terse.")).toBeInTheDocument();
  });
});

describe("NodeInspector — 27.3, multi-selection shows a summary", () => {
  it("shows a count, not the first node's fields, when multiple nodes are selected", () => {
    const store = seededStore();
    store
      .getState()
      .setNodes((current) => [
        ...current,
        node("n2", "ZeroShotAgent", { system_prompt: "Something else." }),
      ]);
    store.getState().setLastSelection({
      nodes: [{ id: "n1" } as never, { id: "n2" } as never],
      edges: [],
    });
    const NodeInspector = createNodeInspector(store);
    render(<NodeInspector />);

    expect(screen.getByText(/2 items selected/i)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Be terse.")).not.toBeInTheDocument();
  });
});

describe("NodeInspector — 27.5, edits write into store.nodes", () => {
  it("updates the node's values in the store", () => {
    const store = seededStore();
    store
      .getState()
      .setLastSelection({ nodes: [{ id: "n1" } as never], edges: [] });
    const NodeInspector = createNodeInspector(store);
    render(<NodeInspector />);

    fireEvent.change(screen.getByDisplayValue("Be terse."), {
      target: { value: "Be terser." },
    });

    expect(store.getState().nodes[0]!.data.values).toEqual({
      system_prompt: "Be terser.",
    });
  });
});

describe("NodeInspector — 27.6, debounced snapshots", () => {
  it("takes exactly one undo step for a whole edit session, not one per keystroke", () => {
    const store = seededStore();
    store
      .getState()
      .setLastSelection({ nodes: [{ id: "n1" } as never], edges: [] });
    const NodeInspector = createNodeInspector(store);
    render(<NodeInspector />);

    expect(store.getState().past).toHaveLength(0);

    const field = screen.getByDisplayValue("Be terse.");
    fireEvent.change(field, { target: { value: "Be t" } });
    fireEvent.change(field, { target: { value: "Be te" } });
    fireEvent.change(field, { target: { value: "Be ter" } });

    expect(store.getState().past).toHaveLength(1);

    fireEvent.blur(field);
    fireEvent.change(field, { target: { value: "A new edit." } });

    expect(store.getState().past).toHaveLength(2);
  });
});

describe("NodeInspector — 27.4, same field renderer as the inline node", () => {
  it("renders the same field via the same value as TemplateNode's inline copy", async () => {
    const { FlowCanvas } = await import("../FlowCanvas");
    const { createTemplateNode } = await import("../nodes/TemplateNode");

    // `selected: true` on the seed node, not a manual `setLastSelection`
    // before mount — xyflow fires its own `onSelectionChange` during
    // mount reflecting real `node.selected` state, which would otherwise
    // overwrite a manually-primed `lastSelection` back to empty (the same
    // real behavior Task 24's FlowCanvas.test.tsx documents).
    const store = createFlowStore();
    store.getState().setNodes([
      {
        ...node("n1", "ZeroShotAgent", { system_prompt: "Be terse." }),
        selected: true,
      },
    ]);
    store.getState().resetDirty();
    store.getState().setInspectorOpen(true);
    const NodeInspector = createNodeInspector(store);

    render(
      <div>
        <div style={{ width: 800, height: 600 }}>
          <FlowCanvas
            store={store}
            lookupHandleTypes={() => null}
            nodeTypes={{ templateNode: createTemplateNode(store) }}
          />
        </div>
        <NodeInspector />
      </div>
    );

    // Both the on-canvas node and the side panel render the field's
    // current value through fields/index.ts's PromptField — proven by
    // both showing it, not a second, divergent implementation.
    expect(screen.getAllByDisplayValue("Be terse.")).toHaveLength(2);
  });
});
