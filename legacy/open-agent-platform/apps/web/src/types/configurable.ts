// The type interface for configuration fields

export type ConfigurableFieldUIType =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "slider"
  | "select"
  | "json";

/**
 * The type interface for options in a select field.
 */
export interface ConfigurableFieldOption {
  label: string;
  value: string;
}

/**
 * The UI configuration for a field in the configurable object.
 */
export type ConfigurableFieldUIMetadata = {
  /**
   * The label of the field. This will be what is rendered in the UI.
   */
  label: string;
  /**
   * The default value to render in the UI component.
   *
   * @default undefined
   */
  default?: unknown;
  /**
   * The type of the field.
   * @default "text"
   */
  type?: ConfigurableFieldUIType;
  /**
   * The description of the field. This will be rendered below the UI component.
   */
  description?: string;
  /**
   * The placeholder of the field. This will be rendered inside the UI component.
   * This is only applicable for text, textarea, number, json, and select fields.
   */
  placeholder?: string;
  /**
   * The options of the field. These will be the options rendered in the select UI component.
   * This is only applicable for select fields.
   */
  options?: ConfigurableFieldOption[];
  /**
   * The minimum value of the field.
   * This is only applicable for number fields.
   */
  min?: number;
  /**
   * The maximum value of the field.
   * This is only applicable for number fields.
   */
  max?: number;
  /**
   * The step value of the field. E.g if using a slider, where you want
   * people to be able to increment by 0.1, you would set this field to 0.1
   * This is only applicable for number fields.
   */
  step?: number;
};

export type ConfigurableFieldMCPMetadata = {
  label: string;
  type: "mcp";
  default?: {
    tools?: string[];
    url?: string;
    auth_required?: boolean;
  };
};

export type ConfigurableFieldRAGMetadata = {
  /**
   * The key in the graph's config schema for the RAG field.
   */
  label: string;
  type: "rag";
  /**
   * When true, only collections that have a knowledge graph built
   * will be shown in the dropdown (used by graph-rag-assistant).
   */
  graph_only?: boolean;
  /**
   * When true, collections that have a knowledge graph built
   * will be EXCLUDED from the dropdown (used by standard rag-assistant).
   */
  rag_only?: boolean;
  default?: {
    rag_url?: string;
    collections?: string[];
  };
};

export type ConfigurableFieldAgentsMetadata = {
  label: string;
  type: "agents";
  default?: {
    agent_id?: string;
    deployment_url?: string;
    name?: string;
  }[];
};

/**
 * Sub-agent definition for flat supervisor (parallel execution)
 */
export interface SubAgentConfig {
  name: string;
  system_prompt: string;
  mcp_tools: string[]; // Array of MCP tool names
  model?: string; // Optional per-agent model override. Falls back to supervisor model if empty.
}

/**
 * Sub-agents configuration for flat supervisor (PARALLEL execution)
 * Each agent runs in parallel, supervisor delegates based on request
 */
export type ConfigurableFieldSubAgentsConfigMetadata = {
  label: string;
  type: "sub_agents_config";
  mcp_url?: string;
  model_options?: Array<{ label: string; value: string }>;
  default?: SubAgentConfig[];
};

/**
 * @deprecated Use ConfigurableFieldSubAgentsConfigMetadata instead
 * Old sub-agents configuration that just selected agent IDs
 */
export type ConfigurableFieldSubAgentsMetadata = {
  label: string;
  type: "sub_agents";
  exclude_self?: boolean;
  default?: string[]; // Array of agent IDs
};

/**
 * Pipeline stage configuration for hierarchy supervisor (SEQUENTIAL execution)
 */
export interface PipelineStage {
  name: string;
  system_prompt: string;
  mcp_tools: string[]; // Array of MCP tool names
  model?: string; // Optional per-stage model override. Falls back to supervisor model if empty.
}

/**
 * Pipeline stages configuration for hierarchy/pipeline supervisor
 * Stages run in SEQUENCE, each stage's output feeds into the next
 */
export type ConfigurableFieldPipelineStagesMetadata = {
  label: string;
  type: "pipeline_stages";
  mcp_url?: string;
  model_options?: Array<{ label: string; value: string }>;
  default?: PipelineStage[];
};
