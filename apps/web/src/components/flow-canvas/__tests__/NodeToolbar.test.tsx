/**
 * Tests for NodeToolbar — mounted through the real FlowCanvas + TemplateNode
 * (Task 26), since the toolbar is only rendered by TemplateNode when its
 * node is selected, and it needs real xyflow context (`NodeToolbar` from
 * `@xyflow/react`) for positioning.
 *
 * Brief: .tmp/flow-canvas-task-27-brief.md
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { FlowCanvas } from "../FlowCanvas";
import { createTemplateNode } from "../nodes/TemplateNode";
import type { CanvasNode, PortType } from "../types/flow";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const mockUseComponentTemplates = jest.fn();
jest.mock("../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => mockUseComponentTemplates(),
}));

const TEMPLATE: GroupedComponentTemplates = {
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
        prompt: {
          type: "prompt" as any,
          display_name: "Prompt",
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
        inputs: [{ name: "message", types: ["Message"] }],
        outputs: [{ name: "message", types: ["Message"] }],
      },
    },
  ],
};

function lookupAlwaysMessage(): PortType[] | null {
  return ["Message"];
}

function node(id: string, selected: boolean): CanvasNode {
  return {
    id,
    type: "templateNode",
    position: { x: 100, y: 100 },
    selected,
    data: { type: "ZeroShotAgent", templateVersion: 1, values: {} },
  };
}

function renderSelectedNode() {
  const store = createFlowStore();
  store.getState().setNodes([node("n1", true)]);
  store.getState().resetDirty();
  render(
    <div style={{ width: 800, height: 600 }}>
      <FlowCanvas
        store={store}
        lookupHandleTypes={lookupAlwaysMessage}
        nodeTypes={{ templateNode: createTemplateNode(store) }}
      />
    </div>
  );
  return store;
}

beforeEach(() => {
  mockUseComponentTemplates.mockReset();
  mockUseComponentTemplates.mockReturnValue({
    data: TEMPLATE,
    isLoading: false,
    error: undefined,
  });
});

describe("NodeToolbar — renders only for the selected node", () => {
  it("shows the toolbar for a selected node", () => {
    renderSelectedNode();
    expect(screen.getByTestId("node-toolbar-n1")).toBeInTheDocument();
  });
});

describe("NodeToolbar — Parameters is an always-visible labelled toggle (upstream ToolbarButton parity)", () => {
  it("shows a labelled Parameters button that toggles the inspector panel", () => {
    const store = renderSelectedNode();
    expect(store.getState().isInspectorOpen).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /show node details/i }));
    expect(store.getState().isInspectorOpen).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /hide node details/i }));
    expect(store.getState().isInspectorOpen).toBe(false);
  });
});

// Duplicate/Copy/Delete live behind the "..." menu (Post-P4 toolbar
// restructure — see NodeToolbar.tsx's header comment), so each test opens
// it before reaching for the action's own accessible name.
function openMoreActionsMenu() {
  fireEvent.click(screen.getByRole("button", { name: /more actions/i }));
}

describe("NodeToolbar — 27.7, delete is undoable", () => {
  it("takes a snapshot before removing the node", () => {
    const store = renderSelectedNode();
    expect(store.getState().past).toHaveLength(0);

    openMoreActionsMenu();
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(store.getState().nodes).toHaveLength(0);
    expect(store.getState().past).toHaveLength(1);

    store.getState().undo();
    expect(store.getState().nodes).toHaveLength(1);
  });
});

describe("NodeToolbar — 27.8, duplicate creates a fresh id", () => {
  it("adds a new node with a different id, offset from the original", () => {
    const store = renderSelectedNode();

    openMoreActionsMenu();
    fireEvent.click(screen.getByRole("button", { name: /^duplicate$/i }));

    const ids = store.getState().nodes.map((n) => n.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    const duplicate = store.getState().nodes.find((n) => n.id !== "n1")!;
    expect(duplicate.position).toEqual({ x: 140, y: 140 });
  });
});

describe("NodeToolbar — Copy shares state with the canvas's own Ctrl+V", () => {
  it("populates the store's clipboard so mod+v can paste it", () => {
    const store = renderSelectedNode();

    openMoreActionsMenu();
    fireEvent.click(screen.getByRole("button", { name: /^copy$/i }));
    expect(store.getState().clipboard?.nodes).toHaveLength(1);

    // react-hotkeys-hook's `useHotkeys` listens on `document` by default,
    // not on the canvas wrapper's own `onKeyDown` (that's a separate,
    // plain React handler this component also has, used for
    // delete/undo/redo) — confirmed by reading its source, not assumed.
    fireEvent.keyDown(document, { key: "v", code: "KeyV", ctrlKey: true });

    expect(store.getState().nodes).toHaveLength(2);
  });
});
