/**
 * 28.12 (canvas half) — a flow-backed agent mounts the canvas, sidebar,
 * inspector, and version bar together. Every data hook is mocked (this
 * project's established pattern for every flow-canvas component test)
 * since the point here is the wiring between pieces already tested in
 * isolation (Tasks 24-27, this task's own hook/VersionBar tests), not
 * their individual request/response logic.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { fireEvent, render, screen } from "@testing-library/react";

jest.mock("@/components/flow-canvas/hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => ({
    data: {},
    isLoading: false,
    error: undefined,
  }),
}));
jest.mock("@/components/flow-canvas/hooks/useFlowDraft", () => ({
  useFlowDraft: () => ({
    isLoading: false,
    loadError: null,
    isSaving: false,
    saveError: null,
  }),
  saveDraftNow: jest.fn(),
}));
jest.mock("@/components/flow-canvas/hooks/useFlowVersions", () => ({
  useFlowVersions: () => ({
    versions: [],
    isLoading: false,
    error: undefined,
    publishedVersion: null,
    draftVersion: null,
    publish: jest.fn(),
    rollback: jest.fn(),
    refresh: jest.fn(),
    getVersionDetail: jest.fn(),
  }),
}));
jest.mock("@/components/flow-canvas/hooks/useFlowValidation", () => ({
  useFlowValidation: () => ({
    result: null,
    isValidating: false,
    hasErrors: false,
    errorsByNode: new Map(),
    errorsByEdge: new Map(),
    warningsByNode: new Map(),
  }),
}));
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ hasAnyPermission: () => true }),
}));

import FlowAgentEditorPage from "../FlowAgentEditorPage";

describe("FlowAgentEditorPage — 28.12, flow agent mounts in canvas mode", () => {
  it("renders the version bar, sidebar, and canvas together", () => {
    render(
      <FlowAgentEditorPage agentDefinitionId="11111111-1111-1111-1111-111111111111" />
    );

    expect(screen.getByTestId("flow-agent-editor-page")).toBeInTheDocument();
    expect(screen.getByTestId("version-bar")).toBeInTheDocument();
    expect(screen.getByTestId("component-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("flow-canvas-wrapper")).toBeInTheDocument();
  });

  it("45 — opens and closes the version history panel from the VersionBar toggle", () => {
    render(
      <FlowAgentEditorPage agentDefinitionId="11111111-1111-1111-1111-111111111111" />
    );

    fireEvent.click(screen.getByTestId("toggle-version-history"));
    expect(screen.getByTestId("version-history-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("version-history-close"));
    expect(
      screen.queryByTestId("version-history-panel")
    ).not.toBeInTheDocument();
  });
});
