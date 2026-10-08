import { StarterMessage } from "@/lib/api/domains/agents/types";
interface PersonaUpsertRequest {
  name: string;
  description: string;
  system_prompt: string;
  task_prompt: string;
  datetime_aware: boolean;
  document_set_ids: number[];
  is_public: boolean;
  llm_model_provider_override: string | null;
  llm_model_version_override: string | null;
  starter_messages: StarterMessage[] | null;
  users?: string[];
  groups: number[];
  tool_ids: number[];
  remove_image?: boolean;
  uploaded_image_id: string | null;
  icon_name: string | null;
  search_start_date: Date | null;
  featured: boolean;
  display_priority: number | null;
  label_ids: number[] | null;
  user_file_ids: string[] | null;
  replace_base_system_prompt: boolean;
  base_agent: string | null;
  graph_schema: string;
  brain_type: string;
  memory_type: string;
  sub_agent_ids: string[];
  sub_agents: Array<Record<string, unknown>>;
  supervisor_prompt: string | null;
  stages: Array<Record<string, unknown>>;
  pipeline_prompt: string | null;
  reflection_prompt: string | null;
  max_iterations: number;
  mcp_tools: string[];
  mcp_tool_configs: Record<string, unknown>;
  connector_bindings: Array<{
    datasource_id: string;
    operations: string[];
  }>;
  // Hierarchy nodes (folders, spaces, channels) for scoped search
  hierarchy_node_ids: number[];
  // Individual documents for scoped search
  document_ids: string[];
  rag_config?: {
    document_processing: string[];
    knowledge_graph: string[];
    display_names?: Record<string, string>;
  } | null;
  long_term_memory?: boolean;
}

export interface PersonaUpsertParameters {
  name: string;
  description: string;
  system_prompt: string;
  replace_base_system_prompt: boolean;
  task_prompt: string;
  datetime_aware: boolean;
  document_set_ids: number[];
  is_public: boolean;
  llm_model_provider_override: string | null;
  llm_model_version_override: string | null;
  starter_messages: StarterMessage[] | null;
  users?: string[];
  groups: number[];
  tool_ids: number[];
  remove_image?: boolean;
  search_start_date: Date | null;
  uploaded_image_id: string | null;
  icon_name: string | null;
  featured: boolean;
  label_ids: number[] | null;
  user_file_ids: string[];
  // Hierarchy nodes (folders, spaces, channels) for scoped search
  hierarchy_node_ids?: number[];
  // Individual documents for scoped search
  document_ids?: string[];
  // Base agent selection (chatbot, configurable-mcp-agent)
  base_agent?: string | null;
  graph_schema?: string;
  brain_type?: string;
  memory_type?: string;
  sub_agent_ids?: string[];
  sub_agents?: Array<Record<string, unknown>>;
  supervisor_prompt?: string | null;
  stages?: Array<Record<string, unknown>>;
  pipeline_prompt?: string | null;
  reflection_prompt?: string | null;
  max_iterations?: number;
  // MCP tool names to bind to the agent
  mcp_tools?: string[];
  // MCP tool-specific configuration references. Secrets are never included here.
  mcp_tool_configs?: Record<string, unknown>;
  connector_bindings?: Array<{
    datasource_id: string;
    operations: string[];
  }>;
  // RAG collection config
  rag_config?: {
    document_processing: string[];
    knowledge_graph: string[];
    display_names?: Record<string, string>;
  };
  long_term_memory?: boolean;
}

export function buildPersonaUpsertRequest({
  name,
  description,
  system_prompt,
  task_prompt,
  document_set_ids,
  is_public,
  groups,
  datetime_aware,
  users,
  tool_ids,
  remove_image,
  search_start_date,
  user_file_ids,
  hierarchy_node_ids,
  document_ids,
  icon_name,
  uploaded_image_id,
  featured,
  llm_model_provider_override,
  llm_model_version_override,
  starter_messages,
  label_ids,
  replace_base_system_prompt,
  base_agent,
  graph_schema,
  brain_type,
  memory_type,
  sub_agent_ids,
  sub_agents,
  supervisor_prompt,
  stages,
  pipeline_prompt,
  reflection_prompt,
  max_iterations,
  mcp_tools,
  mcp_tool_configs,
  connector_bindings,
  rag_config,
  long_term_memory,
}: PersonaUpsertParameters): PersonaUpsertRequest {
  return {
    name,
    description,
    system_prompt,
    task_prompt,
    document_set_ids,
    is_public,
    uploaded_image_id,
    icon_name,
    groups,
    users,
    tool_ids,
    remove_image,
    search_start_date,
    datetime_aware,
    featured: featured ?? false,
    llm_model_provider_override: llm_model_provider_override ?? null,
    llm_model_version_override: llm_model_version_override ?? null,
    starter_messages: starter_messages ?? null,
    display_priority: null,
    label_ids: label_ids ?? null,
    user_file_ids: user_file_ids ?? null,
    replace_base_system_prompt,
    hierarchy_node_ids: hierarchy_node_ids ?? [],
    document_ids: document_ids ?? [],
    base_agent: base_agent ?? null,
    graph_schema: graph_schema ?? "zero_shot",
    brain_type: brain_type ?? "llm",
    memory_type: memory_type ?? "none",
    sub_agent_ids: sub_agent_ids ?? [],
    sub_agents: sub_agents ?? [],
    supervisor_prompt: supervisor_prompt ?? null,
    stages: stages ?? [],
    pipeline_prompt: pipeline_prompt ?? null,
    reflection_prompt: reflection_prompt ?? null,
    max_iterations: max_iterations ?? 3,
    mcp_tools: mcp_tools ?? [],
    mcp_tool_configs: mcp_tool_configs ?? {},
    connector_bindings: connector_bindings ?? [],
    rag_config: rag_config ?? null,
    long_term_memory: long_term_memory ?? false,
  };
}
