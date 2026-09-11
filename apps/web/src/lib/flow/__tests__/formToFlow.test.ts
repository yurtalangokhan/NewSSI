import { formToFlow, type FlowNode, type FlowEdge } from "../formToFlow";
import type { FullPersona } from "@/app/admin/agents/interfaces";

const basePersona: any = {
  id: 1,
  name: "Test Agent",
  description: "Description",
  system_prompt: "You are a helpful assistant",
  base_agent: "dynamic-agent",
  graph_schema: "zero_shot",
  agent_definition_id: "11111111-1111-1111-1111-111111111111",
  tools: [],
  builtin_tools: [],
  is_public: true,
  shared_user_ids: [],
  shared_group_ids: [],
  document_sets: [],
  starter_messages: [],
  llm_model_version_override: "gpt-4o",
  llm_model_provider_override: "openai",
  temperature_override: 0.5,
  search_type: undefined,
  num_chunks: undefined,
  include_citations: true,
  apply_agentic_search: false,
  agentic_search_depth: undefined,
  prompt_template: undefined,
  labels: [],
  users: [],
  groups: [],
  is_visible: true,
  display_priority: undefined,
  remove_thinking: false,
  reasoning_effort: undefined,
  max_iterations: undefined,
  sub_agents: [],
  brain_type: "react",
  tool_calling_strategy: "native",
  memory_type: "none",
  parallel_tool_calling_depth: undefined,
  tool_timeout_seconds: undefined,
  custom_avatar_color: undefined,
  icon_name: undefined,
};

describe("Task 51 — formToFlow conversion", () => {
  it("51.1 — zero_shot converts to minimal flow with ZeroShotAgent and LLMModel", () => {
    const spec = formToFlow({ ...basePersona, graph_schema: "zero_shot" });
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("ZeroShotAgent");
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("LLMModel");
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("ChatInput");
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("ChatOutput");
    expect(spec.edges.length).toBe(3);
  });

  it("51.2 — react converts with tools node when tools present", () => {
    const spec = formToFlow({
      ...basePersona,
      graph_schema: "react",
      builtin_tools: ["web_search"],
      mcp_tools: ["git_status"],
    });
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("ReActAgent");
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("CustomTools");
    const toolsNode = spec.nodes.find(
      (n: FlowNode) => n.type === "CustomTools"
    );
    expect(toolsNode?.values?.tools).toEqual(["web_search", "git_status"]);
  });

  it("51.3 — plan_execute converts with tools node", () => {
    const spec = formToFlow({
      ...basePersona,
      graph_schema: "plan_execute",
      builtin_tools: ["calculator"],
    });
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain(
      "PlanExecuteAgent"
    );
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("CustomTools");
  });

  it("51.4 — self_reflect converts with reflection_prompt and max_iterations", () => {
    const spec = formToFlow({
      ...basePersona,
      graph_schema: "self_reflect",
      max_iterations: 5,
    });
    const agentNode = spec.nodes.find(
      (n: FlowNode) => n.type === "SelfReflectAgent"
    );
    expect(agentNode).toBeDefined();
    expect(agentNode?.values?.max_iterations).toBe(5);
    expect(agentNode?.values?.reflection_prompt).toBeDefined();
  });

  it("51.5 — supervisor converts to Supervisor node", () => {
    const spec = formToFlow({
      ...basePersona,
      graph_schema: "supervisor",
      sub_agent_ids: ["agent-1", "agent-2"],
    });
    const supNode = spec.nodes.find((n: FlowNode) => n.type === "Supervisor");
    expect(supNode).toBeDefined();
    expect(supNode?.values?.sub_agent_ids).toEqual(["agent-1", "agent-2"]);
  });

  it("51.6 — pipeline converts to PipelineStage node", () => {
    const spec = formToFlow({ ...basePersona, graph_schema: "pipeline" });
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("PipelineStage");
  });

  it("51.8 — conversion never mutates the source persona object", () => {
    const persona = { ...basePersona, graph_schema: "zero_shot" };
    const original = JSON.parse(JSON.stringify(persona));
    formToFlow(persona);
    expect(persona).toEqual(original);
  });

  it("51.10 — memory_type none produces no memory node", () => {
    const spec = formToFlow({
      ...basePersona,
      memory_type: "none",
      long_term_memory: false,
    });
    expect(spec.nodes.map((n: FlowNode) => n.type)).not.toContain(
      "LongTermMemory"
    );
  });

  it("51.11 — long_term_memory true produces LongTermMemory node and edge", () => {
    const spec = formToFlow({ ...basePersona, long_term_memory: true });
    expect(spec.nodes.map((n: FlowNode) => n.type)).toContain("LongTermMemory");
    expect(spec.edges.some((e: FlowEdge) => e.target_handle === "memory")).toBe(
      true
    );
  });
});
