import { ValidSources } from "@/lib/types";
import { ToolSnapshot } from "@/lib/tools/interfaces";
import { DocumentSetSummary, MinimalUserSnapshot } from "@/lib/types";

export type AgentId = number | string;

// Represents a hierarchy node (folder, space, channel, etc.) attached to a persona
export interface HierarchyNodeSnapshot {
  id: number;
  raw_node_id: string;
  display_name: string;
  link: string | null;
  source: ValidSources;
  node_type: string; // HierarchyNodeType enum value
}

// Represents a document attached to a persona
export interface AttachedDocumentSnapshot {
  id: string;
  title: string;
  link: string | null;
  parent_id: number | null;
  last_modified: string | null;
  last_synced: string | null;
  source: ValidSources | null;
}

export interface StarterMessageBase {
  message: string;
}

export interface StarterMessage extends StarterMessageBase {
  name: string;
}

export interface MinimalPersonaSnapshot {
  id: number;
  external_id?: string | null;
  is_dynamic?: boolean;
  graph_schema?: string | null;
  stages?: Array<Record<string, unknown>>;
  sub_agents?: Array<Record<string, unknown>>;
  sub_agent_ids?: string[];
  brain_type?: string | null;
  mcp_tools?: string[];
  mcp_tool_configs?: Record<string, Record<string, string>>;
  name: string;
  description: string;
  tools: ToolSnapshot[];
  starter_messages: StarterMessage[] | null;
  document_sets: DocumentSetSummary[];
  // Counts for knowledge sources (used to determine if search tool should be enabled)
  hierarchy_node_count?: number;
  attached_document_count?: number;
  // Unique sources from all knowledge (document sets + hierarchy nodes)
  // Used to populate source filters in chat
  knowledge_sources?: ValidSources[];
  llm_model_version_override?: string;
  llm_model_provider_override?: string;
  availability?: AgentAvailability;
  memory_type?: string | null;
  long_term_memory?: boolean;

  uploaded_image_id?: string;
  icon_name?: string;

  is_public: boolean;
  is_visible: boolean;
  display_priority: number | null;
  featured: boolean;
  builtin_persona: boolean;

  labels?: PersonaLabel[];
  owner: MinimalUserSnapshot | null;
}

export interface Persona extends MinimalPersonaSnapshot {
  user_file_ids: string[];
  users: MinimalUserSnapshot[];
  groups: number[];
  // Hierarchy nodes (folders, spaces, channels) attached for scoped search
  hierarchy_nodes?: HierarchyNodeSnapshot[];
  // Individual documents attached for scoped search
  attached_documents?: AttachedDocumentSnapshot[];

  // Embedded prompt fields on persona
  system_prompt: string | null;
  replace_base_system_prompt: boolean;
  task_prompt: string | null;
  datetime_aware: boolean;

  base_agent?: string;
  mcp_tools?: string[];
  rag_config?: {
    document_processing: string[];
    knowledge_graph: string[];
    display_names?: Record<string, string>;
  };
  sub_agents?: Array<Record<string, unknown>>;
  sub_agent_ids?: string[];
  supervisor_prompt?: string | null;
  stages?: Array<Record<string, unknown>>;
  pipeline_prompt?: string | null;
  reflection_prompt?: string | null;
  max_iterations?: number;
}

export interface FullPersona extends Persona {
  search_start_date: string | null;
}

export interface DynamicAgentDefinition {
  id: string;
  persona_id?: number | null;
  name: string;
  agent_type: string;
  description: string | null;
  graph_schema: string;
  brain_type: string;
  memory_type: string;
  system_prompt: string | null;
  model: string | null;
  mcp_tools: string[];
  mcp_tool_configs?: Record<string, Record<string, string>>;
  rag_config?: {
    document_processing: string[];
    knowledge_graph: string[];
    display_names?: Record<string, string>;
  };
  sub_agents: Array<Record<string, unknown>>;
  sub_agent_ids: string[];
  supervisor_prompt: string | null;
  stages: Array<Record<string, unknown>>;
  pipeline_prompt: string | null;
  reflection_prompt: string | null;
  max_iterations: number;
  version: string;
  tags: string[];
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface PersonaLabel {
  id: number;
  name: string;
}

export interface AgentAvailabilityCheck {
  component: "model" | "memory" | "mcp_tool" | "rag" | "graph_rag";
  status: "ok" | "warning" | "error";
  message: string;
}

export interface AgentAvailability {
  status: "available" | "degraded" | "unavailable";
  checks?: AgentAvailabilityCheck[];
}
