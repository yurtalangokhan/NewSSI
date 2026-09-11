import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { NodeExecutionDrawer } from "../nodes/NodeExecutionDrawer";
import type { NodeExecutionData } from "../types/execution";

// Mock clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn().mockImplementation(() => Promise.resolve()),
  },
});

describe("NodeExecutionDrawer", () => {
  const sampleData: NodeExecutionData = {
    nodeId: "node-stage-research",
    label: "ResearchStage",
    status: "done",
    durationMs: 254000,
    thinking: "Sen bu is akisinin ilk adimi olan Veri Toplama asamasindasin.",
    tools: [
      {
        toolName: "web_search",
        label: "Web Araştırma",
        callCount: 2,
        durationMs: 23660,
        status: "done",
        invocations: [
          {
            index: 1,
            status: "done",
            durationMs: 12000,
            input: { query: "2026 AI trends" },
            output: "Bulunan 5 kaynak",
          },
        ],
      },
    ],
    output: "++ARAŞTIRMA BRİFİNGİ++\nElde edilen sonuçlar...",
  };

  it("renders summary badges in collapsed state", () => {
    render(
      <NodeExecutionDrawer nodeId="node-stage-research" data={sampleData} />
    );

    expect(screen.getByText(/Thinking|Düşünce/i)).toBeInTheDocument();
    expect(screen.getByText(/2.*(tools|araç)/i)).toBeInTheDocument();
    expect(screen.getByText(/Output|Çıktı/i)).toBeInTheDocument();
    expect(screen.getByText(/Details|Detaylar/i)).toBeInTheDocument();
  });

  it("expands on click and displays thinking content", () => {
    const onToggle = jest.fn();
    render(
      <NodeExecutionDrawer
        nodeId="node-stage-research"
        data={sampleData}
        onToggle={onToggle}
      />
    );

    const expandBtn = screen.getByText(/Details|Detaylar/i);
    fireEvent.click(expandBtn);

    expect(onToggle).toHaveBeenCalledWith(true);
    expect(
      screen.getByText(
        /Sen bu is akisinin ilk adimi olan Veri Toplama asamasindasin./i
      )
    ).toBeInTheDocument();
  });

  it("switches tabs between Thinking, Tools, and Output", () => {
    render(
      <NodeExecutionDrawer nodeId="node-stage-research" data={sampleData} />
    );

    // Expand
    fireEvent.click(screen.getByText(/Details|Detaylar/i));

    // Click Tools tab
    const toolsTab = screen.getByRole("button", { name: /Tools|Araçlar/i });
    fireEvent.click(toolsTab);

    expect(screen.getByText("Web Araştırma")).toBeInTheDocument();
    expect(screen.getByText(/2026 AI trends/i)).toBeInTheDocument();

    // Click Output tab
    const outputTab = screen.getByRole("button", { name: /Output|Çıktı/i });
    fireEvent.click(outputTab);

    expect(screen.getByText(/ARAŞTIRMA BRİFİNGİ/i)).toBeInTheDocument();
  });

  it("supports multiple loop iterations switcher", () => {
    const multiIterData: NodeExecutionData = {
      ...sampleData,
      iterations: [
        {
          iteration: 1,
          thinking: "Düşünce Tur 1",
          output: "Çıktı Tur 1",
          status: "done",
          durationMs: 1000,
        },
        {
          iteration: 2,
          thinking: "Düşünce Tur 2",
          output: "Çıktı Tur 2",
          status: "done",
          durationMs: 1500,
        },
      ],
    };

    render(
      <NodeExecutionDrawer nodeId="node-stage-research" data={multiIterData} />
    );

    // Expand
    fireEvent.click(screen.getByText(/Details|Detaylar/i));

    const iterBtns = screen.getAllByRole("button", { name: /1|2/i });
    expect(iterBtns.length).toBeGreaterThanOrEqual(2);

    // Click first iteration
    fireEvent.click(iterBtns[0]!);
    expect(screen.getByText(/Düşünce Tur 1/i)).toBeInTheDocument();
  });

  it("copies thinking text to clipboard", async () => {
    render(
      <NodeExecutionDrawer nodeId="node-stage-research" data={sampleData} />
    );

    fireEvent.click(screen.getByText(/Details|Detaylar/i));

    const copyBtn = screen.getByText(/Copy Thinking|Düşünceyi Kopyala/i);
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      sampleData.thinking
    );
  });
});
