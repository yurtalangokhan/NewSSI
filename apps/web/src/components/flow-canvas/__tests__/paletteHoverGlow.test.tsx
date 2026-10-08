/**
 * End-to-end regression guard for flow-canvas-connect-ux: hovering a
 * palette item glows a placed canvas node's compatible input handle. Each
 * piece (ComponentSidebarItem publishing to the store, TemplateNode reading
 * it) has its own unit coverage; this proves they're actually wired
 * together through ComponentSidebar -> FlowAgentEditorPage's shared store,
 * the one thing those unit tests can't catch on their own (a missed `store`
 * prop at a call site).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { ComponentSidebar } from "../components/ComponentSidebar";
import { FlowCanvas } from "../FlowCanvas";
import { createTemplateNode } from "../nodes/TemplateNode";
import type { CanvasNode } from "../types/flow";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const mockUseComponentTemplates = jest.fn();
jest.mock("../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => mockUseComponentTemplates(),
}));

const GROUPED: GroupedComponentTemplates = {
  agents: [
    {
      type: "ModelSource",
      category: "agents",
      display_name: "Model Source",
      description: "",
      icon: null,
      template_version: 1,
      lifecycle: "stable",
      kind: "execution",
      inputs: {},
      handles: {
        inputs: [],
        outputs: [{ name: "model_out", types: ["Model"] }],
      },
    },
  ],
};

function modelConsumerNode(): CanvasNode {
  return {
    id: "n1",
    type: "templateNode",
    position: { x: 0, y: 0 },
    data: { type: "ModelConsumer", templateVersion: 1, values: {} },
  };
}

beforeEach(() => {
  mockUseComponentTemplates.mockReset();
  mockUseComponentTemplates.mockReturnValue({
    data: {
      ...GROUPED,
      logic: [
        {
          type: "ModelConsumer",
          category: "logic",
          display_name: "Model Consumer",
          description: "",
          icon: null,
          template_version: 1,
          lifecycle: "stable",
          kind: "execution",
          inputs: {},
          handles: {
            inputs: [{ name: "model_in", types: ["Model"] }],
            outputs: [],
          },
        },
      ],
    },
    isLoading: false,
    error: undefined,
  });
});

describe("Palette hover glow — end to end", () => {
  it("glows a placed node's compatible input handle while its palette counterpart is hovered", () => {
    const store = createFlowStore();
    store.getState().setNodes([modelConsumerNode()]);
    store.getState().resetDirty();
    const nodeTypes = { templateNode: createTemplateNode(store) };

    render(
      <div style={{ display: "flex" }}>
        <ComponentSidebar store={store} />
        <div style={{ width: 800, height: 600 }}>
          <FlowCanvas
            store={store}
            lookupHandleTypes={() => null}
            nodeTypes={nodeTypes}
          />
        </div>
      </div>
    );

    const sourceItem = screen.getByTestId("sidebar-item-ModelSource");
    expect(screen.getByTestId("handle-target-model_in")).toBeInTheDocument();
    expect(screen.getByTestId("div-handle-target-model_in")).not.toHaveClass(
      "lf-handle-glow"
    );

    fireEvent.mouseEnter(sourceItem);
    expect(screen.getByTestId("div-handle-target-model_in")).toHaveClass(
      "lf-handle-glow"
    );

    fireEvent.mouseLeave(sourceItem);
    expect(screen.getByTestId("div-handle-target-model_in")).not.toHaveClass(
      "lf-handle-glow"
    );
  });
});
