/**
 * InlineFlowDesigner — a local-only canvas mount used while creating a new
 * flow agent, before an `agent_definitions` row (and thus a real
 * `definitionId`) exists. Unlike `FlowAgentEditorPage`, this must never
 * reach for `useFlowDraft`/`useFlowVersions`/`VersionBar` — there's nothing
 * to autosave or version against yet.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";

jest.mock("@/components/flow-canvas/hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => ({
    data: {},
    isLoading: false,
    error: undefined,
  }),
}));

let mockHasAnyPermission: jest.Mock;
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ hasAnyPermission: mockHasAnyPermission }),
}));

import InlineFlowDesigner from "../InlineFlowDesigner";

describe("InlineFlowDesigner", () => {
  beforeEach(() => {
    mockHasAnyPermission = jest.fn().mockReturnValue(true);
  });

  it("opens import flow modal when import JSON trigger is clicked", () => {
    render(<InlineFlowDesigner />);
    const trigger = screen.getByTestId("inline-import-flow-trigger");
    expect(trigger).toBeInTheDocument();

    const { fireEvent } = require("@testing-library/react");
    fireEvent.click(trigger);

    expect(screen.getByTestId("import-modal-tab-upload")).toBeInTheDocument();
    expect(screen.getByTestId("import-modal-tab-paste")).toBeInTheDocument();
  });

  it("renders the sidebar and canvas without any version/save UI", () => {
    render(<InlineFlowDesigner />);

    expect(screen.getByTestId("inline-flow-designer")).toBeInTheDocument();
    expect(screen.getByTestId("component-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("flow-canvas-wrapper")).toBeInTheDocument();
    expect(screen.queryByTestId("version-bar")).not.toBeInTheDocument();
  });

  it("shows a notice that the design isn't saved yet", () => {
    render(<InlineFlowDesigner />);

    expect(
      screen.getByText(
        /(will be saved when you finish creating the agent|won't be saved until you finish creating the agent)/i
      )
    ).toBeInTheDocument();
  });

  it("lets a user with flow:execute open the playground against the unsaved graph", () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "in",
        position: { x: 0, y: 0 },
        data: { type: "ChatInput", templateVersion: 1, values: {} },
      } as any,
    ]);
    render(<InlineFlowDesigner store={store} />);

    expect(screen.queryByTestId("playground-panel")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("inline-playground-trigger"));
    expect(screen.getByTestId("playground-panel")).toBeInTheDocument();
    expect(mockHasAnyPermission).toHaveBeenCalledWith(["flow:execute"]);
  });

  it("hides the playground trigger without flow:execute permission", () => {
    mockHasAnyPermission = jest.fn().mockReturnValue(false);
    render(<InlineFlowDesigner />);

    expect(
      screen.queryByTestId("inline-playground-trigger")
    ).not.toBeInTheDocument();
  });

  it("disables the test button while the canvas has neither a ChatInput nor a ChatOutput node", () => {
    const store = createFlowStore();
    render(<InlineFlowDesigner store={store} />);

    expect(screen.getByTestId("inline-playground-trigger")).toBeDisabled();
  });

  it("enables the test button once a ChatInput node is on the canvas", () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "in",
        position: { x: 0, y: 0 },
        data: { type: "ChatInput", templateVersion: 1, values: {} },
      } as any,
    ]);
    render(<InlineFlowDesigner store={store} />);

    expect(screen.getByTestId("inline-playground-trigger")).toBeEnabled();
  });

  it("enables the test button once a ChatOutput node is on the canvas", () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "out",
        position: { x: 0, y: 0 },
        data: { type: "ChatOutput", templateVersion: 1, values: {} },
      } as any,
    ]);
    render(<InlineFlowDesigner store={store} />);

    expect(screen.getByTestId("inline-playground-trigger")).toBeEnabled();
  });
});
