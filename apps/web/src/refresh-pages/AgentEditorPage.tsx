"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import * as GeneralLayouts from "@/layouts/general-layouts";
import Button from "@/refresh-components/buttons/Button";
import { FullPersona } from "@/app/admin/agents/interfaces";
import { buildImgUrl } from "@/app/app/components/files/images/utils";
import { Formik, Form, FieldArray } from "formik";
import * as Yup from "yup";
import InputTypeInField from "@/refresh-components/form/InputTypeInField";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import InputSelectField from "@/refresh-components/form/InputSelectField";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTypeInElementField from "@/refresh-components/form/InputTypeInElementField";
import InputDatePickerField from "@/refresh-components/form/InputDatePickerField";
import Message from "@/refresh-components/messages/Message";
import Separator from "@/refresh-components/Separator";
import * as InputLayouts from "@/layouts/input-layouts";
import { useFormikContext } from "formik";
import LLMSelector from "@/components/llm/LLMSelector";
import { parseLlmDescriptor, structureValue } from "@/lib/llmConfig/utils";
import { useLLMProviders } from "@/hooks/useLLMProviders";
import {
  STARTER_MESSAGES_EXAMPLES,
  MAX_CHARACTERS_STARTER_MESSAGE,
  MAX_CHARACTERS_AGENT_DESCRIPTION,
} from "@/lib/constants";
import {
  IMAGE_GENERATION_TOOL_ID,
  WEB_SEARCH_TOOL_ID,
  PYTHON_TOOL_ID,
  SEARCH_TOOL_ID,
  OPEN_URL_TOOL_ID,
} from "@/app/app/components/tools/constants";
import Text from "@/refresh-components/texts/Text";
import { Card } from "@/refresh-components/cards";
import SimpleCollapsible from "@/refresh-components/SimpleCollapsible";
import SwitchField from "@/refresh-components/form/SwitchField";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import { toast } from "@/hooks/useToast";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import {
  SvgActions,
  SvgExpand,
  SvgFold,
  SvgImage,
  SvgLock,
  SvgOnyxOctagon,
  SvgSliders,
  SvgUsers,
  SvgTrash,
} from "@opal/icons";
import CustomAgentAvatar, {
  agentAvatarIconMap,
} from "@/refresh-components/avatars/CustomAgentAvatar";
import InputAvatar from "@/refresh-components/inputs/InputAvatar";
import SquareButton from "@/refresh-components/buttons/SquareButton";
import { useAgents } from "@/hooks/useAgents";
import {
  createPersona,
  updatePersona,
  PersonaUpsertParameters,
} from "@/app/admin/agents/lib";
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
import * as ActionsLayouts from "@/layouts/actions-layouts";
import * as ExpandableCard from "@/layouts/expandable-card-layouts";
import { getActionIcon } from "@/lib/tools/mcpUtils";
import { MCPServer, MCPTool, ToolSnapshot } from "@/lib/tools/interfaces";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import useFilter from "@/hooks/useFilter";
import EnabledCount from "@/refresh-components/EnabledCount";
import { useAppRouter } from "@/hooks/appNavigation";
import { deleteAgent } from "@/lib/agents";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import ShareAgentModal from "@/sections/modals/ShareAgentModal";
import AgentKnowledgePane from "@/sections/knowledge/AgentKnowledgePane";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { useUser } from "@/providers/UserProvider";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";

interface AgentIconEditorProps {
  existingAgent?: FullPersona | null;
}

function FormWarningsEffect() {
  const { values, setStatus } = useFormikContext<{
    web_search: boolean;
    open_url: boolean;
  }>();
  const { t } = useTranslation();

  useEffect(() => {
    const warnings: Record<string, string> = {};
    if (values.web_search && !values.open_url) {
      warnings.open_url = t("agentEditor.webSearchWarning");
    }
    setStatus({ warnings });
  }, [values.web_search, values.open_url, setStatus, t]);

  return null;
}

