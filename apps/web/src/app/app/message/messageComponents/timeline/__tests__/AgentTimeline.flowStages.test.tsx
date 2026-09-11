import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentTimeline } from "../AgentTimeline";
import type { StageGroup } from "../hooks/flowStageGrouping";

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({ hasBackground: false }),
}));
jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useStreamingStartTime: () => null,
}));

const chatState = { agent: { id: 1, name: "Flow" } } as any;

function stage(overrides: Partial<StageGroup> = {}): StageGroup {
  return {
    kind: "stage",
    stageKey: "R#1",
    nodeId: "R",
    label: "Araştırma Ajanı",
    order: 1,
    iteration: 1,
    status: "running",
    durationMs: null,
    outputText: "",
    turnGroups: [],
    ...overrides,
  };
}

describe("AgentTimeline — flow stage sections", () => {
  it("renders the numbered stage section once the run has finished", () => {
    render(
      <AgentTimeline
        turnGroups={[]}
        flowStageSections={[stage({ status: "done" })]}
        chatState={chatState}
        stopPacketSeen
      />
    );
    expect(screen.getByText(/1\.\s*Araştırma Ajanı/)).toBeInTheDocument();
    expect(screen.getByTestId("flow-stage-sections")).toBeInTheDocument();
  });

  it("does not fall back to the bare empty state — the section body renders", () => {
    render(
      <AgentTimeline
        turnGroups={[]}
        flowStageSections={[stage()]}
        chatState={chatState}
        stopPacketSeen
      />
    );
    // The EMPTY-state branch returns a container with a lone header <p> and no
    // children; the section list proves we rendered the real body.
    expect(screen.getByTestId("flow-stage-sections")).toBeInTheDocument();
  });

  it("keeps the card collapsed while the flow run is still streaming", () => {
    // A live run: no stop packet yet. The numbered sections stay folded (the
    // header chevron reveals them); the collapsed card shows a compact
    // thinking peek instead (fed by getActiveStagePreviewStep).
    render(
      <AgentTimeline
        turnGroups={[]}
        flowStageSections={[stage()]}
        chatState={chatState}
      />
    );
    expect(screen.queryByTestId("flow-stage-sections")).not.toBeInTheDocument();
  });

  it("renders nothing extra for a non-flow agent (no sections)", () => {
    render(
      <AgentTimeline
        turnGroups={[]}
        flowStageSections={[]}
        chatState={chatState}
      />
    );
    expect(screen.queryByTestId("flow-stage-sections")).not.toBeInTheDocument();
  });

  it("renders the collapse/expand toggle button in header and allows toggling when flowStageSections is present", () => {
    render(
      <AgentTimeline
        turnGroups={[]}
        flowStageSections={[stage({ status: "done" })]}
        chatState={chatState}
        stopPacketSeen
      />
    );
    // Initially expanded on completion
    expect(screen.getByTestId("flow-stage-sections")).toBeInTheDocument();

    // Toggle button should be present in header (aria-label "Zaman çizelgesini daralt" or "Collapse timeline")
    const toggleBtn = screen.getByRole("button", {
      name: /daralt|collapse/i,
    });
    expect(toggleBtn).toBeInTheDocument();

    // Click to collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId("flow-stage-sections")).not.toBeInTheDocument();

    // Click to expand again
    const expandBtn = screen.getByRole("button", {
      name: /genişlet|expand/i,
    });
    fireEvent.click(expandBtn);
    expect(screen.getByTestId("flow-stage-sections")).toBeInTheDocument();
  });
});
