import type { FullPersona } from "@/app/admin/agents/interfaces";

export interface FlowNode {
  id: string;
  type: string;
  template_version?: number;
  position?: { x: number; y: number };
  values?: Record<string, any>;
}

export interface FlowEdge {
  id: string;
  source: string;
  source_handle: string;
  target: string;
  target_handle: string;
}

export interface FlowSpec {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface FormToFlowOptions {
  toolsByCategory?: Record<string, string[]>;
}

export function formToFlow(
  persona: FullPersona,
  options?: FormToFlowOptions
): FlowSpec {
  const schema = persona.graph_schema || "zero_shot";
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];

  nodes.push({
    id: "node_input",
    type: "ChatInput",
    template_version: 1,
    position: { x: 50, y: 200 },
    values: {},
  });

  nodes.push({
    id: "node_output",
    type: "ChatOutput",
    template_version: 1,
    position: { x: 800, y: 200 },
    values: {},
  });

  nodes.push({
    id: "node_llm",
    type: "LLMModel",
    template_version: 1,
    position: { x: 400, y: 50 },
    values: {
      model: persona.llm_model_version_override || "default",
      provider: persona.llm_model_provider_override || "default",
      temperature: (persona as any).temperature_override ?? 0.7,
    },
  });

  const hasMemory = Boolean(
    persona.long_term_memory ||
      (persona.memory_type && persona.memory_type !== "none")
  );
  if (hasMemory) {
    nodes.push({
      id: "node_memory",
      type: "LongTermMemory",
      template_version: 1,
      position: { x: 100, y: 400 },
      values: {},
    });
  }