function AgentIconEditor({ existingAgent }: AgentIconEditorProps) {
  const { values, setFieldValue } = useFormikContext<{
    name: string;
    icon_name: string | null;
    uploaded_image_id: string | null;
    remove_image: boolean | null;
  }>();
  const { t } = useTranslation();
  const [uploadedImagePreview, setUploadedImagePreview] = useState<
    string | null
  >(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    // Clear previous preview to free memory
    setUploadedImagePreview(null);

    // Clear selected icon and remove_image flag when uploading an image
    setFieldValue("icon_name", null);
    setFieldValue("remove_image", false);

    // Show preview immediately
    const reader = new FileReader();
    reader.onloadend = () => {
      setUploadedImagePreview(reader.result as string);
    };
    reader.readAsDataURL(file);

    // Upload the file
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("/api/admin/persona/upload-image", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        console.error("Failed to upload image");
        setUploadedImagePreview(null);
        return;
      }

      const { file_id } = await response.json();
      setFieldValue("uploaded_image_id", file_id);
      setPopoverOpen(false);
    } catch (error) {
      console.error("Upload error:", error);
      setUploadedImagePreview(null);
    }
  }

  const imageSrc = uploadedImagePreview
    ? uploadedImagePreview
    : values.uploaded_image_id
      ? buildImgUrl(values.uploaded_image_id)
      : values.icon_name
        ? undefined
        : values.remove_image
          ? undefined
          : existingAgent?.uploaded_image_id
            ? buildImgUrl(existingAgent.uploaded_image_id)
            : undefined;

  function handleIconClick(iconName: string | null) {
    setFieldValue("icon_name", iconName);
    setFieldValue("uploaded_image_id", null);
    setFieldValue("remove_image", true);
    setUploadedImagePreview(null);
    setPopoverOpen(false);

    // Reset the file input so the same file can be uploaded again later
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleImageUpload}
        className="hidden"
      />

      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <Popover.Trigger asChild>
          <InputAvatar className="group/InputAvatar relative flex flex-col items-center justify-center h-[7.5rem] w-[7.5rem]">
            {/* We take the `InputAvatar`'s height/width (in REM) and multiply it by 16 (the REM -> px conversion factor). */}
            <CustomAgentAvatar
              size={imageSrc ? 7.5 * 16 : 40}
              src={imageSrc}
              iconName={values.icon_name ?? undefined}
              name={values.name}
            />
            <Button
              className="absolute bottom-0 left-1/2 -translate-x-1/2 h-[1.75rem] mb-2 invisible group-hover/InputAvatar:visible"
              secondary
            >
              {t("agentEditor.editButton")}
            </Button>
          </InputAvatar>
        </Popover.Trigger>
        <Popover.Content>
          <PopoverMenu>
            {[
              <LineItem
                key="upload-image"
                icon={SvgImage}
                onClick={() => fileInputRef.current?.click()}
                emphasized
              >
                {t("agentEditor.uploadImage")}
              </LineItem>,
              null,
              <div className="grid grid-cols-4 gap-1">
                <SquareButton
                  key="default-icon"
                  icon={() => (
                    <CustomAgentAvatar name={values.name} size={30} />
                  )}
                  onClick={() => handleIconClick(null)}
                  transient={!imageSrc && values.icon_name === null}
                />
                {Object.keys(agentAvatarIconMap).map((iconName) => (
                  <SquareButton
                    key={iconName}
                    onClick={() => handleIconClick(iconName)}
                    icon={() => (
                      <CustomAgentAvatar iconName={iconName} size={30} />
                    )}
                    transient={values.icon_name === iconName}
                  />
                ))}
              </div>,
            ]}
          </PopoverMenu>
        </Popover.Content>
      </Popover>
    </>
  );
}

interface OpenApiToolCardProps {
  tool: ToolSnapshot;
}

function OpenApiToolCard({ tool }: OpenApiToolCardProps) {
  const toolFieldName = `openapi_tool_${tool.id}`;

  return (
    <ExpandableCard.Root defaultFolded>
      <ActionsLayouts.Header
        title={tool.display_name || tool.name}
        description={tool.description}
        icon={SvgActions}
        rightChildren={<SwitchField name={toolFieldName} />}
      />
    </ExpandableCard.Root>
  );
}

interface MCPServerCardProps {
  server: MCPServer;
  tools: MCPTool[];
  isLoading: boolean;
}

function MCPServerCard({
  server,
  tools: enabledTools,
  isLoading,
}: MCPServerCardProps) {
  const [isFolded, setIsFolded] = useState(false);
  const { values, setFieldValue, getFieldMeta } = useFormikContext<any>();
  const { t } = useTranslation();
  const serverFieldName = `mcp_server_${server.id}`;
  const isServerEnabled = values[serverFieldName]?.enabled ?? false;
  const {
    query,
    setQuery,
    filtered: filteredTools,
  } = useFilter(enabledTools, (tool) => `${tool.name} ${tool.description}`);

  // Calculate enabled and total tool counts
  const enabledCount = enabledTools.filter((tool) => {
    const toolFieldValue = values[serverFieldName]?.[`tool_${tool.id}`];
    return toolFieldValue === true;
  }).length;

  return (
    <ExpandableCard.Root isFolded={isFolded} onFoldedChange={setIsFolded}>
      <ActionsLayouts.Header
        title={server.name}
        description={server.description}
        icon={getActionIcon(server.server_url, server.name)}
        rightChildren={
          <GeneralLayouts.Section
            flexDirection="row"
            gap={0.5}
            alignItems="start"
          >
            <EnabledCount
              enabledCount={enabledCount}
              totalCount={enabledTools.length}
            />
            <SwitchField
              name={`${serverFieldName}.enabled`}
              onCheckedChange={(checked) => {
                enabledTools.forEach((tool) => {
                  setFieldValue(`${serverFieldName}.tool_${tool.id}`, checked);
                });
                if (!checked) return;
                setIsFolded(false);
              }}
            />
          </GeneralLayouts.Section>
        }
      >
        <GeneralLayouts.Section flexDirection="row" gap={0.5}>
          <InputTypeIn
            placeholder={t("agentEditor.searchToolsPlaceholder")}
            variant="internal"
            leftSearchIcon
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {enabledTools.length > 0 && (
            <Button
              internal
              rightIcon={isFolded ? SvgExpand : SvgFold}
              onClick={() => setIsFolded((prev) => !prev)}
            >
              {isFolded ? t("agentEditor.expandButton") : t("agentEditor.foldButton")}
            </Button>
          )}
        </GeneralLayouts.Section>
      </ActionsLayouts.Header>
      {isLoading ? (
        <ActionsLayouts.Content>
          <GeneralLayouts.Section padding={1}>
            <SimpleLoader />
          </GeneralLayouts.Section>
        </ActionsLayouts.Content>
      ) : (
        enabledTools.length > 0 &&
        filteredTools.length > 0 && (
          <ActionsLayouts.Content>
            {filteredTools.map((tool) => (
              <ActionsLayouts.Tool
                key={tool.id}
                name={`${serverFieldName}.tool_${tool.id}`}
                title={tool.name}
                description={tool.description}
                icon={tool.icon ?? SvgSliders}
                disabled={
                  !tool.isAvailable ||
                  !getFieldMeta<boolean>(`${serverFieldName}.enabled`).value
                }
                rightChildren={
                  <SwitchField
                    name={`${serverFieldName}.tool_${tool.id}`}
                    disabled={!isServerEnabled}
                  />
                }
              />
            ))}
          </ActionsLayouts.Content>
        )
      )}
    </ExpandableCard.Root>
  );
}

