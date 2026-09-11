"use client";

import { useState, useRef, useCallback, useMemo, useEffect } from "react";
import dynamicImport from "next/dynamic";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslation } from "react-i18next";

// @xyflow/react and the zustand store it drives have no meaningful
// server-rendered state (R3). InlineFlowDesigner is the create-time-only
// canvas (flow selected but no definition id exists yet); once a flow
// definition exists, editing happens in the full-screen studio route
// (/app/flows/[definitionId]) instead, so FlowAgentEditorPage is not
// dynamically imported here any more (P4→flow-separation).
import { InlineFlowDesignerSkeleton } from "@/refresh-components/skeletons/FlowStudioSkeleton";

const InlineFlowDesigner = dynamicImport(
  () => import("@/components/flow-canvas/InlineFlowDesigner"),
  {
    ssr: false,
    loading: () => <InlineFlowDesignerSkeleton />,
  }
);
import { useStore } from "zustand";
import { createFlowStore } from "@/components/flow-canvas/stores/flowStore";
import { toFlowSpec } from "@/components/flow-canvas/utils/compile";
import { getChatNodePresence } from "@/components/flow-canvas/utils/chatNodePresence";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import * as GeneralLayouts from "@/layouts/general-layouts";
import Button from "@/refresh-components/buttons/Button";
import { FullPersona } from "@/app/admin/agents/interfaces";
import { Formik, Form } from "formik";
import * as Yup from "yup";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import InputSelectField from "@/refresh-components/form/InputSelectField";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputDatePickerField from "@/refresh-components/form/InputDatePickerField";
import Message from "@/refresh-components/messages/Message";
import Separator from "@/refresh-components/Separator";
import * as InputLayouts from "@/layouts/input-layouts";
import { useFormikContext } from "formik";
import LLMSelector from "@/components/llm/LLMSelector";
import { parseLlmDescriptor, structureValue } from "@/lib/llmConfig/utils";
import { useAvailableModels } from "@/hooks/useAvailableModels";
import {
  MAX_STARTER_MESSAGES,
  MAX_CHARACTERS_STARTER_MESSAGE,
  MAX_CHARACTERS_AGENT_DESCRIPTION,
} from "@/lib/constants";
import { SEARCH_TOOL_ID } from "@/app/app/components/tools/constants";
import Text from "@/refresh-components/texts/Text";
import { Card } from "@/refresh-components/cards";
import SimpleCollapsible from "@/refresh-components/SimpleCollapsible";
import AgentEditorSkeleton from "@/refresh-components/skeletons/AgentEditorSkeleton";
import SwitchField from "@/refresh-components/form/SwitchField";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import { toast } from "@/hooks/useToast";
import {
  SvgInfo,
  SvgLock,
  SvgNetworkGraph,
  SvgOnyxOctagon,
  SvgUsers,
  SvgTrash,
} from "@opal/icons";
import AgentIconPicker from "@/refresh-components/agents/AgentIconPicker";
import StarterMessagesField from "@/refresh-components/agents/StarterMessagesField";
import AgentVisibilityFields from "@/refresh-components/agents/AgentVisibilityFields";
import { useAgents } from "@/hooks/useAgents";
import { useCompositionCatalog } from "@/hooks/useCompositionCatalog";
import {
  createPersona,
  uploadFile,
  updatePersona,
  PersonaUpsertParameters,
} from "@/app/admin/agents/lib";
import { buildMcpToolConfigs, useMailConfigs } from "@/lib/mailConfigs";
import useMcpServersForAgentEditor from "@/hooks/useMcpServersForAgentEditor";
import useOpenApiTools from "@/hooks/useOpenApiTools";
import { useAvailableTools } from "@/hooks/useAvailableTools";
import useBuiltInTools from "@/hooks/useBuiltInTools";
import {
  parseToolCategory,
  groupToolsByCategory,
  buildCategoryLabelMap,
} from "@/lib/tools/builtInToolUtils";
import _ from "lodash";
import { getActionIcon } from "@/lib/tools/mcpUtils";
import { deleteAgent } from "@/lib/agents";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import ShareAgentModal from "@/sections/modals/ShareAgentModal";
import AgentKnowledgePane from "@/sections/knowledge/AgentKnowledgePane";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { useUser } from "@/providers/UserProvider";
import GraphSchemaPreview from "@/refresh-pages/GraphSchemaPreview";
import Modal from "@/refresh-components/Modal";
import { motion, AnimatePresence } from "motion/react";
import { cn } from "@/lib/utils";
import SubAgentSelector, {
  SubAgentConfiguration,
} from "@/refresh-components/agents/SubAgentSelector";
import CompositionValidator from "@/refresh-components/agents/CompositionValidator";
import McpToolSelectionCard, {
  buildMcpOnlyToolSelectionGroups,
  buildToolSelectionGroups,
} from "@/refresh-components/agents/McpToolSelectionCard";
import { flowApi } from "@/components/flow-canvas/api/flowApi";
import useConnectorToolOptions, {
  ConnectorBinding,
} from "@/hooks/useConnectorToolOptions";
import ConnectorBindingsField from "@/refresh-components/agents/ConnectorBindingsField";

interface AgentIconEditorProps {
  existingAgent?: FullPersona | null;
}

/** Thin Formik-bound wrapper around AgentIconPicker (extracted so the flow
 * creation modal can reuse the same picker without a Formik context). */
function AgentIconEditor({ existingAgent }: AgentIconEditorProps) {
  const { values, setFieldValue } = useFormikContext<{
    name: string;
    icon_name: string | null;
    uploaded_image_id: string | null;
    remove_image: boolean | null;
  }>();

  // Falls back to the existing agent's own image until the user picks
  // something new or explicitly clears it (icon_name set, or remove_image
  // set by picking the default icon) — same rule the inline version used.
  const uploadedImageId =
    values.uploaded_image_id ??
    (values.icon_name || values.remove_image
      ? null
      : existingAgent?.uploaded_image_id ?? null);

  return (
    <AgentIconPicker
      name={values.name}
      value={{ uploadedImageId, iconName: values.icon_name }}
      onChange={(next) => {
        setFieldValue("uploaded_image_id", next.uploadedImageId);
        setFieldValue("icon_name", next.iconName);
        // A new upload clears remove_image; picking an icon (or the
        // default) is a clear, so it re-sets it — mirrors the original
        // handleImageUpload/handleIconClick split exactly.
        setFieldValue("remove_image", next.uploadedImageId === null);
      }}
    />
  );
}

/** Thin Formik-bound wrapper around StarterMessagesField. */
function StarterMessages() {
  const { values, setFieldValue } = useFormikContext<{
    starter_messages: string[];
  }>();

  return (
    <StarterMessagesField
      value={values.starter_messages || []}
      onChange={(next) => setFieldValue("starter_messages", next)}
    />
  );
}

function ConnectorBindingsCompatibilityGuard() {
  const { values, setFieldValue } = useFormikContext<{
    base_agent: string;
    connector_bindings: ConnectorBinding[];
  }>();

  useEffect(() => {
    if (
      values.base_agent !== "configurable-mcp-agent" &&
      values.connector_bindings.length > 0
    ) {
      void setFieldValue("connector_bindings", []);
    }
  }, [setFieldValue, values.base_agent, values.connector_bindings.length]);

  return null;
}

export interface AgentEditorPageProps {
  agent?: FullPersona;
  refreshAgent?: () => void;
}

const GRAPH_SCHEMA_CAPABILITIES: Record<
  string,
  { supports_tools: boolean; supports_rag: boolean }
> = {
  zero_shot: { supports_tools: false, supports_rag: false },
  react: { supports_tools: true, supports_rag: true },
  supervisor: { supports_tools: false, supports_rag: false },
  pipeline: { supports_tools: true, supports_rag: true },
  plan_execute: { supports_tools: true, supports_rag: true },
  self_reflect: { supports_tools: false, supports_rag: false },
  // Tools/RAG for a flow are configured per-node on the canvas, not at
  // the persona/definition level — hide those sections here.
  flow: { supports_tools: false, supports_rag: false },
};

function normalizeCompositionConfig(
  config: SubAgentConfiguration,
  fallbackName: string
) {
  const role = config.role?.trim() || config.name?.trim() || fallbackName;

  return {
    agent_id: config.agent_id,
    name: role,
    role,
    system_prompt: config.system_prompt?.trim() || "You are a helpful agent.",
    mcp_tools: config.mcp_tools ?? [],
    model: config.model ?? null,
  };
}

/** Saves whatever InlineFlowDesigner had drawn as this agent's flow draft.
 * A brand-new agent (`isNewAgent`) has no separate "work in progress"
 * concept — the create page has no Publish button or version history
 * (those only exist in FlowAgentEditorPage, reachable once the agent
 * already exists) — so its first draft is published immediately too, the
 * same way a classic agent's config goes live on create.
 *
 * The create page pre-validates the flow server-side (see
 * `validateInlineFlow`) before the persona is ever created, so a failed
 * publish here is unexpected — surface it by throwing rather than
 * swallowing it, so the caller can tell the user the flow needs attention. */
