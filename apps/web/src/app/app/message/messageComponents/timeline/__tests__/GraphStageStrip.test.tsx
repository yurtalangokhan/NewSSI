import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import GraphStageStrip from "../GraphStageStrip";

jest.mock("@/lib/fetcher", () => ({
  errorHandlingFetcher: jest.fn(),
}));

// Mock useAppBackground so background blur styling doesn't break
jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({ hasBackground: false }),
}));

const { errorHandlingFetcher } = jest.requireMock("@/lib/fetcher");

function stagePacket(
  type: "graph_stage_start" | "graph_stage_end",
  stage_name: string,
  timestamp: number = 0
) {
  return {
    placement: { turn_index: 0, sub_turn_index: null },
    obj: { type, stage_name, timestamp },
  } as any;
}

const labelOf = (entry: Element): string =>
  entry.querySelector("span")?.textContent ?? entry.textContent ?? "";

function renderStrip(agent: Partial<MinimalPersonaSnapshot>, packets: any[]) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <GraphStageStrip
        agent={agent as MinimalPersonaSnapshot}
        packets={packets}
      />
    </SWRConfig>
  );
}

describe("GraphStageStrip — classic stage/sub_agent agents (unchanged behavior)", () => {
  it("renders nothing when the agent has no stages/sub_agents and isn't flow-backed", () => {
    const { container } = renderStrip(
      { id: 1, stages: [], sub_agents: [] },
      []
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("highlights the active stage and dims completed ones", () => {
    renderStrip({ id: 1, stages: [{ name: "retrieve" }, { name: "answer" }] }, [
      stagePacket("graph_stage_start", "retrieve"),
      stagePacket("graph_stage_end", "retrieve"),
      stagePacket("graph_stage_start", "answer"),
    ]);

    expect(screen.getByText("Retrieve")).toBeInTheDocument();
    expect(screen.getByText("Answer")).toBeInTheDocument();
  });
});

describe("GraphStageStrip — flow-backed agents", () => {
  const flowAgent: Partial<MinimalPersonaSnapshot> = {
    id: 45,
    graph_schema: "flow",
    agent_definition_id: "def-1",
    stages: [],
    sub_agents: [],
  };

  beforeEach(() => {
    errorHandlingFetcher.mockResolvedValue({
      nodes: [
        {
          id: "ChatInput-e050b40c",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "ReActAgent-89c5195d",
          type: "ReActAgent",
          position: { x: 100, y: 0 },
          values: {},
        },
        {
          id: "ChatOutput-808faa0a",
          type: "ChatOutput",
          position: { x: 200, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "ChatInput-e050b40c",
          target: "ReActAgent-89c5195d",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "ReActAgent-89c5195d",
          target: "ChatOutput-808faa0a",
          sourceHandle: "output",
          targetHandle: "input",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });
  });

  afterEach(() => jest.clearAllMocks());

  it("fetches the published flow and derives stage labels from it, stripped of the id suffix", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
    ]);

    await waitFor(() =>
      expect(errorHandlingFetcher).toHaveBeenCalledWith(
        "/api/agent-definitions/def-1/flow/published"
      )
    );
    expect(await screen.findByText("ReAct Agent")).toBeInTheDocument();
    expect(screen.queryByText("ReActAgent-89c5195d")).not.toBeInTheDocument();
  });

  it("pins the flow to the version a flow_version packet names, not the current published one", async () => {
    renderStrip(flowAgent, [
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: { type: "flow_version", version_no: 3 },
      } as any,
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
    ]);

    await waitFor(() =>
      expect(errorHandlingFetcher).toHaveBeenCalledWith(
        "/api/agent-definitions/def-1/flow/versions/3"
      )
    );
    expect(errorHandlingFetcher).not.toHaveBeenCalledWith(
      "/api/agent-definitions/def-1/flow/published"
    );
  });

  it("falls back to the published flow when no flow_version packet is present", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
    ]);

    await waitFor(() =>
      expect(errorHandlingFetcher).toHaveBeenCalledWith(
        "/api/agent-definitions/def-1/flow/published"
      )
    );
  });

  it("shows a canvas/list toggle and switches to the canvas view", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
    ]);

    await screen.findByText("Chat Input");
    fireEvent.click(screen.getByRole("button", { name: /canvas/i }));

    expect(screen.queryByText("Chat Input")).not.toBeInTheDocument();
  });

  it("orders the list by actual call order, arrows between called stages, not-yet-called ones pending at the end", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
      stagePacket("graph_stage_end", "ChatInput-e050b40c"),
      stagePacket("graph_stage_start", "ReActAgent-89c5195d"),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    expect(entries.map(labelOf)).toEqual([
      "Chat Input",
      "ReAct Agent",
      "Chat Output",
    ]);
    expect(entries.map((e) => e.getAttribute("data-status"))).toEqual([
      "done",
      "running",
      "pending",
    ]);

    // One arrow between each pair of the three entries.
    expect(screen.getAllByTestId("stage-arrow")).toHaveLength(2);
  });

  it("keeps advancing when packets is the same mutated array reference across re-renders (live streaming)", async () => {
    const packets: any[] = [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
    ];
    const { rerender } = render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <GraphStageStrip
          agent={flowAgent as MinimalPersonaSnapshot}
          packets={packets}
        />
      </SWRConfig>
    );

    expect(await screen.findByText("Chat Input")).toBeInTheDocument();

    packets.push(stagePacket("graph_stage_end", "ChatInput-e050b40c"));
    packets.push(stagePacket("graph_stage_start", "ReActAgent-89c5195d"));
    rerender(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <GraphStageStrip
          agent={flowAgent as MinimalPersonaSnapshot}
          packets={packets}
        />
      </SWRConfig>
    );

    const entries = await screen.findAllByTestId("stage-entry");
    expect(entries.map((e) => e.getAttribute("data-status"))).toEqual([
      "done",
      "running",
      "pending",
    ]);
  });

  it("derives real per-stage durations from replayed graph_stage timestamps after a refresh", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c", 1000),
      stagePacket("graph_stage_end", "ChatInput-e050b40c", 1350),
      stagePacket("graph_stage_start", "ReActAgent-89c5195d", 1350),
      stagePacket("graph_stage_end", "ReActAgent-89c5195d", 4200),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    expect(entries.map((e) => e.getAttribute("data-status"))).toEqual([
      "done",
      "done",
      "pending",
    ]);

    expect(entries[0]!.textContent).toContain("350ms");
    expect(entries[1]!.textContent).toContain("2.85s");
  });

  it("shows a revisited stage (a loop) as its own separate entry, not a reordering", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
      stagePacket("graph_stage_end", "ChatInput-e050b40c"),
      stagePacket("graph_stage_start", "ReActAgent-89c5195d"),
      stagePacket("graph_stage_end", "ReActAgent-89c5195d"),
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    expect(entries.map(labelOf)).toEqual([
      "Chat Input",
      "ReAct Agent",
      "Chat Input",
      "Chat Output",
    ]);
    expect(entries.map((e) => e.getAttribute("data-status"))).toEqual([
      "done",
      "done",
      "running",
      "pending",
    ]);
  });

  it("resolves a stage label from the node's component type, not its raw id (ConditionalRouter -> If-Else)", async () => {
    errorHandlingFetcher.mockResolvedValueOnce({
      nodes: [
        {
          id: "ChatInput-e050b40c",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "ifelse",
          type: "ConditionalRouter",
          position: { x: 100, y: 0 },
          values: {},
        },
        {
          id: "ChatOutput-808faa0a",
          type: "ChatOutput",
          position: { x: 200, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "ChatInput-e050b40c",
          target: "ifelse",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "ifelse",
          target: "ChatOutput-808faa0a",
          sourceHandle: "output",
          targetHandle: "input",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });

    renderStrip(flowAgent, [stagePacket("graph_stage_start", "ifelse")]);

    expect(await screen.findByText("If-Else")).toBeInTheDocument();
    expect(screen.queryByText("Ifelse")).not.toBeInTheDocument();
  });

  it("filters out passive config nodes like LLMModel and Memory from the stage strip", async () => {
    errorHandlingFetcher.mockResolvedValueOnce({
      nodes: [
        {
          id: "node-chat-input",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "node-llm-model",
          type: "LLMModel",
          position: { x: 50, y: 0 },
          values: {},
        },
        {
          id: "node-long-memory",
          type: "Memory",
          position: { x: 60, y: 0 },
          values: {},
        },
        {
          id: "node-stage-research",
          type: "Research",
          position: { x: 80, y: 0 },
          values: {},
        },
        {
          id: "node-react-executor",
          type: "ReActAgent",
          position: { x: 100, y: 0 },
          values: {},
        },
        {
          id: "node-chat-output",
          type: "ChatOutput",
          position: { x: 200, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "node-chat-input",
          target: "node-stage-research",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "node-stage-research",
          target: "node-react-executor",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e3",
          source: "node-react-executor",
          target: "node-chat-output",
          sourceHandle: "output",
          targetHandle: "input",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });

    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "node-chat-input"),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const labels = entries.map(labelOf);
    expect(labels).toContain("Chat Input");
    expect(labels).toContain("Research");
    expect(labels).toContain("ReAct Agent");
    expect(labels).toContain("Chat Output");
    expect(labels).not.toContain("LLMModel");
    expect(labels).not.toContain("Memory");
    expect(labels).not.toContain("node-llm-model");
    expect(labels).not.toContain("node-long-memory");
  });
});

describe("GraphStageStrip — tool calls on a resource node (WebTools/CalculatorTools)", () => {
  const flowAgent: Partial<MinimalPersonaSnapshot> = {
    id: 45,
    graph_schema: "flow",
    agent_definition_id: "def-1",
    stages: [],
    sub_agents: [],
  };

  beforeEach(() => {
    errorHandlingFetcher.mockResolvedValue({
      nodes: [
        {
          id: "ChatInput-e050b40c",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "ReActAgent-89c5195d",
          type: "ReActAgent",
          position: { x: 100, y: 0 },
          values: {},
        },
        {
          id: "WebTools-6100aca2",
          type: "WebTools",
          position: { x: 150, y: 0 },
          values: { tools: ["web_search", "fetch_webpage"] },
        },
        {
          id: "ChatOutput-808faa0a",
          type: "ChatOutput",
          position: { x: 200, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "ChatInput-e050b40c",
          target: "ReActAgent-89c5195d",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "ReActAgent-89c5195d",
          target: "ChatOutput-808faa0a",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e3",
          source: "WebTools-6100aca2",
          target: "ReActAgent-89c5195d",
          sourceHandle: "output",
          targetHandle: "tools",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });
  });

  afterEach(() => jest.clearAllMocks());

  function toolPacket(
    type: "custom_tool_start" | "custom_tool_delta",
    tool_name: string,
    extra: Record<string, unknown> = {}
  ) {
    return {
      placement: { turn_index: 0, sub_turn_index: null },
      obj: { type, tool_name, ...extra },
    } as any;
  }

  it("embeds tool calls directly inside the calling parent agent without adding a separate trailing step", async () => {
    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "ChatInput-e050b40c"),
      stagePacket("graph_stage_end", "ChatInput-e050b40c"),
      stagePacket("graph_stage_start", "ReActAgent-89c5195d"),
      toolPacket("custom_tool_start", "web_search", { call_id: "c1" }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "c1",
        response_type: "tool_result",
        data: "some output",
      }),
      stagePacket("graph_stage_end", "ReActAgent-89c5195d"),
      stagePacket("graph_stage_start", "ChatOutput-808faa0a"),
      stagePacket("graph_stage_end", "ChatOutput-808faa0a"),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    // Main stage sequence must be strictly the executable workflow nodes
    expect(entries.map(labelOf)).toEqual([
      "Chat Input",
      "ReAct Agent",
      "Chat Output",
    ]);

    // Tool badge is rendered inside ReActAgent
    const toolBadges = screen.getAllByTestId("stage-tool-badge");
    expect(toolBadges.length).toBe(1);
    expect(toolBadges[0]!.textContent).toContain("Web Tools");
  });

  it("renders a standalone resource entry when a tool runs outside of any active graph stage", async () => {
    renderStrip(flowAgent, [
      toolPacket("custom_tool_start", "web_search", { call_id: "c1" }),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools).toBeDefined();
    expect(webTools?.getAttribute("data-status")).toBe("running");
  });

  it("marks standalone resource entry done once its tool_result delta arrives", async () => {
    renderStrip(flowAgent, [
      toolPacket("custom_tool_start", "web_search", { call_id: "c1" }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "c1",
        response_type: "tool_result",
        data: "some output",
      }),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools?.getAttribute("data-status")).toBe("done");
  });

  it("ignores a custom_tool_delta that isn't a tool_result (progress chunk mid-call)", async () => {
    renderStrip(flowAgent, [
      toolPacket("custom_tool_start", "web_search", { call_id: "c1" }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "c1",
        response_type: "progress",
        data: "still working",
      }),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools?.getAttribute("data-status")).toBe("running");
  });

  it("marks the resource node running on search_tool_start (web_search)", async () => {
    renderStrip(flowAgent, [
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: {
          type: "search_tool_start",
          is_internet_search: true,
          call_id: "c1",
        },
      },
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools?.getAttribute("data-status")).toBe("running");
  });

  it("marks the resource node done on search_tool_documents_delta (web_search result)", async () => {
    renderStrip(flowAgent, [
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: {
          type: "search_tool_start",
          is_internet_search: true,
          call_id: "c1",
        },
      },
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: {
          type: "search_tool_documents_delta",
          documents: [],
          call_id: "c1",
        },
      },
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools?.getAttribute("data-status")).toBe("done");
  });

  it("marks the resource node running on open_url_start (fetch_webpage)", async () => {
    renderStrip(flowAgent, [
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: { type: "open_url_start", call_id: "c1" },
      },
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools?.getAttribute("data-status")).toBe("running");
  });

  it("marks the resource node done on open_url_documents (fetch_webpage result)", async () => {
    renderStrip(flowAgent, [
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: { type: "open_url_start", call_id: "c1" },
      },
      {
        placement: { turn_index: 0, sub_turn_index: null },
        obj: { type: "open_url_documents", documents: [], call_id: "c1" },
      },
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    const webTools = entries.find((e) => labelOf(e) === "Web Tools");
    expect(webTools?.getAttribute("data-status")).toBe("done");
  });

  it("attributes replayed tool calls to their respective parent agent nodes (research tools to research, code tools to analysis)", async () => {
    errorHandlingFetcher.mockResolvedValueOnce({
      nodes: [
        {
          id: "node-chat-input",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "node-stage-research",
          type: "Research",
          position: { x: 80, y: 0 },
          values: {},
        },
        {
          id: "node-stage-analysis",
          type: "Analysis",
          position: { x: 160, y: 0 },
          values: {},
        },
        {
          id: "node-web-tools",
          type: "WebTools",
          position: { x: 80, y: 100 },
          values: { tools: ["web_search"] },
        },
        {
          id: "node-code-tools",
          type: "CodeTools",
          position: { x: 160, y: 100 },
          values: { tools: ["execute_python_code"] },
        },
        {
          id: "node-chat-output",
          type: "ChatOutput",
          position: { x: 240, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "node-chat-input",
          target: "node-stage-research",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "node-stage-research",
          target: "node-stage-analysis",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e3",
          source: "node-stage-analysis",
          target: "node-chat-output",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e4",
          source: "node-web-tools",
          target: "node-stage-research",
          sourceHandle: "output",
          targetHandle: "tools",
        },
        {
          id: "e5",
          source: "node-code-tools",
          target: "node-stage-analysis",
          sourceHandle: "output",
          targetHandle: "tools",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });

    renderStrip(flowAgent, [
      // All graph stage events first (as reconstructed from history)
      stagePacket("graph_stage_start", "node-chat-input", 1000),
      stagePacket("graph_stage_end", "node-chat-input", 1010),
      stagePacket("graph_stage_start", "node-stage-research", 1010),
      stagePacket("graph_stage_end", "node-stage-research", 136000),
      stagePacket("graph_stage_start", "node-stage-analysis", 136000),
      stagePacket("graph_stage_end", "node-stage-analysis", 150000),
      stagePacket("graph_stage_start", "node-chat-output", 150000),
      stagePacket("graph_stage_end", "node-chat-output", 150010),
      // Tool events following history reconstruction
      toolPacket("custom_tool_start", "web_search", {
        call_id: "w1",
        timestamp: 5000,
      }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "w1",
        response_type: "tool_result",
        data: "doc",
        timestamp: 6000,
      }),
      toolPacket("custom_tool_start", "execute_python_code", {
        call_id: "c1",
        timestamp: 140000,
      }),
      toolPacket("custom_tool_delta", "execute_python_code", {
        call_id: "c1",
        response_type: "tool_result",
        data: "ans",
        timestamp: 141000,
      }),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    // Main stage sequence must NOT have trailing WebTools or CodeTools after Chat Output
    expect(entries.map(labelOf)).toEqual([
      "Chat Input",
      "Research",
      "Analysis",
      "Chat Output",
    ]);

    // Find badges
    const toolBadges = screen.getAllByTestId("stage-tool-badge");
    expect(toolBadges.length).toBe(2);

    // Verify Research has WebTools
    expect(entries[1]!.textContent).toContain("Research");
    expect(entries[1]!.textContent).toContain("Web Tools");

    // Verify Analysis has CodeTools
    expect(entries[2]!.textContent).toContain("Analysis");
    expect(entries[2]!.textContent).toContain("Code Tools");
  });

  it("attributes a tool to the stage named by the packet's stage_node_id, overriding graph-edge/position guesses", async () => {
    errorHandlingFetcher.mockResolvedValueOnce({
      nodes: [
        {
          id: "node-chat-input",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "agent-a",
          type: "ReActAgent",
          position: { x: 80, y: 0 },
          values: {},
        },
        {
          id: "agent-b",
          type: "ReActAgent",
          position: { x: 160, y: 0 },
          values: {},
        },
        {
          id: "node-web-tools",
          type: "WebTools",
          position: { x: 80, y: 100 },
          values: { tools: ["web_search"] },
        },
        {
          id: "node-chat-output",
          type: "ChatOutput",
          position: { x: 240, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "node-chat-input",
          target: "agent-a",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "agent-a",
          target: "agent-b",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e3",
          source: "agent-b",
          target: "node-chat-output",
          sourceHandle: "output",
          targetHandle: "input",
        },
        // The tool node's edge points at agent-a — the legacy heuristic
        // would attribute the call there.
        {
          id: "e4",
          source: "node-web-tools",
          target: "agent-a",
          sourceHandle: "output",
          targetHandle: "tools",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });

    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "node-chat-input", 1000),
      stagePacket("graph_stage_end", "node-chat-input", 1010),
      stagePacket("graph_stage_start", "agent-a", 1010),
      stagePacket("graph_stage_end", "agent-a", 2000),
      stagePacket("graph_stage_start", "agent-b", 2000),
      stagePacket("graph_stage_end", "agent-b", 3000),
      stagePacket("graph_stage_start", "node-chat-output", 3000),
      stagePacket("graph_stage_end", "node-chat-output", 3010),
      // ...but the backend stamped stage_node_id: "agent-b" on the call.
      toolPacket("custom_tool_start", "web_search", {
        call_id: "w1",
        timestamp: 2500,
        stage_node_id: "agent-b",
      }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "w1",
        response_type: "tool_result",
        data: "doc",
        timestamp: 2700,
        stage_node_id: "agent-b",
      }),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    expect(entries.map(labelOf)).toEqual([
      "Chat Input",
      "ReAct Agent",
      "ReAct Agent",
      "Chat Output",
    ]);

    const toolBadges = screen.getAllByTestId("stage-tool-badge");
    expect(toolBadges.length).toBe(1);
    // agent-b is the 3rd entry (index 2), not agent-a (index 1).
    expect(entries[2]!.textContent).toContain("Web Tools");
    expect(entries[1]!.textContent).not.toContain("Web Tools");
  });

  it("tracks individual per-call durations when a tool is called multiple times", async () => {
    errorHandlingFetcher.mockResolvedValueOnce({
      nodes: [
        {
          id: "node-chat-input",
          type: "ChatInput",
          position: { x: 0, y: 0 },
          values: {},
        },
        {
          id: "node-stage-research",
          type: "Research",
          position: { x: 80, y: 0 },
          values: {},
        },
        {
          id: "node-web-tools",
          type: "WebTools",
          position: { x: 80, y: 100 },
          values: { tools: ["web_search"] },
        },
        {
          id: "node-chat-output",
          type: "ChatOutput",
          position: { x: 160, y: 0 },
          values: {},
        },
      ],
      edges: [
        {
          id: "e1",
          source: "node-chat-input",
          target: "node-stage-research",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e2",
          source: "node-stage-research",
          target: "node-chat-output",
          sourceHandle: "output",
          targetHandle: "input",
        },
        {
          id: "e3",
          source: "node-web-tools",
          target: "node-stage-research",
          sourceHandle: "output",
          targetHandle: "tools",
        },
      ],
      viewport: { x: 0, y: 0, zoom: 1 },
    });

    renderStrip(flowAgent, [
      stagePacket("graph_stage_start", "node-chat-input", 1000),
      stagePacket("graph_stage_end", "node-chat-input", 1010),
      stagePacket("graph_stage_start", "node-stage-research", 1010),
      // 3 separate tool calls during research
      toolPacket("custom_tool_start", "web_search", {
        call_id: "w1",
        timestamp: 2000,
      }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "w1",
        response_type: "tool_result",
        data: "r1",
        timestamp: 2300,
      }),
      toolPacket("custom_tool_start", "web_search", {
        call_id: "w2",
        timestamp: 3000,
      }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "w2",
        response_type: "tool_result",
        data: "r2",
        timestamp: 3500,
      }),
      toolPacket("custom_tool_start", "web_search", {
        call_id: "w3",
        timestamp: 4000,
      }),
      toolPacket("custom_tool_delta", "web_search", {
        call_id: "w3",
        response_type: "tool_result",
        data: "r3",
        timestamp: 4400,
      }),
      stagePacket("graph_stage_end", "node-stage-research", 5000),
      stagePacket("graph_stage_start", "node-chat-output", 5000),
      stagePacket("graph_stage_end", "node-chat-output", 5010),
    ]);

    const entries = await screen.findAllByTestId("stage-entry");
    expect(entries.length).toBe(3);

    const toolBadge = screen.getByTestId("stage-tool-badge");
    expect(toolBadge.textContent).toContain("Web Tools");
    expect(toolBadge.textContent).toContain("3x");
    expect(toolBadge.textContent).toContain("1.20s");

    // Verify hover tooltip breakdown contains each call's distinct duration
    fireEvent.focus(toolBadge);
    expect((await screen.findAllByText("300ms"))[0]).toBeInTheDocument();
    expect((await screen.findAllByText("500ms"))[0]).toBeInTheDocument();
    expect((await screen.findAllByText("400ms"))[0]).toBeInTheDocument();
  });
});