function StarterMessages() {
  const max_starters = STARTER_MESSAGES_EXAMPLES.length;
  const { t } = useTranslation();

  const { values } = useFormikContext<{
    starter_messages: string[];
  }>();

  const starters = values.starter_messages || [];

  // Count how many non-empty starters we have
  const filledStarters = starters.filter((s) => s).length;
  const canAddMore = filledStarters < max_starters;

  // Show at least 1, or all filled ones, or filled + 1 empty (up to max)
  const visibleCount = Math.min(
    max_starters,
    Math.max(
      1,
      filledStarters === 0 ? 1 : filledStarters + (canAddMore ? 1 : 0)
    )
  );

  return (
    <FieldArray name="starter_messages">
      {(arrayHelpers) => (
        <GeneralLayouts.Section gap={0.5}>
          {Array.from({ length: visibleCount }, (_, i) => (
            <InputTypeInElementField
              key={`starter_messages.${i}`}
              name={`starter_messages.${i}`}
              placeholder={
                STARTER_MESSAGES_EXAMPLES[i] ||
                t("agentEditor.enterConversationStarter")
              }
              onRemove={() => arrayHelpers.remove(i)}
            />
          ))}
        </GeneralLayouts.Section>
      )}
    </FieldArray>
  );
}

export interface AgentEditorPageProps {
  agent?: FullPersona;
  refreshAgent?: () => void;
}

const GRAPH_SCHEMA_CAPABILITIES: Record<string, { supports_tools: boolean; supports_rag: boolean }> = {
  zero_shot:    { supports_tools: false, supports_rag: false },
  react:        { supports_tools: true,  supports_rag: true  },
  supervisor:   { supports_tools: false, supports_rag: false },
  pipeline:     { supports_tools: true,  supports_rag: true  },
  plan_execute: { supports_tools: true,  supports_rag: true  },
  self_reflect: { supports_tools: false, supports_rag: false },
};

