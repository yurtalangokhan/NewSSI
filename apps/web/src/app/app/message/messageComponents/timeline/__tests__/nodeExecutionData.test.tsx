import { Packet, PacketType } from "@/app/app/services/streamingModels";
import type { CanvasNode } from "@/components/flow-canvas/types/flow";
import { buildNodeExecutionData } from "../nodeExecutionData";

describe("buildNodeExecutionData", () => {
  const mockNodes: CanvasNode[] = [
    {
      id: "node-research",
      type: "templateNode",
      position: { x: 0, y: 0 },
      data: {
        type: "SequentialStage",
        templateVersion: 1,
        values: { stage_name: "ResearchStage" },
      },
    },
    {
      id: "node-react",
      type: "templateNode",
      position: { x: 200, y: 0 },
      data: {
        type: "ReActAgent",
        templateVersion: 1,
        values: {},
      },
    },
    {
      id: "node-web-tools",
      type: "templateNode",
      position: { x: 0, y: 100 },
      data: {
        type: "WebTools",
        templateVersion: 1,
        values: { tools: ["web_search"] },
      },
    },
  ];

  it("returns empty object when no packets are provided", () => {
    expect(buildNodeExecutionData([], [], mockNodes, [])).toEqual({});
  });

  it("extracts thinking, tools, and outputs for flow stages", () => {
    const packets: Packet[] = [
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-research#1",
          node_id: "node-research",
          label: "ResearchStage",
          iteration: 1,
          timestamp: 1000,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.REASONING_START,
          reasoning: "Araştırma adımı başladı. ",
          timestamp: 1050,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.REASONING_DELTA,
          reasoning: "Web üzerinden arama yapacağım.",
          timestamp: 1100,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.CUSTOM_TOOL_START,
          tool_name: "web_search",
          call_id: "call-1",
          args: { query: "AI 2026" },
          timestamp: 1200,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.CUSTOM_TOOL_DELTA,
          tool_name: "web_search",
          call_id: "call-1",
          data: "5 sonuç bulundu",
          timestamp: 1500,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_OUTPUT_DELTA,
          stage_key: "node-research#1",
          content: "++ARAŞTIRMA BRİFİNGİ++",
          timestamp: 1600,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-research#1",
          status: "done",
          duration_ms: 600,
          timestamp: 1600,
        },
      } as any,
    ];

    const result = buildNodeExecutionData(packets, [], mockNodes, []);

    expect(result["node-research"]).toBeDefined();
    const nodeData = result["node-research"]!;
    expect(nodeData.status).toBe("done");
    expect(nodeData.durationMs).toBe(600);
    expect(nodeData.thinking).toBe(
      "Araştırma adımı başladı. Web üzerinden arama yapacağım."
    );
    expect(nodeData.output).toBe("++ARAŞTIRMA BRİFİNGİ++");
    expect(nodeData.tools.length).toBe(1);
    expect(nodeData.tools[0]!.toolName).toBe("web_search");
    expect(nodeData.tools[0]!.invocations.length).toBe(1);
    expect(nodeData.tools[0]!.invocations[0]!.input).toEqual({
      query: "AI 2026",
    });
    expect(nodeData.tools[0]!.invocations[0]!.output).toBe("5 sonuç bulundu");
  });

  it("handles multiple iterations in loops", () => {
    const packets: Packet[] = [
      {
        placement: { turn_index: 0, stage_key: "node-react#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-react#1",
          node_id: "node-react",
          iteration: 1,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-react#1" },
        obj: {
          type: PacketType.FLOW_STAGE_OUTPUT_DELTA,
          stage_key: "node-react#1",
          content: "Taslak 1",
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-react#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-react#1",
          status: "done",
          duration_ms: 300,
        },
      } as any,
      {
        placement: { turn_index: 1, stage_key: "node-react#2" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-react#2",
          node_id: "node-react",
          iteration: 2,
        },
      } as any,
      {
        placement: { turn_index: 1, stage_key: "node-react#2" },
        obj: {
          type: PacketType.FLOW_STAGE_OUTPUT_DELTA,
          stage_key: "node-react#2",
          content: "Taslak 2 Son",
        },
      } as any,
      {
        placement: { turn_index: 1, stage_key: "node-react#2" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-react#2",
          status: "done",
          duration_ms: 400,
        },
      } as any,
    ];

    const result = buildNodeExecutionData(packets, [], mockNodes, []);
    const nodeData = result["node-react"]!;
    expect(nodeData).toBeDefined();
    expect(nodeData.iterations).toBeDefined();
    expect(nodeData.iterations!.length).toBe(2);
    expect(nodeData.iterations![0]!.iteration).toBe(1);
    expect(nodeData.iterations![0]!.output).toBe("Taslak 1");
    expect(nodeData.iterations![1]!.iteration).toBe(2);
    expect(nodeData.iterations![1]!.output).toBe("Taslak 2 Son");
  });
  it("groups search tool start, queries delta, and docs delta into a single invocation", () => {
    const packets: Packet[] = [
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-research#1",
          node_id: "node-research",
          label: "ResearchStage",
          iteration: 1,
          timestamp: 1000,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.SEARCH_TOOL_START,
          call_id: "search-call-1",
          timestamp: 1100,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.SEARCH_TOOL_QUERIES_DELTA,
          call_id: "search-call-1",
          queries: ["llama 3 context window"],
          timestamp: 1150,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.SEARCH_TOOL_DOCUMENTS_DELTA,
          call_id: "search-call-1",
          documents: [{ title: "Doc 1" }, { title: "Doc 2" }],
          timestamp: 1300,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-research#1",
          status: "done",
          duration_ms: 400,
          timestamp: 1400,
        },
      } as any,
    ];

    const result = buildNodeExecutionData(packets, [], mockNodes, []);
    const research = result["node-research"]!;
    expect(research.tools.length).toBe(1);
    expect(research.tools[0]!.callCount).toBe(1);
    expect(research.tools[0]!.invocations.length).toBe(1);
    expect(research.tools[0]!.invocations[0]!.callId).toBe("search-call-1");
    expect(research.tools[0]!.invocations[0]!.status).toBe("done");
    expect(research.tools[0]!.invocations[0]!.output).toBe("2 kaynak bulundu");

    // Check resource node WebTools
    const webTools = result["node-web-tools"]!;
    expect(webTools).toBeDefined();
    expect(webTools.status).toBe("done");
    expect(webTools.tools.length).toBe(1);
    expect(webTools.tools[0]!.callCount).toBe(1);
    expect(webTools.tools[0]!.invocations.length).toBe(1);
  });

  it("deduplicates identical reasoning start and delta chunks in a node", () => {
    const packets: Packet[] = [
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-research#1",
          node_id: "node-research",
          iteration: 1,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.REASONING_START,
          reasoning: "Thinking about query.",
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.REASONING_DELTA,
          reasoning: "Thinking about query.", // duplicate delta
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.REASONING_DELTA,
          reasoning: " Next thought.",
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-research#1",
          status: "done",
        },
      } as any,
    ];

    const result = buildNodeExecutionData(packets, [], mockNodes, []);
    expect(result["node-research"]!.thinking).toBe(
      "Thinking about query. Next thought."
    );
  });

  it("correctly resolves execution data for sanitized chat scenario with WebTools and ReAct nodes", () => {
    const chatNodes: CanvasNode[] = [
      { id: "node-stage-research", data: { label: "Research Stage" } } as any,
      { id: "node-stage-analysis", data: { label: "Analysis Stage" } } as any,
      { id: "node-react-executor", data: { label: "ReAct Agent" } } as any,
      { id: "node-web-tools", data: { label: "Web Search" } } as any,
      { id: "node-code-tools", data: { label: "Code Execution" } } as any,
    ];
    const chatEdges: any[] = [
      {
        id: "e1",
        source: "node-stage-research",
        target: "node-web-tools",
      } as any,
      {
        id: "e2",
        source: "node-stage-analysis",
        target: "node-code-tools",
      } as any,
    ];

    const packets: Packet[] = [
      // Stage 1: Research (5 web searches, 1 thinking)
      {
        placement: { turn_index: 0, stage_key: "node-stage-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-stage-research#1",
          node_id: "node-stage-research",
          iteration: 1,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-stage-research#1" },
        obj: { type: PacketType.REASONING_START },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-stage-research#1" },
        obj: {
          type: PacketType.REASONING_DELTA,
          reasoning: "Researching models...",
        },
      } as any,
      ...[1, 2, 3, 4, 5].flatMap((i) => [
        {
          placement: { turn_index: 0, stage_key: "node-stage-research#1" },
          obj: {
            type: PacketType.SEARCH_TOOL_START,
            tool_call_id: `call-web-${i}`,
            query: `search query ${i}`,
          },
        } as any,
        {
          placement: { turn_index: 0, stage_key: "node-stage-research#1" },
          obj: {
            type: PacketType.SEARCH_TOOL_QUERIES_DELTA,
            tool_call_id: `call-web-${i}`,
            queries: [`query ${i}`],
          },
        } as any,
        {
          placement: { turn_index: 0, stage_key: "node-stage-research#1" },
          obj: {
            type: PacketType.SEARCH_TOOL_DOCUMENTS_DELTA,
            tool_call_id: `call-web-${i}`,
            documents: [{ title: `doc ${i}` }],
          },
        } as any,
      ]),
      {
        placement: { turn_index: 0, stage_key: "node-stage-research#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-stage-research#1",
          status: "done",
          duration_ms: 1200,
        },
      } as any,

      // Stage 2: Analysis (4 python runs, 1 thinking)
      {
        placement: { turn_index: 0, stage_key: "node-stage-analysis#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-stage-analysis#1",
          node_id: "node-stage-analysis",
          iteration: 1,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-stage-analysis#1" },
        obj: { type: PacketType.REASONING_START },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-stage-analysis#1" },
        obj: {
          type: PacketType.REASONING_DELTA,
          reasoning: "Analyzing data with python...",
        },
      } as any,
      ...[1, 2, 3, 4].flatMap((i) => [
        {
          placement: { turn_index: 0, stage_key: "node-stage-analysis#1" },
          obj: {
            type: PacketType.CUSTOM_TOOL_START,
            tool_name: "run_python",
            call_id: `call-py-${i}`,
            input: { code: `print(${i})` },
          },
        } as any,
        {
          placement: { turn_index: 0, stage_key: "node-stage-analysis#1" },
          obj: {
            type: PacketType.CUSTOM_TOOL_DELTA,
            call_id: `call-py-${i}`,
            output: `result ${i}`,
          },
        } as any,
      ]),
      {
        placement: { turn_index: 0, stage_key: "node-stage-analysis#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-stage-analysis#1",
          status: "done",
          duration_ms: 800,
        },
      } as any,

      // Stage 3: ReAct Executor (No thinking, output only)
      {
        placement: { turn_index: 0, stage_key: "node-react-executor#1" },
        obj: {
          type: PacketType.FLOW_STAGE_START,
          stage_key: "node-react-executor#1",
          node_id: "node-react-executor",
          iteration: 1,
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-react-executor#1" },
        obj: {
          type: PacketType.FLOW_STAGE_OUTPUT_DELTA,
          stage_key: "node-react-executor#1",
          content: "<<TASLAK_TAMAM>>",
        },
      } as any,
      {
        placement: { turn_index: 0, stage_key: "node-react-executor#1" },
        obj: {
          type: PacketType.FLOW_STAGE_END,
          stage_key: "node-react-executor#1",
          status: "done",
          duration_ms: 100,
        },
      } as any,
    ];

    const result = buildNodeExecutionData(packets, [], chatNodes, chatEdges);

    // Research Stage: 5 tools, not 15
    const researchData = result["node-stage-research"]!;
    expect(researchData).toBeDefined();
    expect(researchData!.tools.length).toBe(1);
    expect(researchData!.tools[0]!.invocations.length).toBe(5);
    expect(researchData!.thinking).toBe("Researching models...");
    expect(researchData!.status).toBe("done");

    // Analysis Stage: 4 tools
    const analysisData = result["node-stage-analysis"]!;
    expect(analysisData).toBeDefined();
    expect(analysisData!.tools.length).toBe(1);
    expect(analysisData!.tools[0]!.invocations.length).toBe(4);
    expect(analysisData!.thinking).toBe("Analyzing data with python...");
    expect(analysisData!.status).toBe("done");

    // ReAct Executor: NO thinking leaked from prior stages!
    const reactData = result["node-react-executor"]!;
    expect(reactData).toBeDefined();
    expect(reactData!.thinking).toBeUndefined();
    expect(reactData!.tools.length).toBe(0);
    expect(reactData!.output).toBe("<<TASLAK_TAMAM>>");
    expect(reactData!.status).toBe("done");

    // Web Tools resource node: marked done, not stuck in running
    const webToolsData = result["node-web-tools"]!;
    expect(webToolsData).toBeDefined();
    expect(webToolsData!.status).toBe("done");
    expect(webToolsData!.tools[0]!.invocations.length).toBe(5);

    // Code Tools resource node: marked done, not stuck in running
    const codeToolsData = result["node-code-tools"]!;
    expect(codeToolsData).toBeDefined();
    expect(codeToolsData!.status).toBe("done");
    expect(codeToolsData!.tools[0]!.invocations.length).toBe(4);
  });

  it("accumulates live message_delta output and streaming reasoning/tools while stage is running", () => {
    const packets: Packet[] = [];
    const flowNodes = [
      {
        id: "node-agent-1",
        type: "agent",
        data: { type: "agent", values: { stage_name: "Writer" } },
      } as any,
    ];

    // 1. Stage starts
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: {
        type: PacketType.FLOW_STAGE_START,
        stage_key: "node-agent-1#1",
        node_id: "node-agent-1",
        iteration: 1,
      },
    } as any);

    let data = buildNodeExecutionData(packets, [], flowNodes, []);
    expect(data["node-agent-1"]).toBeDefined();
    expect(data["node-agent-1"]!.status).toBe("running");

    // 2. Reasoning streams
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: { type: PacketType.REASONING_START },
    } as any);
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: {
        type: PacketType.REASONING_DELTA,
        reasoning: "Thinking about the prompt...",
      },
    } as any);

    data = buildNodeExecutionData(packets, [], flowNodes, []);
    expect(data["node-agent-1"]!.thinking).toBe("Thinking about the prompt...");

    // 3. Tool call starts and finishes
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: {
        type: PacketType.CUSTOM_TOOL_START,
        tool_name: "lookup",
        call_id: "c1",
        input: { q: "foo" },
      },
    } as any);

    data = buildNodeExecutionData(packets, [], flowNodes, []);
    expect(data["node-agent-1"]!.tools[0]!.status).toBe("running");

    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: {
        type: PacketType.CUSTOM_TOOL_DELTA,
        tool_name: "lookup",
        call_id: "c1",
        output: "bar",
      },
    } as any);

    data = buildNodeExecutionData(packets, [], flowNodes, []);
    expect(data["node-agent-1"]!.tools[0]!.status).toBe("done");
    expect(data["node-agent-1"]!.tools[0]!.invocations[0]!.output).toBe("bar");

    // 4. Output streams live via message_delta
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: { type: PacketType.MESSAGE_DELTA, content: "Hello, " },
    } as any);
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: { type: PacketType.MESSAGE_DELTA, content: "world!" },
    } as any);

    data = buildNodeExecutionData(packets, [], flowNodes, []);
    expect(data["node-agent-1"]!.output).toBe("Hello, world!");
    expect(data["node-agent-1"]!.status).toBe("running");

    // 5. Stage ends
    packets.push({
      placement: { turn_index: 0, stage_key: "node-agent-1#1" },
      obj: {
        type: PacketType.FLOW_STAGE_END,
        stage_key: "node-agent-1#1",
        status: "done",
        duration_ms: 1500,
      },
    } as any);

    data = buildNodeExecutionData(packets, [], flowNodes, []);
    expect(data["node-agent-1"]!.status).toBe("done");
    expect(data["node-agent-1"]!.durationMs).toBe(1500);
    expect(data["node-agent-1"]!.output).toBe("Hello, world!");
    expect(data["node-agent-1"]!.thinking).toBe("Thinking about the prompt...");
  });
});