export async function saveInitialFlow(
  agentDefinitionId: string,
  isNewAgent: boolean,
  flowSpec: unknown
): Promise<void> {
  await fetch(flowApi.draft(agentDefinitionId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flow_spec: flowSpec }),
  });

  if (!isNewAgent) return;

  const res = await fetch(flowApi.publish(agentDefinitionId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      `Failed to auto-publish new agent's initial flow (${res.status}): ${detail}`
    );
  }
}

type FlowValidationIssue = {
  code: string;
  message: string;
  node_id?: string | null;
  edge_id?: string | null;
};

/** Server-side flow validation, run before the persona is created so an
 * invalid flow (missing Chat Input / Chat Output, incompatible edges, …)
 * blocks agent creation entirely instead of leaving an orphan draft-only
 * agent behind. Mirrors the gate the edit page's Publish button applies. */
export async function validateInlineFlow(
  flowSpec: unknown
): Promise<{ valid: boolean; errors: FlowValidationIssue[] }> {
  try {
    const res = await fetch(flowApi.validate(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ flow_spec: flowSpec }),
    });
    if (!res.ok) {
      return {
        valid: false,
        errors: [
          {
            code: "FLOW_VALIDATE_REQUEST_FAILED",
            message: await res.text().catch(() => `HTTP ${res.status}`),
          },
        ],
      };
    }
    const body = (await res.json()) as {
      valid: boolean;
      errors?: FlowValidationIssue[];
    };
    return { valid: body.valid, errors: body.errors ?? [] };
  } catch (err) {
    return {
      valid: false,
      errors: [
        {
          code: "FLOW_VALIDATE_REQUEST_FAILED",
          message: err instanceof Error ? err.message : String(err),
        },
      ],
    };
  }
}