export default function AgentEditorPage({
  agent: existingAgent,
  refreshAgent,
}: AgentEditorPageProps) {
  const router = useRouter();
  const appRouter = useAppRouter();
  const { refresh: refreshAgents } = useAgents();
  const shareAgentModal = useCreateModal();
  const deleteAgentModal = useCreateModal();
  const settings = useSettingsContext();
  const { isAdmin, isCurator } = useUser();
  const { t } = useTranslation();
  const canUpdateFeaturedStatus = isAdmin || isCurator;
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;

  const GRAPH_SCHEMA_OPTIONS = useMemo(() => [
    { value: "zero_shot", label: t("agentEditor.strategyZeroShot") },
    { value: "react", label: t("agentEditor.strategyReAct") },
    { value: "supervisor", label: t("agentEditor.strategySupervisor") },
    { value: "pipeline", label: t("agentEditor.strategyPipeline") },
    { value: "plan_execute", label: t("agentEditor.strategyPlanExecute") },
    { value: "self_reflect", label: t("agentEditor.strategySelfReflect") },
  ], [t]);

  const BRAIN_TYPE_OPTIONS = useMemo(() => [
    { value: "llm", label: t("agentEditor.typeLLM") },
    { value: "guard", label: t("agentEditor.typeGuard") },
    { value: "multi_model", label: t("agentEditor.typeMultiModel") },
  ], [t]);

  const MEMORY_TYPE_OPTIONS = useMemo(() => [
    { value: "none", label: t("agentEditor.memoryNone") },
    { value: "long_term", label: t("agentEditor.memoryLongTerm") },
    { value: "buffer", label: t("agentEditor.memoryBuffer") },
  ], [t]);

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
  const { llmProviders } = useLLMProviders(existingAgent?.id);
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
  const searchTool = availableTools?.find(
    (t) => t.in_code_tool_id === SEARCH_TOOL_ID
  );
  const imageGenTool = availableTools?.find(
    (t) => t.in_code_tool_id === IMAGE_GENERATION_TOOL_ID
  );
  const webSearchTool = availableTools?.find(
    (t) => t.in_code_tool_id === WEB_SEARCH_TOOL_ID
  );
  const openURLTool = availableTools?.find(
    (t) => t.in_code_tool_id === OPEN_URL_TOOL_ID
  );
  const codeInterpreterTool = availableTools?.find(
    (t) => t.in_code_tool_id === PYTHON_TOOL_ID
  );
  const isImageGenerationAvailable = !!imageGenTool;
  const imageGenerationDisabledTooltip = isImageGenerationAvailable
    ? undefined
    : t("agentEditor.imageGenWarning");

  // Group MCP server tools from availableTools by server ID
  const mcpServersWithTools = mcpServers.map((server) => {
    const serverTools: MCPTool[] = (availableTools || [])
      .filter((tool) => tool.mcp_server_id === server.id)
      .map((tool) => ({
        id: tool.id.toString(),
        icon: getActionIcon(server.server_url, server.name),
        name: tool.display_name || tool.name,
        description: tool.description,
        isAvailable: true,
        isEnabled: tool.enabled,
      }));

    return { server, tools: serverTools, isLoading: false };
  });

  const allMcpTools = useMemo(() => {
    return mcpServersWithTools.flatMap(({ tools }) => tools);
  }, [mcpServersWithTools]);

  // Transform built-in tools for the form (parse and clean category tags)
  const allBuiltInTools = useMemo(() => {
    return builtInTools.map((tool) => {
      const parsed = parseToolCategory({
        name: tool.name,
        description: tool.description || "",
        input_schema: tool.input_schema || {},
      });
      return {
        name: tool.name,
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
    () => groupToolsByCategory(allBuiltInTools) as Record<string, (typeof allBuiltInTools[number])[]>,
    [allBuiltInTools]
  );

  const builtInCategoryLabelMap = useMemo(
    () => buildCategoryLabelMap(allBuiltInTools),
    [allBuiltInTools]
  );

  const sortedBuiltInCategories = useMemo(
    () =>
      Object.keys(builtInToolsByCategory).sort((a, b) => {
        if (a === "other") return 1;
        if (b === "other") return -1;
        return (builtInCategoryLabelMap[a] || _.startCase(a)).localeCompare(
          builtInCategoryLabelMap[b] || _.startCase(b)
        );
      }),
    [builtInToolsByCategory, builtInCategoryLabelMap]
  );

  const initialValues = {
    // General
    icon_name: existingAgent?.icon_name ?? null,
    uploaded_image_id: existingAgent?.uploaded_image_id ?? null,
    remove_image: false,
    name: existingAgent?.name ?? "",
    description: existingAgent?.description ?? "",
    
    // Base Agent Selection (only for custom agents - not built-in)
    base_agent: existingAgent?.base_agent ?? "chatbot",
    graph_schema: existingAgent?.graph_schema ?? "zero_shot",
    brain_type: (existingAgent as any)?.brain_type ?? "llm",
    memory_type: (existingAgent as any)?.memory_type ?? "none",

    // Prompts
    instructions: existingAgent?.system_prompt ?? "",
    starter_messages: Array.from(
      { length: STARTER_MESSAGES_EXAMPLES.length },
      (_, i) => existingAgent?.starter_messages?.[i]?.message ?? ""
    ),

    // Knowledge - enabled if agent has any RAG collections selected
    enable_knowledge:
      (existingAgent?.rag_config?.document_processing?.length ?? 0) > 0 ||
      (existingAgent?.rag_config?.knowledge_graph?.length ?? 0) > 0,
    rag_document_collection_ids: existingAgent?.rag_config?.document_processing ?? [],
    rag_graph_collection_ids: existingAgent?.rag_config?.knowledge_graph ?? [],

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
    // For new agents, default to false for optional tools to avoid
    // "Tool not available" errors when the tool isn't configured.
    // For existing agents, preserve the current tool configuration.
    image_generation:
      !!imageGenTool &&
      (existingAgent?.tools?.some(
        (tool) => tool.in_code_tool_id === IMAGE_GENERATION_TOOL_ID
      ) ??
        false),
    web_search:
      !!webSearchTool &&
      (existingAgent?.tools?.some(
        (tool) => tool.in_code_tool_id === WEB_SEARCH_TOOL_ID
      ) ??
        false),
    open_url:
      !!openURLTool &&
      (existingAgent?.tools?.some(
        (tool) => tool.in_code_tool_id === OPEN_URL_TOOL_ID
      ) ??
        false),
    code_interpreter:
      !!codeInterpreterTool &&
      (existingAgent?.tools?.some(
        (tool) => tool.in_code_tool_id === PYTHON_TOOL_ID
      ) ??
        false),
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
  };

  const validationSchema = Yup.object().shape({
    // General
    icon_name: Yup.string().nullable(),
    remove_image: Yup.boolean().optional(),
    uploaded_image_id: Yup.string().nullable(),
    name: Yup.string().required(t("agentEditor.agentNameRequired")),
    description: Yup.string()
      .max(
        MAX_CHARACTERS_AGENT_DESCRIPTION,
        t("agentEditor.descriptionMaxChars", { count: MAX_CHARACTERS_AGENT_DESCRIPTION })
      )
      .optional(),

    // Base Agent (only for custom agents)
    base_agent: Yup.string().oneOf(["chatbot", "configurable-mcp-agent", "dynamic-agent"]),
      graph_schema: Yup.string().oneOf(GRAPH_SCHEMA_OPTIONS.map((option) => option.value)),
      brain_type: Yup.string().oneOf(BRAIN_TYPE_OPTIONS.map((option) => option.value)),
      memory_type: Yup.string().oneOf(MEMORY_TYPE_OPTIONS.map((option) => option.value)),

    // Prompts
    instructions: Yup.string().optional(),
    starter_messages: Yup.array().of(
      Yup.string().max(
        MAX_CHARACTERS_STARTER_MESSAGE,
        t("agentEditor.starterMaxChars", { count: MAX_CHARACTERS_STARTER_MESSAGE })
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

    // MCP tools (from external MCP servers)
    ...Object.fromEntries(
      allMcpTools.map((tool) => [`mcp_tool_${tool.name}`, Yup.boolean().optional()])
    ),

    // Built-in tools from tools-service
    ...Object.fromEntries(
      allBuiltInTools.map((tool) => [`builtin_tool_${tool.name}`, Yup.boolean().optional()])
    ),

    // OpenAPI tools
    ...Object.fromEntries(
      openApiTools.map((tool) => [`openapi_tool_${tool.id}`, Yup.boolean().optional()])
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
      if (values.image_generation && imageGenTool) {
        toolIds.push(imageGenTool.id);
      }
      if (values.web_search && webSearchTool) {
        toolIds.push(webSearchTool.id);
      }
      if (values.open_url && openURLTool) {
        toolIds.push(openURLTool.id);
      }
      if (values.code_interpreter && codeInterpreterTool) {
        toolIds.push(codeInterpreterTool.id);
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
      const dynamicLikeAgent = ["configurable-mcp-agent", "dynamic-agent"].includes(
        values.base_agent
      );

      if (dynamicLikeAgent) {
        allMcpTools.forEach((tool) => {
          if ((values as any)[`mcp_tool_${tool.name}`] === true) {
            enabledMcpToolNames.push(tool.name);
          }
        });
      }

      // Collect enabled built-in tools from tools-service
      if (dynamicLikeAgent) {
        allBuiltInTools.forEach((tool) => {
          if ((values as any)[`builtin_tool_${tool.name}`] === true) {
            enabledMcpToolNames.push(tool.name);
          }
        });
      }

      // Keep dynamic-agent actions compatible with configurable-mcp-agent behavior
      if (values.base_agent === "dynamic-agent") {
        if (values.enable_knowledge && searchTool?.name) enabledMcpToolNames.push(searchTool.name);
        if (values.image_generation && imageGenTool?.name) enabledMcpToolNames.push(imageGenTool.name);
        if (values.web_search && webSearchTool?.name) enabledMcpToolNames.push(webSearchTool.name);
        if (values.open_url && openURLTool?.name) enabledMcpToolNames.push(openURLTool.name);
        if (values.code_interpreter && codeInterpreterTool?.name) enabledMcpToolNames.push(codeInterpreterTool.name);
      }

      const dedupedMcpToolNames = Array.from(new Set(enabledMcpToolNames));

      // Build rag_config from selected collections
      const hasKnowledge =
        values.enable_knowledge &&
        (values.rag_document_collection_ids.length > 0 ||
          values.rag_graph_collection_ids.length > 0);

      const ragConfig = hasKnowledge
        ? {
            document_processing: values.rag_document_collection_ids,
            knowledge_graph: values.rag_graph_collection_ids,
          }
        : undefined;

      // Auto-promote base_agent when knowledge is enabled
      const effectiveBaseAgent =
        hasKnowledge && values.base_agent === "chatbot"
          ? "configurable-mcp-agent"
          : values.base_agent || "chatbot";

      if (effectiveBaseAgent === "dynamic-agent") {
        const dynamicGraphSchema =
          values.graph_schema === "zero_shot" && (dedupedMcpToolNames.length > 0 || hasKnowledge)
            ? "react"
            : values.graph_schema;

        const dynamicAgentId = existingAgent?.external_id ?? null;
        const dynamicMethod = dynamicAgentId ? "PUT" : "POST";
        const dynamicEndpoint = dynamicAgentId
          ? `/api/agent-definitions/${dynamicAgentId}`
          : "/api/agent-definitions";

        const dynamicResponse = await fetch(dynamicEndpoint, {
          method: dynamicMethod,
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: values.name,
            description: values.description || null,
            graph_schema: dynamicGraphSchema,
            brain_type: values.brain_type,
            memory_type: values.memory_type,
            system_prompt: values.instructions || null,
            model: values.llm_model_version_override || null,
            mcp_tools: dedupedMcpToolNames,
            rag_config:
              ragConfig ?? {
                document_processing: [],
                knowledge_graph: [],
              },
            tags: [],
          }),
        });

        if (!dynamicResponse.ok) {
          const errorText = await dynamicResponse.text();
          toast.error(
            `${t("agentEditor.failedToDynamicAgent", { action: dynamicAgentId ? t("agentEditor.actionUpdate") : t("agentEditor.actionCreate") })} - ${errorText}`
          );
          return;
        }

        const createdDynamicAgent = await dynamicResponse.json();
        toast.success(
          `${t("agentEditor.agentSuccess", { name: createdDynamicAgent.name, action: dynamicAgentId ? t("agentEditor.actionUpdated") : t("agentEditor.actionCreated") })}`
        );
        await refreshAgents();
        appRouter({ agentId: createdDynamicAgent.id });
        return;
      }

      // Build submission data
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
        mcp_tools: dedupedMcpToolNames,
      };

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
          `${t("agentEditor.failedToAgent", { action: existingAgent ? t("agentEditor.actionUpdate") : t("agentEditor.actionCreate") })} - ${error}`
        );
        return;
      }

      // Success
      const agent = await personaResponse.json();
      toast.success(
        `${t("agentEditor.agentSuccess", { name: agent.name, action: existingAgent ? t("agentEditor.actionUpdated") : t("agentEditor.actionCreated") })}`
      );

      // Refresh agents list and the specific agent
      await refreshAgents();
      if (refreshAgent) {
        refreshAgent();
      }

      // Immediately start a chat with this agent.
      appRouter({ agentId: agent.id });
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

  // Wait for async tool data before rendering the form. Formik captures
  // initialValues on mount — if tools haven't loaded yet, the initial values
  // won't include MCP tool fields. Later, toggling those fields would make
  // the form permanently dirty since they have no baseline to compare against.
  if (isToolsLoading || isMcpLoading || isOpenApiLoading) {
    return null;
  }

  return (
    <>
      <div
        data-testid="AgentsEditorPage/container"
        aria-label="Agents Editor Page"
        className="h-full w-full"
      >
        <Formik
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
            const schemaCapabilities = isDynamicAgent
              ? (GRAPH_SCHEMA_CAPABILITIES[values.graph_schema] ?? { supports_tools: true, supports_rag: true })
              : null;
            const schemaSupportsTools = !isDynamicAgent || (schemaCapabilities?.supports_tools ?? true);
            const schemaSupportsRag = !isDynamicAgent || (schemaCapabilities?.supports_rag ?? true);

            return (
              <>
                <FormWarningsEffect />

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
                        <Text>
                          {t("agentEditor.deleteAgentConfirmText")}
                        </Text>
                        <Text>{t("agentEditor.deleteAgentAreYouSure")}</Text>
                      </GeneralLayouts.Section>
                    </ConfirmationModalLayout>
                  )}
                </deleteAgentModal.Provider>

                <Form className="h-full w-full">
                  <SettingsLayouts.Root>
                    <SettingsLayouts.Header
                      icon={SvgOnyxOctagon}
                      title={existingAgent ? t("agentEditor.editAgentTitle") : t("agentEditor.createAgentTitle")}
                      rightChildren={
                        <div className="flex gap-2">
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
                              !dirty
                            }
                          >
                            {existingAgent ? t("agentEditor.saveButton") : t("agentEditor.createButton")}
                          </Button>
                        </div>
                      }
                      backButton
                      separator
                    />

                    {/* Agent Form Content */}
                    <SettingsLayouts.Body>
                      <GeneralLayouts.Section
                        flexDirection="row"
                        gap={2.5}
                        alignItems="start"
                      >
                        <GeneralLayouts.Section>
                          <InputLayouts.Vertical name="name" title={t("agentEditor.nameLabel")}>
                            <InputTypeInField
                              name="name"
                              placeholder={t("agentEditor.agentNamePlaceholder")}
                            />
                          </InputLayouts.Vertical>

                          <InputLayouts.Vertical
                            name="description"
                            title={`${t("agentEditor.descriptionLabel")} (${t("agentEditor.optionalLabel")})`}
                          >
                            <InputTextAreaField
                              name="description"
                              placeholder={t("agentEditor.agentDescriptionPlaceholder")}
                            />
                          </InputLayouts.Vertical>

                          <InputLayouts.Vertical
                            name="base_agent"
                            title={t("agentEditor.baseAgentLabel")}
                            description={t("agentEditor.baseAgentDescription")}
                          >
                            <InputSelectField
                              name="base_agent"
                            >
                              <InputSelect.Trigger placeholder={t("agentEditor.selectBaseAgentPlaceholder")} />
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
                            <>
                              <InputLayouts.Vertical
                                name="graph_schema"
                                title={t("agentEditor.graphSchemaLabel")}
                                description={t("agentEditor.graphSchemaDescription")}
                              >
                                <InputSelectField name="graph_schema">
                                  <InputSelect.Trigger placeholder={t("agentEditor.selectGraphSchemaPlaceholder")} />
                                  <InputSelect.Content>
                                    {GRAPH_SCHEMA_OPTIONS.map((option) => (
                                      <InputSelect.Item key={option.value} value={option.value}>
                                        {option.label}
                                      </InputSelect.Item>
                                    ))}
                                  </InputSelect.Content>
                                </InputSelectField>
                              </InputLayouts.Vertical>

                              <InputLayouts.Vertical
                                name="brain_type"
                                title={t("agentEditor.brainTypeLabel")}
                              >
                                <InputSelectField name="brain_type">
                                  <InputSelect.Trigger placeholder={t("agentEditor.selectBrainTypePlaceholder")} />
                                  <InputSelect.Content>
                                    {BRAIN_TYPE_OPTIONS.map((option) => (
                                      <InputSelect.Item key={option.value} value={option.value}>
                                        {option.label}
                                      </InputSelect.Item>
                                    ))}
                                  </InputSelect.Content>
                                </InputSelectField>
                              </InputLayouts.Vertical>

                              <InputLayouts.Vertical
                                name="memory_type"
                                title={t("agentEditor.memoryTypeLabel")}
                              >
                                <InputSelectField name="memory_type">
                                  <InputSelect.Trigger placeholder={t("agentEditor.selectMemoryTypePlaceholder")} />
                                  <InputSelect.Content>
                                    {MEMORY_TYPE_OPTIONS.map((option) => (
                                      <InputSelect.Item key={option.value} value={option.value}>
                                        {option.label}
                                      </InputSelect.Item>
                                    ))}
                                  </InputSelect.Content>
                                </InputSelectField>
                              </InputLayouts.Vertical>
                            </>
                          )}
                        </GeneralLayouts.Section>

                        <GeneralLayouts.Section width="fit">
                          <InputLayouts.Vertical
                            name="agent_avatar"
                            title={t("agentEditor.agentAvatarLabel")}
                          >
                            <AgentIconEditor existingAgent={existingAgent} />
                          </InputLayouts.Vertical>
                        </GeneralLayouts.Section>
                      </GeneralLayouts.Section>

                      <Separator noPadding />

                      <GeneralLayouts.Section>
                        <InputLayouts.Vertical
                          name="instructions"
                          title={`${t("agentEditor.instructionsLabel")} (${t("agentEditor.optionalLabel")})`}
                          description={t("agentEditor.instructionsDescription")}
                        >
                          <InputTextAreaField
                            name="instructions"
                            placeholder={t("agentEditor.instructionsPlaceholder")}
                          />
                        </InputLayouts.Vertical>

                        <InputLayouts.Vertical
                          name="starter_messages"
                          description={t("agentEditor.conversationStartersDescription")}
                          title={`${t("agentEditor.conversationStartersLabel")} (${t("agentEditor.optionalLabel")})`}
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
                            ragDocumentCollectionIds={values.rag_document_collection_ids}
                            onDocumentCollectionIdsChange={(ids) =>
                              setFieldValue("rag_document_collection_ids", ids)
                            }
                            ragGraphCollectionIds={values.rag_graph_collection_ids}
                            onGraphCollectionIdsChange={(ids) =>
                              setFieldValue("rag_graph_collection_ids", ids)
                            }
                          />

                          <Separator noPadding />
                        </>
                      )}

                      {schemaSupportsTools && (
                      <SimpleCollapsible>
                        <SimpleCollapsible.Header
                          title={t("agentEditor.actionsLabel")}
                          description={t("agentEditor.actionsDescription")}
                        />
                        <SimpleCollapsible.Content>
                          <GeneralLayouts.Section gap={0.5}>
                            <SimpleTooltip
                              tooltip={imageGenerationDisabledTooltip}
                              side="top"
                            >
                              <Card
                                variant={
                                  isImageGenerationAvailable
                                    ? undefined
                                    : "disabled"
                                }
                              >
                                <InputLayouts.Horizontal
                                  name="image_generation"
                                  title={t("agentEditor.imageGenerationLabel")}
                                  description={t("agentEditor.imageGenerationDescription")}
                                  disabled={!isImageGenerationAvailable}
                                >
                                  <SwitchField
                                    name="image_generation"
                                    disabled={!isImageGenerationAvailable}
                                  />
                                </InputLayouts.Horizontal>
                              </Card>
                            </SimpleTooltip>

                            <Card
                              variant={!!webSearchTool ? undefined : "disabled"}
                            >
                              <InputLayouts.Horizontal
                                name="web_search"
                                title={t("agentEditor.webSearchLabel")}
                                description={t("agentEditor.webSearchDescription")}
                                disabled={!webSearchTool}
                              >
                                <SwitchField
                                  name="web_search"
                                  disabled={!webSearchTool}
                                />
                              </InputLayouts.Horizontal>
                            </Card>

                            <Card
                              variant={!!openURLTool ? undefined : "disabled"}
                            >
                              <InputLayouts.Horizontal
                                name="open_url"
                                title={t("agentEditor.openURLLabel")}
                                description={t("agentEditor.openURLDescription")}
                                disabled={!openURLTool}
                              >
                                <SwitchField
                                  name="open_url"
                                  disabled={!openURLTool}
                                />
                              </InputLayouts.Horizontal>
                            </Card>

                            <Card
                              variant={
                                !!codeInterpreterTool ? undefined : "disabled"
                              }
                            >
                              <InputLayouts.Horizontal
                                name="code_interpreter"
                                title={t("agentEditor.codeInterpreterLabel")}
                                description={t("agentEditor.codeInterpreterDescription")}
                                disabled={!codeInterpreterTool}
                              >
                                <SwitchField
                                  name="code_interpreter"
                                  disabled={!codeInterpreterTool}
                                />
                              </InputLayouts.Horizontal>
                            </Card>

                            {/* Tools */}
                            <>
                              {/* render the separator if there is at least one mcp-server or open-api-tool */}
                              {(mcpServers.length > 0 ||
                                openApiTools.length > 0) && (
                                <Separator noPadding className="py-1" />
                              )}

                              {/* MCP tools (from external MCP servers) - only show when configurable-mcp-agent is selected */}
                              {["configurable-mcp-agent", "dynamic-agent"].includes(values.base_agent) && allMcpTools.length > 0 && (
                                <GeneralLayouts.Section gap={0.5}>
                                  <Text mainUiBody>{t("agentEditor.externalMcpTools")}</Text>
                                  {allMcpTools.map((tool) => (
                                    <Card
                                      key={tool.name}
                                      variant={tool.isAvailable ? undefined : "disabled"}
                                    >
                                      <InputLayouts.Horizontal
                                        name={`mcp_tool_${tool.name}`}
                                        title={tool.name}
                                        description={tool.description}
                                        disabled={!tool.isAvailable}
                                      >
                                        <SwitchField
                                          name={`mcp_tool_${tool.name}`}
                                          disabled={!tool.isAvailable}
                                        />
                                      </InputLayouts.Horizontal>
                                    </Card>
                                  ))}
                                </GeneralLayouts.Section>
                              )}

                              {/* Built-in tools from tools-service - only show when configurable-mcp-agent is selected */}
                              {["configurable-mcp-agent", "dynamic-agent"].includes(values.base_agent) && allBuiltInTools.length > 0 && (
                                <GeneralLayouts.Section gap={0.5}>
                                  <Text mainUiBody>{t("agentEditor.toolsServiceLabel")}</Text>
                                  <div className="max-h-96 overflow-y-auto space-y-4 pr-1">
                                    {sortedBuiltInCategories.map((category) => (
                                      <div key={category}>
                                        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 px-1">
                                          {builtInCategoryLabelMap[category] || _.startCase(category)}
                                        </div>
                                        {(builtInToolsByCategory[category] ?? []).map((tool) => (
                                          <Card
                                            key={tool.name}
                                            variant={tool.isAvailable ? undefined : "disabled"}
                                          >
                                            <InputLayouts.Horizontal
                                              name={`builtin_tool_${tool.name}`}
                                              title={_.startCase(tool.name)}
                                              description={tool.description}
                                              disabled={!tool.isAvailable}
                                            >
                                              <SwitchField
                                                name={`builtin_tool_${tool.name}`}
                                                disabled={!tool.isAvailable}
                                              />
                                            </InputLayouts.Horizontal>
                                          </Card>
                                        ))}
                                      </div>
                                    ))}
                                  </div>
                                </GeneralLayouts.Section>
                              )}

                              {/* OpenAPI tools */}
                              {openApiTools.length > 0 && (
                                <GeneralLayouts.Section gap={0.5}>
                                  {openApiTools.map((tool) => (
                                    <OpenApiToolCard
                                      key={tool.id}
                                      tool={tool}
                                    />
                                  ))}
                                </GeneralLayouts.Section>
                              )}
                            </>
                          </GeneralLayouts.Section>
                        </SimpleCollapsible.Content>
                      </SimpleCollapsible>
                      )}

                      <Separator noPadding />

                      <SimpleCollapsible>
                        <SimpleCollapsible.Header
                          title={t("agentEditor.advancedOptionsLabel")}
                          description={t("agentEditor.advancedOptionsDescription")}
                        />
                        <SimpleCollapsible.Content>
                          <GeneralLayouts.Section>
                            <Card>
                              <InputLayouts.Horizontal
                                title={t("agentEditor.shareThisAgentLabel")}
                                description={t("agentEditor.shareThisAgentDescription")}
                                center
                              >
                                <Button
                                  secondary
                                  leftIcon={isShared ? SvgUsers : SvgLock}
                                  onClick={() => shareAgentModal.toggle(true)}
                                >
                                  {t("agentEditor.shareButton")}
                                </Button>
                              </InputLayouts.Horizontal>
                              {canUpdateFeaturedStatus && (
                                <>
                                  <InputLayouts.Horizontal
                                    name="featured"
                                    title={t("agentEditor.featureThisAgentLabel")}
                                    description={t("agentEditor.featureThisAgentDescription")}
                                  >
                                    <SwitchField name="featured" />
                                  </InputLayouts.Horizontal>
                                  {values.featured && !isShared && (
                                    <Message
                                      static
                                      close={false}
                                      className="w-full"
                                      text={t("agentEditor.agentPrivateWarning")}
                                    />
                                  )}
                                </>
                              )}
                            </Card>

                            <Card>
                              <InputLayouts.Horizontal
                                name="llm_model"
                                title={t("agentEditor.defaultModelLabel")}
                                description={t("agentEditor.defaultModelDescription")}
                              >
                                <LLMSelector
                                  name="llm_model"
                                  llmProviders={llmProviders ?? []}
                                  currentLlm={getCurrentLlm(
                                    values,
                                    llmProviders
                                  )}
                                  onSelect={(selected) =>
                                    onLlmSelect(selected, setFieldValue)
                                  }
                                />
                              </InputLayouts.Horizontal>
                              <InputLayouts.Horizontal
                                name="knowledge_cutoff_date"
                                title={t("agentEditor.knowledgeCutoffLabel")}
                                description={t("agentEditor.knowledgeCutoffDescription")}
                              >
                                <InputDatePickerField name="knowledge_cutoff_date" />
                              </InputLayouts.Horizontal>
                              <InputLayouts.Horizontal
                                name="replace_base_system_prompt"
                                title={t("agentEditor.overwritePromptLabel")}
                                description={t("agentEditor.overwritePromptDescription")}
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
                                  placeholder={t("agentEditor.remindersPlaceholder")}
                                />
                              </InputLayouts.Vertical>
                              <Text text03 secondaryBody>
                                {t("agentEditor.remindersHint")}
                              </Text>
                            </GeneralLayouts.Section>
                          </GeneralLayouts.Section>
                        </SimpleCollapsible.Content>
                      </SimpleCollapsible>

                      {existingAgent && (
                        <>
                          <Separator noPadding />

                          <Card>
                            <InputLayouts.Horizontal
                              title={t("agentEditor.deleteThisAgentLabel")}
                              description={t("agentEditor.deleteThisAgentDescription")}
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
