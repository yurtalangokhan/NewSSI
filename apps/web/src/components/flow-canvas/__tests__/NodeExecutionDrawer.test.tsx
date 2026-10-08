import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { NodeExecutionDrawer } from "../nodes/NodeExecutionDrawer";
import type { NodeExecutionData } from "../types/execution";
import type { KnowledgeEvidence } from "@/lib/api/domains/chat/knowledge-evidence-types";
import { setupUser } from "@tests/setup/test-utils";

// Mock clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn().mockImplementation(() => Promise.resolve()),
  },
});

function documentEvidence(query: string, content: string): KnowledgeEvidence {
  return {
    kind: "document",
    tool: "document_search",
    query,
    collections: [{ id: "col-1", name: "İK Politikaları" }],
    chunks: [
      {
        ref: 1,
        id: "chk-1",
        score: 0.89,
        content,
        truncated: false,
        collectionId: "col-1",
        source: {
          document: "İzin Yönetmeliği 2026.pdf",
          title: null,
          page: 7,
          section: null,
          fileId: null,
        },
      },
    ],
    graph: null,
    modelContext: content,
    modelContextTruncated: false,
    elapsedMs: 380,
  };
}

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

  it("opens a retrieval node on its sources and lists the chunks it used", () => {
    const retrievalData: NodeExecutionData = {
      nodeId: "search-1",
      label: "Politika belgeleri",
      status: "done",
      durationMs: 380,
      tools: [],
      evidence: [
        {
          kind: "document",
          tool: "document_search",
          query: "izin devri",
          collections: [{ id: "col-1", name: "İK Politikaları" }],
          chunks: [
            {
              ref: 1,
              id: "chk-1",
              score: 0.89,
              content: "Kullanılmayan izin devredilir.",
              truncated: false,
              collectionId: "col-1",
              source: {
                document: "İzin Yönetmeliği 2026.pdf",
                title: null,
                page: 7,
                section: null,
                fileId: null,
              },
            },
          ],
          graph: null,
          modelContext: "Kullanılmayan izin devredilir.",
          modelContextTruncated: false,
          elapsedMs: 380,
        },
      ],
    };

    render(<NodeExecutionDrawer nodeId="search-1" data={retrievalData} />);
    expect(screen.getByText(/(Sources|Kaynaklar) \(1\)/)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/Details|Detaylar/i));

    expect(screen.getByText("İzin Yönetmeliği 2026")).toBeInTheDocument();
    // The preview is split into highlighted segments; assert the whole text.
    expect(
      screen.getByTestId("node-execution-drawer-search-1")
    ).toHaveTextContent("Kullanılmayan izin devredilir.");
  });

  describe("sources", () => {
    const withSources: NodeExecutionData = {
      nodeId: "search-1",
      label: "Politika belgeleri",
      status: "done",
      durationMs: 380,
      thinking: "Belgelerde aranacak.",
      tools: [],
      output: "Tamam.",
      evidence: [
        documentEvidence("izin devri", "Kullanılmayan izin devredilir."),
      ],
    };

    it("switches tabs from the keyboard", async () => {
      const user = setupUser();
      render(<NodeExecutionDrawer nodeId="search-1" data={withSources} />);
      fireEvent.click(screen.getByText(/Details|Detaylar/i));

      screen.getByRole("button", { name: /(Sources|Kaynaklar) \(1\)/ }).focus();
      await user.keyboard("{Enter}");
      expect(screen.getByText("İzin Yönetmeliği 2026")).toBeInTheDocument();

      screen.getByRole("button", { name: /Tools|Araçlar/i }).focus();
      await user.keyboard(" ");
      expect(
        screen.queryByText("İzin Yönetmeliği 2026")
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/harici araç çağrılmadı|No external tools/i)
      ).toBeInTheDocument();
    });

    it("tells assistive technology which tab is showing", () => {
      render(<NodeExecutionDrawer nodeId="search-1" data={withSources} />);
      fireEvent.click(screen.getByText(/Details|Detaylar/i));

      const thinking = screen.getByRole("button", {
        name: /^(Thinking|Düşünce)$/,
      });
      const sources = screen.getByRole("button", {
        name: /(Sources|Kaynaklar) \(1\)/,
      });
      expect(thinking).toHaveAttribute("aria-pressed", "true");
      expect(sources).toHaveAttribute("aria-pressed", "false");

      fireEvent.click(sources);

      expect(thinking).toHaveAttribute("aria-pressed", "false");
      expect(sources).toHaveAttribute("aria-pressed", "true");
    });

    it("follows the loop iteration the reader picks", async () => {
      const user = setupUser();
      const looped: NodeExecutionData = {
        nodeId: "search-1",
        label: "Politika belgeleri",
        status: "done",
        durationMs: 900,
        tools: [],
        evidence: [
          documentEvidence("birinci sorgu", "Birinci turun parçası."),
          documentEvidence("ikinci sorgu", "İkinci turun parçası."),
        ],
        iterations: [
          {
            iteration: 1,
            status: "done",
            durationMs: 400,
            evidence: [
              documentEvidence("birinci sorgu", "Birinci turun parçası."),
            ],
          },
          {
            iteration: 2,
            status: "done",
            durationMs: 500,
            evidence: [
              documentEvidence("ikinci sorgu", "İkinci turun parçası."),
            ],
          },
        ],
      };
      render(<NodeExecutionDrawer nodeId="search-1" data={looped} />);
      fireEvent.click(screen.getByText(/Details|Detaylar/i));

      // The latest iteration leads until the reader picks another.
      const drawer = screen.getByTestId("node-execution-drawer-search-1");
      expect(drawer).toHaveTextContent("İkinci turun parçası.");
      expect(drawer).not.toHaveTextContent("Birinci turun parçası.");
      expect(
        screen.getByRole("button", { name: /(Sources|Kaynaklar) \(1\)/ })
      ).toBeInTheDocument();

      const first = screen.getByRole("button", { name: /(Tur|Iteration) 1/ });
      first.focus();
      await user.keyboard("{Enter}");

      expect(drawer).toHaveTextContent("Birinci turun parçası.");
      expect(drawer).not.toHaveTextContent("İkinci turun parçası.");
      expect(first).toHaveAttribute("aria-pressed", "true");
    });
  });
});