  if (schema === "zero_shot") {
    nodes.push({
      id: "node_agent",
      type: "ZeroShotAgent",
      template_version: 1,
      position: { x: 400, y: 200 },
      values: {
        system_prompt: persona.system_prompt || "",
      },
    });

    edges.push(
      {
        id: "e_in_agent",
        source: "node_input",
        source_handle: "message",
        target: "node_agent",
        target_handle: "message",
      },
      {
        id: "e_agent_out",
        source: "node_agent",
        source_handle: "message",
        target: "node_output",
        target_handle: "message",
      },
      {
        id: "e_llm_agent",
        source: "node_llm",
        source_handle: "model",
        target: "node_agent",
        target_handle: "model",
      }
    );
    if (hasMemory) {
      edges.push({
        id: "e_mem_agent",
        source: "node_memory",
        source_handle: "memory",
        target: "node_agent",
        target_handle: "memory",
      });
    }
  } else if (schema === "react") {
    nodes.push({
      id: "node_agent",
      type: "ReActAgent",
      template_version: 1,
      position: { x: 400, y: 200 },
      values: {
        system_prompt: persona.system_prompt || "",
      },
    });

    edges.push(
      {
        id: "e_in_agent",
        source: "node_input",
        source_handle: "message",
        target: "node_agent",
        target_handle: "message",
      },
      {
        id: "e_agent_out",
        source: "node_agent",
        source_handle: "message",
        target: "node_output",
        target_handle: "message",
      },
      {
        id: "e_llm_agent",
        source: "node_llm",
        source_handle: "model",
        target: "node_agent",
        target_handle: "model",
      }
    );
    if (hasMemory) {
      edges.push({
        id: "e_mem_agent",
        source: "node_memory",
        source_handle: "memory",
        target: "node_agent",
        target_handle: "memory",
      });
    }

    const allTools = [
      ...(persona.tools?.map((t) =>
        typeof t === "string" ? t : (t as any).name
      ) || []),
      ...((persona as any).builtin_tools || []),
      ...(persona.mcp_tools || []),
    ].filter(Boolean);

    if (allTools.length > 0) {
      nodes.push({
        id: "node_tools",
        type: "CustomTools",
        template_version: 1,
        position: { x: 400, y: 350 },
        values: { tools: allTools },
      });
      edges.push({
        id: "e_tools_agent",
        source: "node_tools",
        source_handle: "tools",
        target: "node_agent",
        target_handle: "tools",
      });
    }
  } else if (schema === "plan_execute") {
    nodes.push({
      id: "node_agent",
      type: "PlanExecuteAgent",
      template_version: 1,
      position: { x: 400, y: 200 },
      values: {
        system_prompt: persona.system_prompt || "",
      },
    });

    edges.push(
      {
        id: "e_in_agent",
        source: "node_input",
        source_handle: "message",
        target: "node_agent",
        target_handle: "message",
      },
      {
        id: "e_agent_out",
        source: "node_agent",
        source_handle: "message",
        target: "node_output",
        target_handle: "message",
      },
      {
        id: "e_llm_agent",
        source: "node_llm",
        source_handle: "model",
        target: "node_agent",
        target_handle: "model",
      }
    );
    if (hasMemory) {
      edges.push({
        id: "e_mem_agent",
        source: "node_memory",
        source_handle: "memory",
        target: "node_agent",
        target_handle: "memory",
      });
    }

    const allTools = [
      ...(persona.tools?.map((t) =>
        typeof t === "string" ? t : (t as any).name
      ) || []),
      ...((persona as any).builtin_tools || []),
      ...(persona.mcp_tools || []),
    ].filter(Boolean);

    if (allTools.length > 0) {
      nodes.push({
        id: "node_tools",
        type: "CustomTools",
        template_version: 1,
        position: { x: 400, y: 350 },
        values: { tools: allTools },
      });
      edges.push({
        id: "e_tools_agent",
        source: "node_tools",
        source_handle: "tools",
        target: "node_agent",
        target_handle: "tools",
      });
    }
  } else if (schema === "self_reflect") {
    nodes.push({
      id: "node_agent",
      type: "SelfReflectAgent",
      template_version: 1,
      position: { x: 400, y: 200 },
      values: {
        system_prompt: persona.system_prompt || "",
        reflection_prompt: "Reflect on and critique the generated response.",
        max_iterations: persona.max_iterations || 3,
      },
    });

    edges.push(
      {
        id: "e_in_agent",
        source: "node_input",
        source_handle: "message",
        target: "node_agent",
        target_handle: "message",
      },
      {
        id: "e_agent_out",
        source: "node_agent",
        source_handle: "message",
        target: "node_output",
        target_handle: "message",
      },
      {
        id: "e_llm_agent",
        source: "node_llm",
        source_handle: "model",
        target: "node_agent",
        target_handle: "model",
      }
    );
    if (hasMemory) {
      edges.push({
        id: "e_mem_agent",
        source: "node_memory",
        source_handle: "memory",
        target: "node_agent",
        target_handle: "memory",
      });
    }
  } else if (schema === "supervisor") {
    nodes.push({
      id: "node_supervisor",
      type: "Supervisor",
      template_version: 1,
      position: { x: 400, y: 200 },
      values: {
        system_prompt: persona.system_prompt || "",
        sub_agent_ids: persona.sub_agent_ids || [],
      },
    });

    edges.push(
      {
        id: "e_in_sup",
        source: "node_input",
        source_handle: "message",
        target: "node_supervisor",
        target_handle: "input",
      },
      {
        id: "e_sup_out",
        source: "node_supervisor",
        source_handle: "output",
        target: "node_output",
        target_handle: "message",
      },
      {
        id: "e_llm_sup",
        source: "node_llm",
        source_handle: "model",
        target: "node_supervisor",
        target_handle: "model",
      }
    );
    if (hasMemory) {
      edges.push({
        id: "e_mem_sup",
        source: "node_memory",
        source_handle: "memory",
        target: "node_supervisor",
        target_handle: "memory",
      });
    }
  } else if (schema === "pipeline") {
    nodes.push({
      id: "node_pipeline",
      type: "PipelineStage",
      template_version: 1,
      position: { x: 400, y: 200 },
      values: {
        system_prompt: persona.system_prompt || "",
      },
    });

    edges.push(
      {
        id: "e_in_pipe",
        source: "node_input",
        source_handle: "message",
        target: "node_pipeline",
        target_handle: "input",
      },
      {
        id: "e_pipe_out",
        source: "node_pipeline",
        source_handle: "output",
        target: "node_output",
        target_handle: "message",
      },
      {
        id: "e_llm_pipe",
        source: "node_llm",
        source_handle: "model",
        target: "node_pipeline",
        target_handle: "model",
      }
    );
    if (hasMemory) {
      edges.push({
        id: "e_mem_pipe",
        source: "node_memory",
        source_handle: "memory",
        target: "node_pipeline",
        target_handle: "memory",
      });
    }
  }

  return { nodes, edges };
}