export default function AgentEditorPage({
  agent: existingAgent,
  refreshAgent,
}: AgentEditorPageProps) {
  const router = useRouter();
  const { refresh: refreshAgents } = useAgents();
  const shareAgentModal = useCreateModal();
  const deleteAgentModal = useCreateModal();
  const [isGraphPreviewOpen, setIsGraphPreviewOpen] = useState(false);
  const [compositionDepth, setCompositionDepth] = useState(0);
  const [collectionDisplayNames, setCollectionDisplayNames] = useState<
    Record<string, string>
  >({});
  const settings = useSettingsContext();
  const { isAdmin, isCurator } = useUser();
  const { t } = useTranslation();
  // Tracks whether the async tool data has finished loading at least once.
  // Declared with the other top-level hooks (never after an early return) so
  // the hook order stays stable across the Form/Flow tab switch.
  const hasLoadedInitialData = useRef(false);
  const optionalLabel = t("common.optional");
  const optionalTag = ` (${optionalLabel})`;
  const canUpdateFeaturedStatus = isAdmin || isCurator;
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;

  const {
    graphStrategies,
    brains,
    isLoading: catalogLoading,
  } = useCompositionCatalog();

  const GRAPH_SCHEMA_OPTIONS = useMemo(() => {
    const labelMap: Record<string, string> = {
      zero_shot: t("agentEditor.strategyZeroShot"),
      react: t("agentEditor.strategyReAct"),
      supervisor: t("agentEditor.strategySupervisor"),
      pipeline: t("agentEditor.strategyPipeline"),
      plan_and_execute: t("agentEditor.strategyPlanExecute"),
      self_reflect: t("agentEditor.strategySelfReflect"),
      flow: t("agentEditor.strategyFlow", "Visual Flow (Beta)"),
    };
    return graphStrategies.map((s) => ({
      value: s.key,
      label: labelMap[s.key] ?? s.key,
      available: s.available,
    }));
  }, [graphStrategies, t]);

  const BRAIN_TYPE_OPTIONS = useMemo(() => {
    const labelMap: Record<string, string> = {
      standard_model: t("agentEditor.typeLLM"),
      guard: t("agentEditor.typeGuard"),
      multi_model: t("agentEditor.typeMultiModel"),
    };
    return brains.map((b) => ({
      value: b.key,
      label: labelMap[b.key] ?? b.key,
      available: b.available,
    }));
  }, [brains, t]);

  const MEMORY_TYPE_OPTIONS = useMemo(
    () => [
      { value: "none", label: t("agentEditor.memoryNone"), available: true },
      {
        value: "long_term",
        label: t("agentEditor.memoryLongTerm"),
        available: true,
      },
      {
        value: "buffer",
        label: t("agentEditor.memoryBuffer"),
        available: false,
      },
    ],
    [t]
  );

  // LLM Model Selection
  const getCurrentLlm = useCallback(
    (values: any, llmProviders: any) =>
      values.llm_model_version_override && values.llm_model_provider_override
        ? (() => {
            const provider = llmProviders?.find(
              (p: any) => p.name === values.llm_model_provider_override
            );
            return structureValue(
              values.llm_model_provider_override,
              provider?.provider || "",
              values.llm_model_version_override
            );
          })()
        : null,
    []
  );

  const onLlmSelect = useCallback(
    (selected: string | null, setFieldValue: any) => {
      if (selected === null) {
        setFieldValue("llm_model_version_override", null);
        setFieldValue("llm_model_provider_override", null);
      } else {
        const { modelName, name } = parseLlmDescriptor(selected);
        if (modelName && name) {
          setFieldValue("llm_model_version_override", modelName);
          setFieldValue("llm_model_provider_override", name);
        }
      }
    },
    []
  );

  const { mcpData, isLoading: isMcpLoading } = useMcpServersForAgentEditor();
  const { openApiTools: openApiToolsRaw, isLoading: isOpenApiLoading } =
    useOpenApiTools();
  const { llmProviders } = useAvailableModels();
  const mcpServers = mcpData?.mcp_servers ?? [];
  const openApiTools = openApiToolsRaw ?? [];

  // Check if the *BUILT-IN* tools are available.
  // The built-in tools are:
  // - image-gen
  // - web-search
  // - code-interpreter
  const { tools: availableTools, isLoading: isToolsLoading } =
    useAvailableTools();

  // Fetch built-in tools from tools-service MCP
  const { tools: builtInTools, isLoading: isBuiltInToolsLoading } =
    useBuiltInTools();
  const { mailConfigs, isLoading: isMailConfigsLoading } = useMailConfigs();
  const {
    options: connectorToolOptions,
    error: connectorToolOptionsError,
    isLoading: isConnectorToolOptionsLoading,
  } = useConnectorToolOptions();
  const searchTool = availableTools?.find(
    (t) => t.in_code_tool_id === SEARCH_TOOL_ID
  );

  // Group MCP server tools from availableTools by server ID.
  // `name` is the selection identity (qualified for external MCP tools);
  // `displayLabel` is the raw name shown in the UI.
  const mcpServersWithTools = useMemo(() => {
    return mcpServers.map((server) => {
      const serverTools = (availableTools || [])
        .filter((tool) => tool.mcp_server_id === server.id)
        .map((tool) => ({
          id: tool.id.toString(),
          icon: getActionIcon(server.server_url, server.name),
          name: tool.qualified_name || tool.name,
          displayLabel: tool.display_name || tool.name,
          description: tool.description,
          isAvailable: true,
          isEnabled: tool.enabled,
        }));

      return { server, tools: serverTools, isLoading: false };
    });
  }, [availableTools, mcpServers]);

  const allMcpTools = useMemo(() => {
    return mcpServersWithTools.flatMap(({ tools }) => tools);
  }, [mcpServersWithTools]);

  // Transform built-in tools for the form (parse and clean category tags)
  const allBuiltInTools = useMemo(() => {
    return builtInTools
      .filter(
        (tool) =>
          !["connector_list_resources", "connector_read"].includes(tool.name)
      )
      .map((tool) => {
        const parsed = parseToolCategory({
          name: tool.name,
          description: tool.description || "",
          input_schema: tool.input_schema || {},
        });
        return {
          name: tool.name,
          display_name: parsed.title || _.startCase(tool.name),
          description: parsed.description,
          input_schema: parsed.input_schema,
          category: parsed.category,
          categoryLabel: parsed.categoryLabel,
          isAvailable: true,
          isEnabled: false,
        };
      });
  }, [builtInTools]);

  const builtInToolsByCategory = useMemo(
    () =>
      groupToolsByCategory(allBuiltInTools) as Record<
        string,
        (typeof allBuiltInTools)[number][]
      >,
    [allBuiltInTools]
  );

  const builtInCategoryLabelMap = useMemo(
    () => buildCategoryLabelMap(allBuiltInTools),
    [allBuiltInTools]
  );
  const toolSelectionGroups = useMemo(() => {
    const serverGroups = buildMcpOnlyToolSelectionGroups({
      tools: mcpServersWithTools.flatMap(({ server, tools }) =>
        tools.map((tool) => ({
          id: tool.id,
          name: tool.name,
          display_name: tool.displayLabel,
          description: tool.description,
          mcp_server_id: server.id,
          isAvailable: tool.isAvailable,
          enabled: tool.isEnabled,
        }))
      ),
      mcpServers,
    });
    const builtInCategoryGroups = buildToolSelectionGroups({
      serviceToolsByCategory: builtInToolsByCategory,
      categoryLabelMap: builtInCategoryLabelMap,
    });
    const builtInRoot = builtInCategoryGroups.length
      ? [
          {
            id: "builtin-root",
            title: t("agentEditor.builtInToolsGroup", "Built-in Tools"),
            kind: "builtin-root" as const,
            children: builtInCategoryGroups,
          },
        ]
      : [];
    return [...serverGroups, ...builtInRoot];
  }, [
    builtInCategoryLabelMap,
    builtInToolsByCategory,
    mcpServers,
    mcpServersWithTools,
    t,
  ]);

  const initialValues = useMemo(
    () => ({
      // General
      icon_name: existingAgent?.icon_name ?? null,
      uploaded_image_id: existingAgent?.uploaded_image_id ?? null,
      remove_image: false,
      name: existingAgent?.name ?? "",
      description: existingAgent?.description ?? "",

      // Base Agent Selection (only for custom agents - not built-in)
      base_agent: existingAgent?.base_agent ?? "chatbot",
      connector_bindings: existingAgent?.connector_bindings ?? [],
      graph_schema: existingAgent?.graph_schema ?? "zero_shot",
      brain_type: (existingAgent as any)?.brain_type ?? "llm",
      memory_type: (existingAgent as any)?.memory_type ?? "none",
      long_term_memory: existingAgent?.long_term_memory ?? false,
      sub_agent_ids: (existingAgent as any)?.sub_agent_ids ?? [], // NEW: Sub-agent references
      sub_agents: ((existingAgent as any)?.sub_agents ??
        []) as SubAgentConfiguration[],
      stages: ((existingAgent as any)?.stages ?? []) as SubAgentConfiguration[],

      // Prompts
      instructions: existingAgent?.system_prompt ?? "",
      starter_messages: Array.from(
        { length: MAX_STARTER_MESSAGES },
        (_, i) => existingAgent?.starter_messages?.[i]?.message ?? ""
      ),

      // Knowledge - enabled if agent has any RAG collections selected
      enable_knowledge:
        (existingAgent?.rag_config?.document_processing?.length ?? 0) > 0 ||
        (existingAgent?.rag_config?.knowledge_graph?.length ?? 0) > 0,
      rag_document_collection_ids:
        existingAgent?.rag_config?.document_processing ?? [],
      rag_graph_collection_ids:
        existingAgent?.rag_config?.knowledge_graph ?? [],

      // Advanced
      llm_model_provider_override:
        existingAgent?.llm_model_provider_override ?? null,
      llm_model_version_override:
        existingAgent?.llm_model_version_override ?? null,
      knowledge_cutoff_date: existingAgent?.search_start_date
        ? new Date(existingAgent.search_start_date)
        : null,
      replace_base_system_prompt:
        existingAgent?.replace_base_system_prompt ?? false,
      reminders: existingAgent?.task_prompt ?? "",
      image_generation: false,
      web_search: false,
      open_url: false,
      code_interpreter: false,
      send_email_mail_config_id:
        existingAgent?.mcp_tool_configs?.send_email?.mail_config_id ?? "",
      // MCP tools - dynamically add fields for each tool (from MCP servers)
      ...Object.fromEntries(
        allMcpTools.map((tool) => [
          `mcp_tool_${tool.name}`,
          existingAgent?.mcp_tools?.includes(tool.name) ?? false,
        ])
      ),
      // Built-in tools from tools-service - dynamically add fields for each tool
      ...Object.fromEntries(
        allBuiltInTools.map((tool) => [
          `builtin_tool_${tool.name}`,
          existingAgent?.mcp_tools?.includes(tool.name) ?? false,
        ])
      ),

      // MCP servers - dynamically add fields for each server with nested tool fields
      ...Object.fromEntries(
        mcpServersWithTools.map(({ server, tools }) => {
          // Find all tools from existingAgent that belong to this MCP server
          const serverToolsFromAgent =
            existingAgent?.tools?.filter(
              (tool) => tool.mcp_server_id === server.id
            ) ?? [];

          // Build the tool field object with tool_{id} for ALL available tools
          const toolFields: Record<string, boolean> = {};
          tools.forEach((tool) => {
            // Set to true if this tool was enabled in existingAgent, false otherwise
            toolFields[`tool_${tool.id}`] = serverToolsFromAgent.some(
              (t) => t.id === Number(tool.id)
            );
          });

          return [
            `mcp_server_${server.id}`,
            {
              enabled: serverToolsFromAgent.length > 0, // Server is enabled if it has any tools
              ...toolFields, // Add individual tool states for ALL tools
            },
          ];
        })
      ),

      // OpenAPI tools - add a boolean field for each tool
      ...Object.fromEntries(
        openApiTools.map((openApiTool) => [
          `openapi_tool_${openApiTool.id}`,
          existingAgent?.tools?.some((t) => t.id === openApiTool.id) ?? false,
        ])
      ),

      // Sharing
      shared_user_ids: existingAgent?.users?.map((user) => user.id) ?? [],
      shared_group_ids: existingAgent?.groups ?? [],
      is_public: existingAgent?.is_public ?? true,
      label_ids: existingAgent?.labels?.map((l) => l.id) ?? [],
      featured: existingAgent?.featured ?? false,
    }),
    [
      allBuiltInTools,
      allMcpTools,
      existingAgent,
      mcpServersWithTools,
      openApiTools,
    ]
  );

  const validationSchema = Yup.object().shape({
    // General
    icon_name: Yup.string().nullable(),
    remove_image: Yup.boolean().optional(),
    uploaded_image_id: Yup.string().nullable(),
    name: Yup.string().required(t("agentEditor.agentNameRequired")),
    description: Yup.string()
      .max(
        MAX_CHARACTERS_AGENT_DESCRIPTION,
        t("agentEditor.descriptionMaxChars", {
          count: MAX_CHARACTERS_AGENT_DESCRIPTION,
        })
      )
      .optional(),

    // Base Agent (only for custom agents)
    base_agent: Yup.string().oneOf([
      "chatbot",
      "configurable-mcp-agent",
      "dynamic-agent",
    ]),
    // Accepts whatever the composition catalog advertises (so a strategy the
    // backend adds needs no change here) plus the legacy aliases the editor
    // still normalizes, and "flow", which is compiled from a flow_spec.
    graph_schema: Yup.string().oneOf([
      ...GRAPH_SCHEMA_OPTIONS.map((option) => option.value),
      "zero_shot",
      "react",
      "supervisor",
      "pipeline",
      "plan_execute",
      "plan_and_execute",
      "self_reflect",
      "flow",
    ]),
    brain_type: Yup.string().oneOf([
      ...BRAIN_TYPE_OPTIONS.map((option) => option.value),
      "llm",
      "standard_model",
      "guard",
      "multi_model",
    ]),
    memory_type: Yup.string().oneOf(
      MEMORY_TYPE_OPTIONS.map((option) => option.value)
    ),
    long_term_memory: Yup.boolean(),
    connector_bindings: Yup.array().of(
      Yup.object({
        datasource_id: Yup.string().required(),
        operations: Yup.array()
          .of(Yup.string().oneOf(["list_resources", "read"]))
          .min(1)
          .required(),
      })
    ),
    sub_agent_ids: Yup.array().of(Yup.string()).optional(), // NEW: Sub-agent references
    sub_agents: Yup.array()
      .of(
        Yup.object({
          agent_id: Yup.string().required(),
          name: Yup.string().required(),
          role: Yup.string().required(t("agentEditor.subAgentRoleRequired")),
          system_prompt: Yup.string().required(
            t("agentEditor.subAgentInstructionRequired")
          ),
          mcp_tools: Yup.array().of(Yup.string()),
          model: Yup.string().nullable(),
        })
      )
      .optional(),
    stages: Yup.array()
      .of(
        Yup.object({
          agent_id: Yup.string().required(),
          name: Yup.string().required(),
          role: Yup.string().required(t("agentEditor.subAgentRoleRequired")),
          system_prompt: Yup.string().required(
            t("agentEditor.subAgentInstructionRequired")
          ),
          mcp_tools: Yup.array().of(Yup.string()),
          model: Yup.string().nullable(),
        })
      )
      .optional(),

    // Prompts
    instructions: Yup.string().optional(),
    starter_messages: Yup.array().of(
      Yup.string().max(
        MAX_CHARACTERS_STARTER_MESSAGE,
        t("agentEditor.starterMaxChars", {
          count: MAX_CHARACTERS_STARTER_MESSAGE,
        })
      )
    ),

    // Knowledge
    enable_knowledge: Yup.boolean(),
    rag_document_collection_ids: Yup.array().of(Yup.string()),
    rag_graph_collection_ids: Yup.array().of(Yup.string()),

    // Advanced
    llm_model_provider_override: Yup.string().nullable().optional(),
    llm_model_version_override: Yup.string().nullable().optional(),
    knowledge_cutoff_date: Yup.date().nullable().optional(),
    replace_base_system_prompt: Yup.boolean(),
    reminders: Yup.string().optional(),

    // Built-in tools
    image_generation: Yup.boolean().optional(),
    web_search: Yup.boolean().optional(),
    open_url: Yup.boolean().optional(),
    code_interpreter: Yup.boolean().optional(),
    send_email_mail_config_id: Yup.string().optional(),

    // MCP tools (from external MCP servers)
    ...Object.fromEntries(
      allMcpTools.map((tool) => [
        `mcp_tool_${tool.name}`,
        Yup.boolean().optional(),
      ])
    ),

    // Built-in tools from tools-service
    ...Object.fromEntries(
      allBuiltInTools.map((tool) => [
        `builtin_tool_${tool.name}`,
        Yup.boolean().optional(),
      ])
    ),

    // OpenAPI tools
    ...Object.fromEntries(
      openApiTools.map((tool) => [
        `openapi_tool_${tool.id}`,
        Yup.boolean().optional(),
      ])
    ),
  });

  async function handleSubmit(values: typeof initialValues) {
    try {
      // Map conversation starters
      const starterMessages = values.starter_messages
        .filter((message: string) => message.trim() !== "")
        .map((message: string) => ({
          message: message,
          name: message,
        }));

      // Send null instead of empty array if no starter messages
      const finalStarterMessages =
        starterMessages.length > 0 ? starterMessages : null;

      // Always look up tools in availableTools to ensure we can find all tools

      const toolIds = [];
      if (values.enable_knowledge) {
        if (vectorDbEnabled && searchTool) {
          toolIds.push(searchTool.id);
        }
      }
      // Collect enabled MCP tool IDs
      mcpServers.forEach((server) => {
        const serverFieldName = `mcp_server_${server.id}`;
        const serverData = (values as any)[serverFieldName];

        if (
          serverData &&
          typeof serverData === "object" &&
          serverData.enabled
        ) {
          // Server is enabled, collect all enabled tools
          Object.keys(serverData).forEach((key) => {
            if (key.startsWith("tool_") && serverData[key] === true) {
              // Extract tool ID from key (e.g., "tool_123" -> 123)
              const toolId = parseInt(key.replace("tool_", ""), 10);
              if (!isNaN(toolId)) {
                toolIds.push(toolId);
              }
            }
          });
        }
      });

      // Collect enabled OpenAPI tool IDs
      openApiTools.forEach((openApiTool) => {
        const toolFieldName = `openapi_tool_${openApiTool.id}`;
        if ((values as any)[toolFieldName] === true) {
          toolIds.push(openApiTool.id);
        }
      });

      // Collect enabled MCP tool names (for backend - separate from tool_ids)
      const enabledMcpToolNames: string[] = [];

      allMcpTools.forEach((tool) => {
        if ((values as any)[`mcp_tool_${tool.name}`] === true) {
          enabledMcpToolNames.push(tool.name);
        }
      });

      // Collect enabled built-in tools from tools-service
      allBuiltInTools.forEach((tool) => {
        if ((values as any)[`builtin_tool_${tool.name}`] === true) {
          enabledMcpToolNames.push(tool.name);
        }
      });

      // Safeguard: Preserve existing agent's tools if they were not displayed in the current form
      // (e.g. if an MCP server or tools-service is temporarily unreachable during edit)
      if (existingAgent?.mcp_tools) {
        const knownFormToolNames = new Set([
          ...allMcpTools.map((t) => t.name),
          ...allBuiltInTools.map((t) => t.name),
        ]);
        existingAgent.mcp_tools.forEach((toolName) => {
          if (!knownFormToolNames.has(toolName)) {
            enabledMcpToolNames.push(toolName);
          }
        });
      }

      const dedupedMcpToolNames = Array.from(new Set(enabledMcpToolNames));
      let mcpToolConfigs;
      try {
        mcpToolConfigs = buildMcpToolConfigs(
          dedupedMcpToolNames,
          values.send_email_mail_config_id
        );
      } catch {
        toast.error(
          t(
            "agentEditor.sendEmailMailConfigRequired",
            "Select a mail config before enabling send_email."
          )
        );
        return;
      }

      // Build rag_config from selected collections
      const hasKnowledge =
        values.enable_knowledge &&
        (values.rag_document_collection_ids.length > 0 ||
          values.rag_graph_collection_ids.length > 0);

      const ragConfig = hasKnowledge
        ? (() => {
            const selectedCollectionIds = [
              ...values.rag_document_collection_ids,
              ...values.rag_graph_collection_ids,
            ];
            return {
              document_processing: values.rag_document_collection_ids,
              knowledge_graph: values.rag_graph_collection_ids,
              display_names: Object.fromEntries(
                selectedCollectionIds
                  .map((id) => [id, collectionDisplayNames[id]])
                  .filter((entry): entry is [string, string] =>
                    Boolean(entry[1])
                  )
              ),
            };
          })()
        : undefined;

      const hasTools = dedupedMcpToolNames.length > 0 || toolIds.length > 0;

      // Auto-promote base_agent when knowledge or tools are enabled
      const effectiveBaseAgent =
        (hasKnowledge || hasTools) && values.base_agent === "chatbot"
          ? "configurable-mcp-agent"
          : values.base_agent || "chatbot";

      // Build submission data
      const rawGraphSchema =
        values.graph_schema === "zero_shot" &&
        (dedupedMcpToolNames.length > 0 || hasKnowledge)
          ? "react"
          : values.graph_schema;
      const dynamicGraphSchema =
        rawGraphSchema === "plan_and_execute" ? "plan_execute" : rawGraphSchema;
      const dynamicSubAgents =
        values.base_agent === "dynamic-agent" &&
        dynamicGraphSchema === "supervisor"
          ? values.sub_agents.map((config, index) =>
              normalizeCompositionConfig(config, `specialist_${index + 1}`)
            )
          : [];
      const dynamicStages =
        values.base_agent === "dynamic-agent" &&
        dynamicGraphSchema === "pipeline"
          ? values.stages.map((config, index) =>
              normalizeCompositionConfig(config, `stage_${index + 1}`)
            )
          : [];
      const submissionData: PersonaUpsertParameters = {
        name: values.name,
        description: values.description,
        document_set_ids: [],
        is_public: values.is_public,
        llm_model_provider_override: values.llm_model_provider_override || null,
        llm_model_version_override: values.llm_model_version_override || null,
        starter_messages: finalStarterMessages,
        users: values.shared_user_ids,
        groups: values.shared_group_ids,
        tool_ids: toolIds,
        // uploaded_image: null, // Already uploaded separately
        remove_image: values.remove_image ?? false,
        uploaded_image_id: values.uploaded_image_id,
        icon_name: values.icon_name,
        search_start_date: values.knowledge_cutoff_date || null,
        label_ids: values.label_ids,
        featured: values.featured,

        user_file_ids: [],
        hierarchy_node_ids: [],
        document_ids: [],
        rag_config: ragConfig,

        system_prompt: values.instructions,
        replace_base_system_prompt: values.replace_base_system_prompt,
        task_prompt: values.reminders || "",
        datetime_aware: false,

        // Base agent and MCP tools for custom agents
        base_agent: effectiveBaseAgent,
        graph_schema: dynamicGraphSchema,
        brain_type:
          values.brain_type === "standard_model" ? "llm" : values.brain_type,
        memory_type: values.memory_type,
        sub_agent_ids: values.sub_agent_ids, // NEW: Sub-agent references
        sub_agents: dynamicSubAgents,
        supervisor_prompt: null,
        stages: dynamicStages,
        pipeline_prompt: null,
        reflection_prompt: null,
        max_iterations: 3,
        mcp_tools: dedupedMcpToolNames,
        mcp_tool_configs: mcpToolConfigs,
        connector_bindings:
          effectiveBaseAgent === "configurable-mcp-agent"
            ? values.connector_bindings
            : [],
        long_term_memory: values.long_term_memory,
      };

      // Block creating a flow agent whose canvas can't be published — the
      // same server-side validation the edit page's Publish button runs,
      // done before createPersona so an invalid flow leaves no orphan
      // agent behind. Only the create path is gated; a not-yet-flow-backed
      // existing agent may still save an incomplete draft and publish it
      // later from FlowAgentEditorPage.
      if (!existingAgent && dynamicGraphSchema === "flow") {
        const { nodes, edges, viewport } = inlineFlowStore.getState();
        const { valid, errors } = await validateInlineFlow(
          toFlowSpec(nodes, edges, viewport)
        );
        if (!valid) {
          const issues =
            errors.map((issue) => issue.message).join(" • ") ||
            t("agentEditor.flowMissingChatNodes", {
              nodes: `${t("agentEditor.flowChatInputNode")}, ${t(
                "agentEditor.flowChatOutputNode"
              )}`,
            });
          toast.error(t("agentEditor.flowValidationFailed", { issues }));
          return;
        }
      }

      // Call API
      let personaResponse;
      if (!!existingAgent) {
        personaResponse = await updatePersona(existingAgent.id, submissionData);
      } else {
        personaResponse = await createPersona(submissionData);
      }

      // Handle response
      if (!personaResponse || !personaResponse.ok) {
        const error = personaResponse
          ? await personaResponse.text()
          : t("agentEditor.noResponseReceived");
        toast.error(
          `${t("agentEditor.failedToAgent", {
            action: existingAgent
              ? t("agentEditor.actionUpdate")
              : t("agentEditor.actionCreate"),
          })} - ${error}`
        );
        return;
      }

      // Success
      const agent = await personaResponse.json();
      toast.success(
        `${t("agentEditor.agentSuccess", {
          name: agent.name,
          action: existingAgent
            ? t("agentEditor.actionUpdated")
            : t("agentEditor.actionCreated"),
        })}`
      );

      // InlineFlowDesigner has no agent_definition_id to save to until the
      // persona above exists — this is that first save, so whatever the
      // user drew before hitting Save doesn't open to an empty canvas next
      // time (matches the Convert-to-Flow button's own draft PUT).
      if (dynamicGraphSchema === "flow" && agent.agent_definition_id) {
        const { nodes, edges, viewport } = inlineFlowStore.getState();
        try {
          await saveInitialFlow(
            agent.agent_definition_id,
            !existingAgent,
            toFlowSpec(nodes, edges, viewport)
          );
        } catch (err) {
          console.error("Failed to save flow draft:", err);
          toast.error(
            t("agentEditor.flowValidationFailed", {
              issues: err instanceof Error ? err.message : String(err),
            })
          );
        }
      }

      // Refresh agents list and the specific agent
      await refreshAgents();
      if (refreshAgent) {
        refreshAgent();
      }

      router.push("/admin/agents");
    } catch (error) {
      console.error("Submit error:", error);
      toast.error(`${t("agentEditor.anErrorOccurred")}: ${error}`);
    }
  }

  // Delete agent handler
  async function handleDeleteAgent() {
    if (!existingAgent) return;

    const error = await deleteAgent(existingAgent.id);

    if (error) {
      toast.error(`${t("agentEditor.failedToDeleteAgent")}: ${error}`);
    } else {
      toast.success(t("agentEditor.agentDeletedSuccess"));

      deleteAgentModal.toggle(false);
      await refreshAgents();
      router.push("/app/agents");
    }
  }

  const [agentGraphSchema, setAgentGraphSchema] = useState<string | undefined>(
    existingAgent?.graph_schema ?? undefined
  );
  // Owns InlineFlowDesigner's canvas across the whole edit session, so
  // handleSubmit can read out what was drawn once the agent (and its
  // agent_definition_id) exist — InlineFlowDesigner itself has nowhere to
  // persist to before that id exists.
  const inlineFlowStore = useMemo(() => createFlowStore(), []);

  // Live chat entry/exit presence on the inline canvas — the create button
  // stays disabled until both exist (the backend rejects publish otherwise:
  // FLOW_NO_ENTRY / FLOW_NO_EXIT). Two primitive selectors rather than one
  // object selector so zustand's Object.is comparison doesn't re-render on
  // every unrelated store change.
  const flowHasChatInput = useStore(
    inlineFlowStore,
    (s) => getChatNodePresence(s.nodes).hasChatInput
  );
  const flowHasChatOutput = useStore(
    inlineFlowStore,
    (s) => getChatNodePresence(s.nodes).hasChatOutput
  );

  // Editing an existing flow persona never reaches this component — the
  // edit route (apps/web/src/app/app/agents/edit/[id]/page.tsx) redirects
  // to the full-screen studio (/app/flows/[definitionId]) before mount.
  // `isFlowBacked` still applies here during *creation*, while
  // `agentGraphSchema` is "flow" but no definition id exists yet — that
  // path renders InlineFlowDesigner below, unrelated to the old tab bar.
  const isFlowBacked =
    (agentGraphSchema === "flow" || existingAgent?.graph_schema === "flow") &&
    Boolean(existingAgent?.agent_definition_id);

  const isAnyToolsLoading =
    isToolsLoading ||
    isMcpLoading ||
    isOpenApiLoading ||
    isBuiltInToolsLoading ||
    isMailConfigsLoading;

  if (!isAnyToolsLoading) {
    hasLoadedInitialData.current = true;
  }

  // Wait for async tool data before rendering the form for the first time. Formik captures
  // initialValues on mount — if tools haven't loaded yet, the initial values
  // won't include MCP tool fields.
  if (!isFlowBacked && !hasLoadedInitialData.current && isAnyToolsLoading) {
    return <AgentEditorSkeleton isEditing={!!existingAgent} />;
  }

  return (
    <>
      <div
        data-testid="AgentsEditorPage/container"
        aria-label="Agents Editor Page"
        className="h-full w-full flex flex-col"
      >
        <Formik
          key={existingAgent?.id ?? "new"}
          initialValues={initialValues}
          validationSchema={validationSchema}
          onSubmit={handleSubmit}
          validateOnChange
          validateOnBlur
          validateOnMount
          initialStatus={{ warnings: {} }}
        >
          {({ isSubmitting, isValid, dirty, values, setFieldValue }) => {
            const isShared =
              values.is_public ||
              values.shared_user_ids.length > 0 ||
              values.shared_group_ids.length > 0;

            const isDynamicAgent = values.base_agent === "dynamic-agent";
            // `isFlowBacked` only turns true once a flow definition actually
            // exists (`existingAgent.agent_definition_id`) — right for
            // locking the graph_schema picker itself once it's permanent,
            // wrong for gating everything else: while *creating* an agent,
            // picking "Visual Flow" from the dropdown must hide the classic
            // config sections immediately, not only after the first save.
            // `InlineFlowDesigner` below already reacts to the picked value
            // this way (`values.graph_schema === "flow"`, no `isFlowBacked`
            // check) — this extends the same behaviour to every section
            // that's now fully superseded by the canvas.
            const isFlowSchemaSelected =
              isDynamicAgent && values.graph_schema === "flow";
            const schemaCapabilities = isDynamicAgent
              ? GRAPH_SCHEMA_CAPABILITIES[values.graph_schema] ?? {
                  supports_tools: true,
                  supports_rag: true,
                }
              : null;
            const schemaSupportsTools =
              !isFlowSchemaSelected &&
              (!isDynamicAgent || (schemaCapabilities?.supports_tools ?? true));
            const schemaSupportsRag = !isFlowSchemaSelected;
            const graphSchemaLabel =
              GRAPH_SCHEMA_OPTIONS.find(
                (option) => option.value === values.graph_schema
              )?.label ?? values.graph_schema;
            const brainTypeLabel =
              BRAIN_TYPE_OPTIONS.find(
                (option) => option.value === values.brain_type
              )?.label ?? values.brain_type;
            const memoryTypeLabel =
              values.memory_type === "none"
                ? undefined
                : MEMORY_TYPE_OPTIONS.find(
                    (option) => option.value === values.memory_type
                  )?.label ?? values.memory_type;
            const selectedMcpToolNamesForCard = [
              ...allMcpTools
                .filter((tool) => (values as any)[`mcp_tool_${tool.name}`])
                .map((tool) => tool.name),
              ...allBuiltInTools
                .filter((tool) => (values as any)[`builtin_tool_${tool.name}`])
                .map((tool) => tool.name),
            ];
            const isSendEmailSelected =
              selectedMcpToolNamesForCard.includes("send_email");
            const selectedDynamicToolNames = [
              ...allMcpTools
                .filter((tool) => (values as any)[`mcp_tool_${tool.name}`])
                .map((tool) => tool.name),
              ...allBuiltInTools
                .filter((tool) => (values as any)[`builtin_tool_${tool.name}`])
                .map((tool) => tool.display_name),
            ];
            const hasKnowledgeEnabled =
              values.enable_knowledge &&
              (values.rag_document_collection_ids.length > 0 ||
                values.rag_graph_collection_ids.length > 0);
            const previewSubAgentConfigs =
              values.graph_schema === "pipeline"
                ? values.stages
                : values.graph_schema === "supervisor"
                  ? values.sub_agents
                  : [];

            return (
              <>
                <ConnectorBindingsCompatibilityGuard />
                <shareAgentModal.Provider>
                  <ShareAgentModal
                    agentId={existingAgent?.id}
                    userIds={values.shared_user_ids}
                    groupIds={values.shared_group_ids}
                    isPublic={values.is_public}
                    isFeatured={values.featured}
                    labelIds={values.label_ids}
                    onShare={(
                      userIds,
                      groupIds,
                      isPublic,
                      isFeatured,
                      labelIds
                    ) => {
                      setFieldValue("shared_user_ids", userIds);
                      setFieldValue("shared_group_ids", groupIds);
                      setFieldValue("is_public", isPublic);
                      setFieldValue("featured", isFeatured);
                      setFieldValue("label_ids", labelIds);
                      shareAgentModal.toggle(false);
                    }}
                  />
                </shareAgentModal.Provider>
                <deleteAgentModal.Provider>
                  {deleteAgentModal.isOpen && (
                    <ConfirmationModalLayout
                      icon={SvgTrash}
                      title={t("agentEditor.deleteAgentTitle")}
                      submit={
                        <Button danger onClick={handleDeleteAgent}>
                          {t("agentEditor.deleteButton")}
                        </Button>
                      }
                      onClose={() => deleteAgentModal.toggle(false)}
                    >
                      <GeneralLayouts.Section alignItems="start" gap={0.5}>
                        <Text>{t("agentEditor.deleteAgentConfirmText")}</Text>
                        <Text>{t("agentEditor.deleteAgentAreYouSure")}</Text>
                      </GeneralLayouts.Section>
                    </ConfirmationModalLayout>
                  )}
                </deleteAgentModal.Provider>

                <Form className="h-full w-full">
                  <SettingsLayouts.Root width="xl">
                    <SettingsLayouts.Header
                      icon={SvgOnyxOctagon}
                      title={
                        existingAgent
                          ? t("agentEditor.editAgentTitle")
                          : t("agentEditor.createAgentTitle")
                      }
                      rightChildren={
                        <div className="flex gap-2">
                          {isDynamicAgent &&
                            existingAgent?.agent_definition_id &&
                            !isFlowBacked && (
                              <Button
                                type="button"
                                data-testid="convert-to-flow-button"
                                secondary
                                onClick={async () => {
                                  if (
                                    !existingAgent?.id ||
                                    !existingAgent?.agent_definition_id
                                  )
                                    return;
                                  try {
                                    const res: any = await updatePersona(
                                      existingAgent.id,
                                      {
                                        ...values,
                                        graph_schema: "flow",
                                      } as any
                                    );
                                    if (res?.error) {
                                      toast.error(res.error);
                                      return;
                                    }
                                    await fetch(
                                      flowApi.draft(
                                        existingAgent.agent_definition_id
                                      ),
                                      {
                                        method: "PUT",
                                        headers: {
                                          "Content-Type": "application/json",
                                        },
                                        body: JSON.stringify({
                                          nodes: [],
                                          edges: [],
                                        }),
                                      }
                                    );
                                    if (existingAgent) {
                                      existingAgent.graph_schema = "flow";
                                    }
                                    setAgentGraphSchema("flow");
                                    toast.success(
                                      "Converted to Visual Flow successfully!"
                                    );
                                    // Flow-backed agents are edited in the
                                    // full-screen studio now, not a tab here.
                                    router.push(
                                      `/app/flows/${existingAgent.agent_definition_id}` as Route
                                    );
                                  } catch (err: any) {
                                    toast.error(
                                      err?.message ||
                                        "Failed to convert to flow"
                                    );
                                  }
                                }}
                              >
                                {t(
                                  "agentEditor.convertToFlow",
                                  "Convert to Flow"
                                )}
                              </Button>
                            )}
                          <Button
                            type="button"
                            secondary
                            onClick={() => router.back()}
                          >
                            {t("agentEditor.cancelButton")}
                          </Button>
                          <Button
                            type="submit"
                            disabled={
                              isSubmitting ||
                              !isValid ||
                              !dirty ||
                              (!existingAgent &&
                                isFlowSchemaSelected &&
                                (!flowHasChatInput || !flowHasChatOutput))
                            }
                          >
                            {existingAgent
                              ? t("agentEditor.saveButton")
                              : t("agentEditor.createButton")}
                          </Button>
                        </div>
                      }
                      separator
                    />

                    {/* Agent Form Content */}
                    <SettingsLayouts.Body>
                      <div className="flex w-full flex-col gap-6 md:gap-8">
                        <div
                          className={cn(
                            "grid w-full items-start gap-6",
                            isDynamicAgent && !isFlowSchemaSelected
                              ? "xl:grid-cols-[minmax(0,1fr)_minmax(30rem,38rem)]"
                              : "lg:grid-cols-[minmax(0,1fr)_auto]"
                          )}
                        >
                          <div className="flex min-w-0 flex-col gap-4">
                            <InputLayouts.Vertical
                              name="name"
                              title={t("agentEditor.nameLabel")}
                            >
                              <InputTypeInField
                                name="name"
                                placeholder={t(
                                  "agentEditor.agentNamePlaceholder"
                                )}
                              />
                            </InputLayouts.Vertical>

                            <InputLayouts.Vertical
                              name="description"
                              title={`${t(
                                "agentEditor.descriptionLabel"
                              )}${optionalTag}`}
                            >
                              <InputTextAreaField
                                name="description"
                                placeholder={t(
                                  "agentEditor.agentDescriptionPlaceholder"
                                )}
                              />
                            </InputLayouts.Vertical>

                            <InputLayouts.Vertical
                              name="base_agent"
                              title={t("agentEditor.baseAgentLabel")}
                              description={t(
                                "agentEditor.baseAgentDescription"
                              )}
                            >
                              <InputSelectField name="base_agent">
                                <InputSelect.Trigger
                                  placeholder={t(
                                    "agentEditor.selectBaseAgentPlaceholder"
                                  )}
                                />
                                <InputSelect.Content>
                                  <InputSelect.Item value="chatbot">
                                    {t("agentEditor.chatbotOption")}
                                  </InputSelect.Item>
                                  <InputSelect.Item value="configurable-mcp-agent">
                                    {t("agentEditor.mcpAgentOption")}
                                  </InputSelect.Item>
                                  <InputSelect.Item value="dynamic-agent">
                                    {t("agentEditor.dynamicAgentOption")}
                                  </InputSelect.Item>
                                </InputSelect.Content>
                              </InputSelectField>
                            </InputLayouts.Vertical>

                            {values.base_agent === "dynamic-agent" && (
                              <InputLayouts.Vertical
                                name="graph_schema"
                                title={t("agentEditor.graphSchemaLabel")}
                                description={t(
                                  "agentEditor.graphSchemaDescription"
                                )}
                              >
                                <InputSelectField name="graph_schema">
                                  <InputSelect.Trigger
                                    placeholder={t(
                                      "agentEditor.selectGraphSchemaPlaceholder"
                                    )}
                                  />
                                  <InputSelect.Content>
                                    {GRAPH_SCHEMA_OPTIONS.map((option) => (
                                      <InputSelect.Item
                                        key={option.value}
                                        value={option.value}
                                      >
                                        {option.label}
                                      </InputSelect.Item>
                                    ))}
                                  </InputSelect.Content>
                                </InputSelectField>
                              </InputLayouts.Vertical>
                            )}

                            {/* Brain type and sub-agent composition are
                                meaningless once the canvas defines the
                                agent's behaviour — hidden as soon as "Visual
                                Flow" is picked, not only once a flow
                                definition has actually been saved. */}
                            {values.base_agent === "dynamic-agent" &&
                              !isFlowSchemaSelected && (
                                <>
                                  <InputLayouts.Vertical
                                    name="brain_type"
                                    title={t("agentEditor.brainTypeLabel")}
                                  >
                                    <InputSelectField name="brain_type">
                                      <InputSelect.Trigger
                                        placeholder={t(
                                          "agentEditor.selectBrainTypePlaceholder"
                                        )}
                                      />
                                      <InputSelect.Content>
                                        {BRAIN_TYPE_OPTIONS.map((option) => (
                                          <InputSelect.Item
                                            key={option.value}
                                            value={option.value}
                                          >
                                            {option.label}
                                          </InputSelect.Item>
                                        ))}
                                      </InputSelect.Content>
                                    </InputSelectField>
                                  </InputLayouts.Vertical>

                                  {(values.graph_schema === "supervisor" ||
                                    values.graph_schema === "pipeline") && (
                                    <>
                                      <Separator />
                                      <SubAgentSelector
                                        graphSchema={values.graph_schema}
                                      />
                                      <CompositionValidator
                                        agentId={
                                          existingAgent?.id
                                            ? String(existingAgent.id)
                                            : null
                                        }
                                        graphSchema={values.graph_schema}
                                        subAgentIds={values.sub_agent_ids}
                                        onValidationChange={(_, depth) =>
                                          setCompositionDepth(depth)
                                        }
                                      />
                                    </>
                                  )}
                                </>
                              )}

                            {!isFlowSchemaSelected && (
                              <InputLayouts.Horizontal
                                name="long_term_memory"
                                title={t("agentEditor.longTermMemoryLabel")}
                                description={t(
                                  "agentEditor.longTermMemoryDescription"
                                )}
                              >
                                <SwitchField name="long_term_memory" />
                              </InputLayouts.Horizontal>
                            )}
                          </div>

                          <div
                            className={cn(
                              "flex min-w-0 flex-col gap-4",
                              isDynamicAgent && !isFlowSchemaSelected
                                ? "order-first xl:order-none xl:sticky xl:top-32 xl:self-start"
                                : "lg:w-fit"
                            )}
                          >
                            <InputLayouts.Vertical
                              name="agent_avatar"
                              title={t("agentEditor.agentAvatarLabel")}
                            >
                              <AgentIconEditor existingAgent={existingAgent} />
                            </InputLayouts.Vertical>

                            {isDynamicAgent && !isFlowSchemaSelected && (
                              <div className="flex w-full min-w-0 flex-col gap-3 animate-in fade-in duration-200">
                                <GraphSchemaPreview
                                  variant="hero"
                                  graphSchema={values.graph_schema}
                                  graphSchemaLabel={graphSchemaLabel}
                                  agentName={values.name}
                                  brainTypeLabel={brainTypeLabel}
                                  memoryTypeLabel={memoryTypeLabel}
                                  longTermMemoryEnabled={
                                    values.long_term_memory
                                  }
                                  selectedToolNames={selectedDynamicToolNames}
                                  hasKnowledgeEnabled={hasKnowledgeEnabled}
                                  compositionDepth={compositionDepth}
                                  subAgentConfigs={previewSubAgentConfigs}
                                />
                                <Button
                                  secondary
                                  type="button"
                                  leftIcon={SvgNetworkGraph}
                                  onClick={() => setIsGraphPreviewOpen(true)}
                                  className="w-full"
                                >
                                  {t("agentEditor.graphPreviewShowButton")}
                                </Button>

                                <Modal
                                  open={isGraphPreviewOpen}
                                  onOpenChange={setIsGraphPreviewOpen}
                                >
                                  <Modal.Content
                                    width="md"
                                    height="lg"
                                    preventAccidentalClose={false}
                                    background="gray"
                                  >
                                    <Modal.Header
                                      icon={SvgNetworkGraph}
                                      title={t(
                                        "agentEditor.graphPreviewModalTitle"
                                      )}
                                      description={t(
                                        "agentEditor.graphPreviewModalDescription"
                                      )}
                                      onClose={() =>
                                        setIsGraphPreviewOpen(false)
                                      }
                                    />
                                    <Modal.Body twoTone>
                                      <GraphSchemaPreview
                                        variant="hero"
                                        graphSchema={values.graph_schema}
                                        graphSchemaLabel={graphSchemaLabel}
                                        agentName={values.name}
                                        brainTypeLabel={brainTypeLabel}
                                        memoryTypeLabel={memoryTypeLabel}
                                        longTermMemoryEnabled={
                                          values.long_term_memory
                                        }
                                        selectedToolNames={
                                          selectedDynamicToolNames
                                        }
                                        hasKnowledgeEnabled={
                                          hasKnowledgeEnabled
                                        }
                                        compositionDepth={compositionDepth}
                                        subAgentConfigs={previewSubAgentConfigs}
                                      />
                                    </Modal.Body>
                                    <Modal.Footer>
                                      <Button
                                        secondary
                                        type="button"
                                        onClick={() =>
                                          setIsGraphPreviewOpen(false)
                                        }
                                      >
                                        {t(
                                          "agentEditor.graphPreviewCloseButton"
                                        )}
                                      </Button>
                                    </Modal.Footer>
                                  </Modal.Content>
                                </Modal>
                              </div>
                            )}
                          </div>
                        </div>

                        <AnimatePresence>
                          {isDynamicAgent && values.graph_schema === "flow" && (
                            <motion.div
                              key="inline_flow_designer_section"
                              initial={{ opacity: 0, y: 24, scale: 0.99 }}
                              animate={{ opacity: 1, y: 0, scale: 1 }}
                              exit={{ opacity: 0, y: 24, scale: 0.99 }}
                              transition={{
                                duration: 0.38,
                                ease: [0.16, 1, 0.3, 1],
                              }}
                              className="flex flex-col gap-4"
                            >
                              <Separator noPadding />
                              {!existingAgent &&
                                (!flowHasChatInput || !flowHasChatOutput) && (
                                  <Message
                                    error
                                    static
                                    large
                                    close={false}
                                    className="w-full"
                                    text={t(
                                      "agentEditor.flowMissingChatNodes",
                                      {
                                        nodes: [
                                          !flowHasChatInput &&
                                            t("agentEditor.flowChatInputNode"),
                                          !flowHasChatOutput &&
                                            t("agentEditor.flowChatOutputNode"),
                                        ]
                                          .filter(Boolean)
                                          .join(", "),
                                      }
                                    )}
                                  />
                                )}
                              <InlineFlowDesigner store={inlineFlowStore} />
                            </motion.div>
                          )}
                        </AnimatePresence>

                        <Separator noPadding />

                        <GeneralLayouts.Section>
                          {/* The agent's instructions live on the canvas
                              itself (Agent Instructions / system-prompt
                              fields on the relevant nodes) once it's
                              flow-backed — this classic single system prompt
                              no longer applies. */}
                          {!isFlowSchemaSelected && (
                            <InputLayouts.Vertical
                              name="instructions"
                              title={`${t(
                                "agentEditor.instructionsLabel"
                              )}${optionalTag}`}
                              description={t(
                                "agentEditor.instructionsDescription"
                              )}
                            >
                              <InputTextAreaField
                                name="instructions"
                                placeholder={t(
                                  "agentEditor.instructionsPlaceholder"
                                )}
                              />
                            </InputLayouts.Vertical>
                          )}

                          <InputLayouts.Vertical
                            name="starter_messages"
                            title={`${t(
                              "agentEditor.conversationStartersLabel"
                            )}${optionalTag}`}
                            description={t(
                              "agentEditor.conversationStartersDescription"
                            )}
                          >
                            <StarterMessages />
                          </InputLayouts.Vertical>
                        </GeneralLayouts.Section>

                        <Separator noPadding />

                        {schemaSupportsRag && (
                          <>
                            <AgentKnowledgePane
                              enableKnowledge={values.enable_knowledge}
                              onEnableKnowledgeChange={(enabled) =>
                                setFieldValue("enable_knowledge", enabled)
                              }
                              ragDocumentCollectionIds={
                                values.rag_document_collection_ids
                              }
                              onDocumentCollectionIdsChange={(ids) =>
                                setFieldValue(
                                  "rag_document_collection_ids",
                                  ids
                                )
                              }
                              ragGraphCollectionIds={
                                values.rag_graph_collection_ids
                              }
                              onGraphCollectionIdsChange={(ids) =>
                                setFieldValue("rag_graph_collection_ids", ids)
                              }
                              onCollectionDisplayNamesChange={
                                setCollectionDisplayNames
                              }
                            />

                            <Separator noPadding />
                          </>
                        )}

                        {schemaSupportsTools && (
                          <SimpleCollapsible>
                            <SimpleCollapsible.Header
                              title={t("agentEditor.actionsLabel")}
                              description={
                                values.base_agent === "chatbot"
                                  ? t("agentEditor.actionsChatbotDescription")
                                  : t("agentEditor.actionsDescription")
                              }
                            />
                            <SimpleCollapsible.Content>
                              <GeneralLayouts.Section gap={0.5}>
                                {values.base_agent === "chatbot" ? (
                                  <Card className="border border-amber-300 dark:border-amber-700/60 bg-amber-50/70 dark:bg-amber-950/30 p-4 rounded-12">
                                    <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
                                      <div className="flex items-start gap-3">
                                        <div className="p-2 rounded-08 bg-amber-100 dark:bg-amber-900/50 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5">
                                          <SvgInfo className="w-5 h-5" />
                                        </div>
                                        <div className="flex flex-col gap-1">
                                          <Text
                                            mainUiAction
                                            text03
                                            className="font-semibold text-amber-800 dark:text-amber-200"
                                          >
                                            {t(
                                              "agentEditor.actionsChatbotWarningTitle"
                                            )}
                                          </Text>
                                          <Text
                                            mainUiMuted
                                            text03
                                            className="text-amber-700/90 dark:text-amber-300/90 leading-relaxed"
                                          >
                                            {t(
                                              "agentEditor.actionsChatbotWarningDescription"
                                            )}
                                          </Text>
                                        </div>
                                      </div>
                                      <div className="shrink-0 w-full sm:w-auto">
                                        <Button
                                          type="button"
                                          secondary
                                          size="md"
                                          onClick={() =>
                                            setFieldValue(
                                              "base_agent",
                                              "configurable-mcp-agent"
                                            )
                                          }
                                          className="w-full sm:w-auto"
                                        >
                                          {t(
                                            "agentEditor.actionsChatbotSwitchToMcpButton"
                                          )}
                                        </Button>
                                      </div>
                                    </div>
                                  </Card>
                                ) : (
                                  <>
                                    {[
                                      "configurable-mcp-agent",
                                      "dynamic-agent",
                                    ].includes(values.base_agent) &&
                                      schemaSupportsTools &&
                                      toolSelectionGroups.length > 0 && (
                                        <McpToolSelectionCard
                                          title={t("agentEditor.actionsLabel")}
                                          description={t(
                                            "agentEditor.mcpToolsCardDescription",
                                            "Choose MCP and tools-service tools this agent can call."
                                          )}
                                          groups={toolSelectionGroups}
                                          selectedToolNames={
                                            selectedMcpToolNamesForCard
                                          }
                                          onSelectedToolNamesChange={(
                                            toolNames
                                          ) => {
                                            const next = new Set(toolNames);
                                            if (!next.has("send_email")) {
                                              setFieldValue(
                                                "send_email_mail_config_id",
                                                ""
                                              );
                                            }
                                            allMcpTools.forEach((tool) => {
                                              setFieldValue(
                                                `mcp_tool_${tool.name}`,
                                                next.has(tool.name)
                                              );
                                            });
                                            allBuiltInTools.forEach((tool) => {
                                              setFieldValue(
                                                `builtin_tool_${tool.name}`,
                                                next.has(tool.name)
                                              );
                                            });
                                          }}
                                          isLoading={
                                            isToolsLoading ||
                                            isBuiltInToolsLoading ||
                                            isMcpLoading
                                          }
                                        />
                                      )}

                                    {values.base_agent ===
                                      "configurable-mcp-agent" && (
                                      <ConnectorBindingsField
                                        options={connectorToolOptions}
                                        isLoading={
                                          isConnectorToolOptionsLoading
                                        }
                                        error={connectorToolOptionsError}
                                      />
                                    )}

                                    {isSendEmailSelected && (
                                      <InputLayouts.Vertical
                                        name="send_email_mail_config_id"
                                        title={t(
                                          "agentEditor.sendEmailMailConfigLabel",
                                          "Mail config"
                                        )}
                                        description={t(
                                          "agentEditor.sendEmailMailConfigDescription",
                                          "This agent will send email through the selected SMTP account."
                                        )}
                                      >
                                        <InputSelectField
                                          name="send_email_mail_config_id"
                                          disabled={
                                            isMailConfigsLoading ||
                                            mailConfigs.filter(
                                              (config) => config.is_active
                                            ).length === 0
                                          }
                                        >
                                          <InputSelect.Trigger
                                            placeholder={
                                              mailConfigs.filter(
                                                (config) => config.is_active
                                              ).length === 0
                                                ? t(
                                                    "agentEditor.noMailConfigsPlaceholder",
                                                    "E-posta yapılandırması bulunamadı"
                                                  )
                                                : t(
                                                    "agentEditor.selectMailConfigPlaceholder",
                                                    "Select mail config"
                                                  )
                                            }
                                          />
                                          <InputSelect.Content>
                                            {mailConfigs
                                              .filter(
                                                (config) => config.is_active
                                              )
                                              .map((config) => (
                                                <InputSelect.Item
                                                  key={config.id}
                                                  value={config.id}
                                                  description={`${config.from_email} - ${config.host}:${config.port}`}
                                                >
                                                  {config.name}
                                                </InputSelect.Item>
                                              ))}
                                          </InputSelect.Content>
                                        </InputSelectField>
                                        {!isMailConfigsLoading &&
                                          mailConfigs.filter(
                                            (config) => config.is_active
                                          ).length === 0 && (
                                            <Text secondaryBody text03>
                                              {t(
                                                "agentEditor.noMailConfigsAvailable",
                                                "Create a mail config in Configuration first."
                                              )}
                                            </Text>
                                          )}
                                      </InputLayouts.Vertical>
                                    )}
                                  </>
                                )}
                              </GeneralLayouts.Section>
                            </SimpleCollapsible.Content>
                          </SimpleCollapsible>
                        )}

                        <Separator noPadding />

                        <SimpleCollapsible>
                          <SimpleCollapsible.Header
                            title={t("agentEditor.advancedOptionsLabel")}
                            description={t(
                              "agentEditor.advancedOptionsDescription"
                            )}
                          />
                          <SimpleCollapsible.Content>
                            <GeneralLayouts.Section>
                              <Card>
                                <AgentVisibilityFields
                                  isPublic={values.is_public}
                                  featured={values.featured}
                                  canFeature={canUpdateFeaturedStatus}
                                  onChange={(next) => {
                                    setFieldValue("is_public", next.isPublic);
                                    setFieldValue("featured", next.featured);
                                  }}
                                  footer={
                                    <Button
                                      secondary
                                      leftIcon={isShared ? SvgUsers : SvgLock}
                                      onClick={() =>
                                        shareAgentModal.toggle(true)
                                      }
                                    >
                                      {t("agentEditor.shareButton")}
                                    </Button>
                                  }
                                />
                              </Card>

                              {/* Default model / knowledge cutoff / prompt
                                  overwrite / reminders all tune the classic
                                  single system prompt — a flow-backed agent
                                  has its own Language Model node(s) per
                                  step on the canvas instead of one default. */}
                              {!isFlowSchemaSelected && (
                                <>
                                  <Card>
                                    <InputLayouts.Horizontal
                                      name="llm_model"
                                      title={t("agentEditor.defaultModelLabel")}
                                      description={t(
                                        "agentEditor.defaultModelDescription"
                                      )}
                                    >
                                      <LLMSelector
                                        name="llm_model"
                                        llmProviders={llmProviders ?? []}
                                        currentLlm={getCurrentLlm(
                                          values,
                                          llmProviders
                                        )}
                                        defaultOptionLabel={t(
                                          "agentEditor.defaultModelOption"
                                        )}
                                        onSelect={(selected, _providerId) =>
                                          onLlmSelect(selected, setFieldValue)
                                        }
                                      />
                                    </InputLayouts.Horizontal>
                                    <InputLayouts.Horizontal
                                      name="knowledge_cutoff_date"
                                      title={t(
                                        "agentEditor.knowledgeCutoffLabel"
                                      )}
                                      description={t(
                                        "agentEditor.knowledgeCutoffDescription"
                                      )}
                                    >
                                      <InputDatePickerField name="knowledge_cutoff_date" />
                                    </InputLayouts.Horizontal>
                                    <InputLayouts.Horizontal
                                      name="replace_base_system_prompt"
                                      title={t(
                                        "agentEditor.overwritePromptLabel"
                                      )}
                                      description={t(
                                        "agentEditor.overwritePromptDescription"
                                      )}
                                    >
                                      <SwitchField name="replace_base_system_prompt" />
                                    </InputLayouts.Horizontal>
                                  </Card>

                                  <GeneralLayouts.Section gap={0.25}>
                                    <InputLayouts.Vertical
                                      name="reminders"
                                      title={t("agentEditor.remindersLabel")}
                                    >
                                      <InputTextAreaField
                                        name="reminders"
                                        placeholder={t(
                                          "agentEditor.remindersPlaceholder"
                                        )}
                                      />
                                    </InputLayouts.Vertical>
                                    <Text text03 secondaryBody>
                                      {t("agentEditor.remindersHint")}
                                    </Text>
                                  </GeneralLayouts.Section>
                                </>
                              )}
                            </GeneralLayouts.Section>
                          </SimpleCollapsible.Content>
                        </SimpleCollapsible>

                        {existingAgent && (
                          <>
                            <Separator noPadding />

                            <Card>
                              <InputLayouts.Horizontal
                                title={t("agentEditor.deleteThisAgentLabel")}
                                description={t(
                                  "agentEditor.deleteThisAgentDescription"
                                )}
                                center
                              >
                                <Button
                                  secondary
                                  danger
                                  onClick={() => deleteAgentModal.toggle(true)}
                                >
                                  {t("agentEditor.deleteButton")}
                                </Button>
                              </InputLayouts.Horizontal>
                            </Card>
                          </>
                        )}
                      </div>
                    </SettingsLayouts.Body>
                  </SettingsLayouts.Root>
                </Form>
              </>
            );
          }}
        </Formik>
      </div>
    </>
  );
}
