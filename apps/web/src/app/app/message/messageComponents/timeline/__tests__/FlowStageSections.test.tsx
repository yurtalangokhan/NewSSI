import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  StageGroupSection,
  LoopGroupSection,
  FlowStageSections,
} from "../FlowStageSections";
import type { StageGroup, LoopGroup } from "../hooks/flowStageGrouping";

const chatState = {} as any;

function stage(overrides: Partial<StageGroup> = {}): StageGroup {
  return {
    kind: "stage",
    stageKey: "A#1",
    nodeId: "A",
    label: "Analiz Ajanı",
    order: 2,
    iteration: 1,
    status: "done",
    durationMs: 12000,
    outputText: "ara çıktı metni",
    turnGroups: [],
    ...overrides,
  };
}

describe("StageGroupSection", () => {
  it("renders a numbered header with label and duration", () => {
    render(
      <StageGroupSection
        group={stage()}
        index={2}
        chatState={chatState}
        expanded={false}
        onToggle={() => {}}
      />
    );
    expect(screen.getByText(/2\.\s*Analiz Ajanı/)).toBeInTheDocument();
    expect(screen.getByText(/12\.00s/)).toBeInTheDocument();
  });

  it("hides the body when collapsed and shows the Çıktı block when expanded", () => {
    const { rerender } = render(
      <StageGroupSection
        group={stage()}
        index={2}
        chatState={chatState}
        expanded={false}
        onToggle={() => {}}
      />
    );
    expect(screen.queryByText("ara çıktı metni")).not.toBeInTheDocument();

    rerender(
      <StageGroupSection
        group={stage()}
        index={2}
        chatState={chatState}
        expanded
        onToggle={() => {}}
      />
    );
    expect(screen.getByText("Çıktı")).toBeInTheDocument();
    expect(screen.getByText("ara çıktı metni")).toBeInTheDocument();
  });

  it("calls onToggle when the header button is clicked", () => {
    const onToggle = jest.fn();
    render(
      <StageGroupSection
        group={stage()}
        index={2}
        chatState={chatState}
        expanded={false}
        onToggle={onToggle}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /Analiz Ajanı/ }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("counts only tool-invocation steps in the wrench badge, not reasoning", () => {
    const mkStep = (type: string, key: string) => ({
      key,
      turnIndex: 0,
      tabIndex: 0,
      packets: [{ obj: { type } }],
    });
    const group = stage({
      durationMs: null,
      turnGroups: [
        {
          turnIndex: 0,
          isParallel: false,
          steps: [
            mkStep("reasoning_start", "r0"),
            mkStep("search_tool_start", "t1"),
            mkStep("custom_tool_start", "t2"),
          ],
        },
      ] as any,
    });
    render(
      <StageGroupSection
        group={group}
        index={3}
        chatState={chatState}
        expanded={false}
        onToggle={() => {}}
      />
    );
    // 2 tool calls counted; the reasoning step is excluded
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows a spinner when the stage is running", () => {
    render(
      <StageGroupSection
        group={stage({ status: "running" })}
        index={1}
        chatState={chatState}
        expanded={false}
        onToggle={() => {}}
      />
    );
    expect(screen.getByTestId("stage-status-running")).toBeInTheDocument();
  });
});

describe("StageOutputBlock — full-view modal", () => {
  it("opens the full stage output in a modal from a maximize button", () => {
    const output = "satır ".repeat(200);
    render(
      <TooltipProvider>
        <StageGroupSection
          group={stage({ label: "Araştırma", outputText: output })}
          index={1}
          chatState={chatState}
          expanded
          onToggle={() => {}}
        />
      </TooltipProvider>
    );

    fireEvent.click(screen.getByTestId("stage-output-maximize"));

    const dialog = screen.getByRole("dialog");
    // header carries the numbered stage name, body carries the full text
    expect(within(dialog).getByText(/1\.\s*Araştırma/)).toBeInTheDocument();
    expect(dialog).toHaveTextContent("satır satır");
  });

  it("offers the maximize button regardless of output length", () => {
    render(
      <TooltipProvider>
        <StageGroupSection
          group={stage({ outputText: "kısa çıktı" })}
          index={1}
          chatState={chatState}
          expanded
          onToggle={() => {}}
        />
      </TooltipProvider>
    );

    fireEvent.click(screen.getByTestId("stage-output-maximize"));
    expect(screen.getByRole("dialog")).toHaveTextContent("kısa çıktı");
  });
});

describe("LoopGroupSection", () => {
  const loop: LoopGroup = {
    kind: "loop",
    // Base node label only; the component appends the translated " Döngüsü".
    label: "Analiz",
    iterationCount: 3,
    durationMs: 41000,
    iterations: [1, 2, 3].map((k) => [
      stage({
        stageKey: `A#${k}`,
        order: k,
        iteration: k,
        label: "Analiz",
        outputText: "",
      }),
    ]),
  };

  it("renders the loop header with the turn count", () => {
    render(
      <LoopGroupSection
        group={loop}
        index={1}
        chatState={chatState}
        expanded
        onToggle={() => {}}
      />
    );
    expect(screen.getByText(/Analiz Loop/)).toBeInTheDocument();
    expect(screen.getByText(/3 iterations/)).toBeInTheDocument();
  });

  it("renders one 'Tur k' sub-header per iteration when expanded", () => {
    render(
      <LoopGroupSection
        group={loop}
        index={1}
        chatState={chatState}
        expanded
        onToggle={() => {}}
      />
    );
    expect(screen.getByText("Iteration 1")).toBeInTheDocument();
    expect(screen.getByText("Iteration 2")).toBeInTheDocument();
    expect(screen.getByText("Iteration 3")).toBeInTheDocument();
  });
});

describe("FlowStageSections", () => {
  it("renders nothing when there are no sections (non-flow agent)", () => {
    const { container } = render(
      <FlowStageSections sections={[]} chatState={chatState} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("numbers sections and starts a running stage expanded, a completed one collapsed", () => {
    render(
      <FlowStageSections
        sections={[
          stage({
            stageKey: "R#1",
            order: 1,
            label: "Araştırma",
            status: "done",
            outputText: "arastirma ciktisi",
          }),
          stage({
            stageKey: "A#1",
            order: 2,
            label: "Analiz",
            status: "running",
            outputText: "",
          }),
        ]}
        chatState={chatState}
      />
    );
    expect(screen.getByText(/1\.\s*Araştırma/)).toBeInTheDocument();
    expect(screen.getByText(/2\.\s*Analiz/)).toBeInTheDocument();
    // completed R#1 collapsed -> its output hidden
    expect(screen.queryByText("arastirma ciktisi")).not.toBeInTheDocument();
    // running A#1 expanded -> spinner visible
    expect(screen.getByTestId("stage-status-running")).toBeInTheDocument();
  });

  it("does not render expand-all or collapse-all buttons", () => {
    render(
      <FlowStageSections
        sections={[
          stage({
            stageKey: "R#1",
            order: 1,
            label: "Araştırma",
            status: "done",
            outputText: "arastirma ciktisi",
          }),
          stage({
            stageKey: "A#1",
            order: 2,
            label: "Analiz",
            status: "done",
            outputText: "analiz ciktisi",
          }),
        ]}
        chatState={chatState}
      />
    );
    expect(
      screen.queryByRole("button", { name: /Tümünü aç/ })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Tümünü kapat/ })
    ).not.toBeInTheDocument();
  });
});
