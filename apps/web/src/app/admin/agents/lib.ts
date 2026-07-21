import {
  MinimalPersonaSnapshot,
  Persona,
  StarterMessage,
} from "@/app/admin/agents/interfaces";

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
  // RAG collection config
  rag_config?: {
    document_processing: string[];
    knowledge_graph: string[];
    display_names?: Record<string, string>;
  };
  long_term_memory?: boolean;
}

function buildPersonaUpsertRequest({
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
    rag_config: rag_config ?? null,
    long_term_memory: long_term_memory ?? false,
  };
}

export async function uploadFile(file: File): Promise<string | null> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/admin/persona/upload-image", {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!response.ok) {
    console.error("Failed to upload file");
    return null;
  }

  const responseJson = await response.json();
  return responseJson.file_id;
}

export async function createPersona(
  personaUpsertParams: PersonaUpsertParameters
): Promise<Response | null> {
  const createPersonaResponse = await fetch("/api/persona", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(buildPersonaUpsertRequest(personaUpsertParams)),
    credentials: "include",
  });

  return createPersonaResponse;
}

export async function updatePersona(
  id: number,
  personaUpsertParams: PersonaUpsertParameters
): Promise<Response | null> {
  const updatePersonaResponse = await fetch(`/api/persona/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(buildPersonaUpsertRequest(personaUpsertParams)),
    credentials: "include",
  });

  return updatePersonaResponse;
}

export function deletePersona(personaId: number) {
  return fetch(`/api/persona/${personaId}`, {
    method: "DELETE",
    credentials: "include",
  });
}

function smallerNumberFirstComparator(a: number, b: number) {
  return a > b ? 1 : -1;
}

function closerToZeroNegativesFirstComparator(a: number, b: number) {
  if (a < 0 && b > 0) {
    return -1;
  }
  if (a > 0 && b < 0) {
    return 1;
  }

  const absA = Math.abs(a);
  const absB = Math.abs(b);

  if (absA === absB) {
    return a > b ? 1 : -1;
  }

  return absA > absB ? 1 : -1;
}

export function personaComparator(
  a: MinimalPersonaSnapshot | Persona,
  b: MinimalPersonaSnapshot | Persona
) {
  if (a.display_priority === null && b.display_priority === null) {
    return closerToZeroNegativesFirstComparator(a.id, b.id);
  }

  if (a.display_priority !== b.display_priority) {
    if (a.display_priority === null) {
      return 1;
    }
    if (b.display_priority === null) {
      return -1;
    }

    return smallerNumberFirstComparator(a.display_priority, b.display_priority);
  }

  return closerToZeroNegativesFirstComparator(a.id, b.id);
}

export async function togglePersonaFeatured(
  personaId: number,
  featured: boolean
) {
  const response = await fetch(`/api/admin/persona/${personaId}/featured`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      featured: !featured,
    }),
    credentials: "include",
  });
  return response;
}

export async function togglePersonaVisibility(
  personaId: number,
  isVisible: boolean
) {
  const response = await fetch(`/api/admin/persona/${personaId}/visible`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      is_visible: !isVisible,
    }),
    credentials: "include",
  });
  return response;
}
