"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { errorHandlingFetcher, authenticatedFetch } from "@/lib/fetcher";
import { useAvailableTools } from "@/hooks/useAvailableTools";
import useBuiltInTools from "@/hooks/useBuiltInTools";
import useMcpServersForAgentEditor from "@/hooks/useMcpServersForAgentEditor";
import { useAgents } from "@/hooks/useAgents";
import { useAppRouter } from "@/hooks/appNavigation";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import McpToolSelectionCard, {
  buildMcpOnlyToolSelectionGroups,
  buildToolSelectionGroups,
  flattenGroupTools,
  toSelectableTool,
} from "@/refresh-components/agents/McpToolSelectionCard";
import {
  buildCategoryLabelMap,
  groupToolsByCategory,
  parseToolCategory,
} from "@/lib/tools/builtInToolUtils";
import { useTranslation } from "react-i18next";

interface GraphSchemaInfo {
  schema_type: string;
  description: string;
  supports_memory: boolean;
  supports_tools: boolean;
  supports_sub_agents: boolean;
  is_multi_step: boolean;
}

interface BrainTypeInfo {
  brain_type: string;
  description: string;
}

interface MemoryTypeInfo {
  memory_type: string;
  description: string;
}

function parseJsonArray(
  raw: string,
  fieldName: string,
  t: (key: string, options?: any) => string
) {
  if (!raw.trim()) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error(
        t("agentEditor.dynamic.jsonArrayError", { field: fieldName })
      );
    }
    return parsed;
  } catch (error) {
    if (error instanceof Error && error.message.includes("JSON array")) {
      throw error;
    }
    throw new Error(
      t("agentEditor.dynamic.jsonValidError", { field: fieldName })
    );
  }
}

export default function DynamicAgentEditorPage() {
  const { t } = useTranslation();
  const { refresh: refreshAgents } = useAgents();
  const { tools, isLoading: isToolsLoading } = useAvailableTools();
  const { tools: builtInTools, isLoading: isBuiltInToolsLoading } =
    useBuiltInTools();
  const { mcpData, isLoading: isMcpLoading } = useMcpServersForAgentEditor();
  const appRouter = useAppRouter();

  const { data: schemas } = useSWR<GraphSchemaInfo[]>(
    "/api/agent-definitions/schemas/list",
    errorHandlingFetcher
  );
  const { data: brains } = useSWR<BrainTypeInfo[]>(
    "/api/agent-definitions/brains/list",
    errorHandlingFetcher
  );
  const { data: memoryTypes } = useSWR<MemoryTypeInfo[]>(
    "/api/agent-definitions/memory/list",
    errorHandlingFetcher
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [graphSchema, setGraphSchema] = useState("zero_shot");
  const [brainType, setBrainType] = useState("llm");
  const [memoryType, setMemoryType] = useState("none");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [model, setModel] = useState("");
  const [supervisorPrompt, setSupervisorPrompt] = useState("");
  const [pipelinePrompt, setPipelinePrompt] = useState("");
  const [reflectionPrompt, setReflectionPrompt] = useState("");
  const [maxIterations, setMaxIterations] = useState("3");
  const [subAgentsJson, setSubAgentsJson] = useState("[]");
  const [stagesJson, setStagesJson] = useState("[]");
  const [selectedTools, setSelectedTools] = useState<Record<string, boolean>>(
    {}
  );

  const selectedSchema = useMemo(
    () => schemas?.find((schema) => schema.schema_type === graphSchema),
    [schemas, graphSchema]
  );
  const toolGroups = useMemo(() => {
    const externalMcpGroups = buildMcpOnlyToolSelectionGroups({
      tools: tools.map(toSelectableTool),
      mcpServers: mcpData?.mcp_servers ?? [],
    });
    const serviceTools = builtInTools.map((tool) => {
      const parsed = parseToolCategory({
        name: tool.name,
        description: tool.description || "",
        input_schema: tool.input_schema || {},
      });
      return {
        name: parsed.name,
        display_name: parsed.name,
        description: parsed.description,
        enabled: true,
        agent_creation_selectable: true,
        category: parsed.category,
        categoryLabel: parsed.categoryLabel,
        input_schema: parsed.input_schema,
      };
    });

    const builtInCategoryGroups = buildToolSelectionGroups({
      serviceToolsByCategory: groupToolsByCategory(serviceTools),
      categoryLabelMap: buildCategoryLabelMap(serviceTools),
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

    return [...externalMcpGroups, ...builtInRoot];
  }, [builtInTools, mcpData?.mcp_servers, tools, t]);
  const selectedToolNames = useMemo(
    () =>
      Object.entries(selectedTools)
        .filter(([, enabled]) => enabled)
        .map(([toolName]) => toolName),
    [selectedTools]
  );

  async function handleSubmit() {
    if (!name.trim()) {
      toast.error(t("agentEditor.agentNameRequired"));
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await authenticatedFetch("/api/agent-definitions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          graph_schema: graphSchema,
          brain_type: brainType,
          memory_type: memoryType,
          system_prompt: systemPrompt.trim() || null,
          model: model.trim() || null,
          mcp_tools: Object.entries(selectedTools)
            .filter(([, enabled]) => enabled)
            .map(([toolName]) => toolName),
          sub_agents: parseJsonArray(
            subAgentsJson,
            t("agentEditor.dynamic.subAgentsField"),
            t
          ),
          supervisor_prompt: supervisorPrompt.trim() || null,
          stages: parseJsonArray(
            stagesJson,
            t("agentEditor.dynamic.stagesField"),
            t
          ),
          pipeline_prompt: pipelinePrompt.trim() || null,
          reflection_prompt: reflectionPrompt.trim() || null,
          max_iterations: Number.parseInt(maxIterations, 10) || 3,
          tags: [],
        }),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const created = await response.json();
      await refreshAgents();
      toast.success(
        t("agentEditor.agentSuccess", {
          name: created.name,
          action: t("agentEditor.actionCreated"),
        })
      );
      appRouter({ agentId: created.id });
    } catch (error) {
      console.error("Dynamic agent create failed", error);
      toast.error(
        error instanceof Error
          ? error.message
          : t("agentEditor.dynamic.createFailed")
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 w-full max-w-4xl p-4">
      <div className="flex flex-col gap-2">
        <Text as="p" headingH2>
          {t("agentEditor.dynamic.createTitle")}
        </Text>
        <Text as="p" secondaryBody>
          {t("agentEditor.dynamic.createSubtitle")}
        </Text>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Text as="p" secondaryBody>
            {t("agentEditor.nameLabel")}
          </Text>
          <InputTypeIn
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Text as="p" secondaryBody>
            {t("agentEditor.dynamic.modelOverrideLabel")}
          </Text>
          <InputTypeIn
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder={t("agentEditor.optionalLabel")}
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Text as="p" secondaryBody>
          {t("agentEditor.descriptionLabel")}
        </Text>
        <InputTextArea
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="flex flex-col gap-2">
          <Text as="p" secondaryBody>
            {t("agentEditor.graphSchemaLabel")}
          </Text>
          <InputSelect value={graphSchema} onValueChange={setGraphSchema}>
            <InputSelect.Trigger
              placeholder={t("agentEditor.selectGraphSchemaPlaceholder")}
            />
            <InputSelect.Content>
              {(schemas ?? []).map((schema) => (
                <InputSelect.Item
                  key={schema.schema_type}
                  value={schema.schema_type}
                >
                  {schema.schema_type}
                </InputSelect.Item>
              ))}
            </InputSelect.Content>
          </InputSelect>
        </div>
        <div className="flex flex-col gap-2">
          <Text as="p" secondaryBody>
            {t("agentEditor.brainTypeLabel")}
          </Text>
          <InputSelect value={brainType} onValueChange={setBrainType}>
            <InputSelect.Trigger
              placeholder={t("agentEditor.selectBrainTypePlaceholder")}
            />
            <InputSelect.Content>
              {(brains ?? []).map((brain) => (
                <InputSelect.Item
                  key={brain.brain_type}
                  value={brain.brain_type}
                >
                  {brain.brain_type}
                </InputSelect.Item>
              ))}
            </InputSelect.Content>
          </InputSelect>
        </div>
        <div className="flex flex-col gap-2">
          <Text as="p" secondaryBody>
            {t("agentEditor.memoryTypeLabel")}
          </Text>
          <InputSelect value={memoryType} onValueChange={setMemoryType}>
            <InputSelect.Trigger
              placeholder={t("agentEditor.selectMemoryTypePlaceholder")}
            />
            <InputSelect.Content>
              {(memoryTypes ?? []).map((memory) => (
                <InputSelect.Item
                  key={memory.memory_type}
                  value={memory.memory_type}
                >
                  {memory.memory_type}
                </InputSelect.Item>
              ))}
            </InputSelect.Content>
          </InputSelect>
        </div>
      </div>

      {selectedSchema && (
        <Text as="p" secondaryBody>
          {selectedSchema.description}
        </Text>
      )}

      <div className="flex flex-col gap-2">
        <Text as="p" secondaryBody>
          {t("agentEditor.instructionsLabel")}
        </Text>
        <InputTextArea
          rows={6}
          value={systemPrompt}
          onChange={(event) => setSystemPrompt(event.target.value)}
        />
      </div>

      {selectedSchema?.supports_tools && (
        <McpToolSelectionCard
          title={t("agentEditor.actionsLabel")}
          description={t(
            "agentEditor.dynamic.mcpToolsDescription",
            "Choose the tools this dynamic agent can call."
          )}
          groups={toolGroups}
          selectedToolNames={selectedToolNames}
          onSelectedToolNamesChange={(toolNames) => {
            const next = new Set(toolNames);
            setSelectedTools(
              Object.fromEntries(
                flattenGroupTools(toolGroups).map((tool) => [
                  tool.name,
                  next.has(tool.name),
                ])
              )
            );
          }}
          isLoading={isToolsLoading || isBuiltInToolsLoading || isMcpLoading}
        />
      )}

      {graphSchema === "supervisor" && (
        <>
          <div className="flex flex-col gap-2">
            <Text as="p" secondaryBody>
              {t("agentEditor.dynamic.supervisorPromptLabel")}
            </Text>
            <InputTextArea
              rows={4}
              value={supervisorPrompt}
              onChange={(event) => setSupervisorPrompt(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Text as="p" secondaryBody>
              {t("agentEditor.dynamic.subAgentsJsonLabel")}
            </Text>
            <InputTextArea
              rows={8}
              value={subAgentsJson}
              onChange={(event) => setSubAgentsJson(event.target.value)}
            />
          </div>
        </>
      )}

      {graphSchema === "pipeline" && (
        <>
          <div className="flex flex-col gap-2">
            <Text as="p" secondaryBody>
              {t("agentEditor.dynamic.pipelinePromptLabel")}
            </Text>
            <InputTextArea
              rows={4}
              value={pipelinePrompt}
              onChange={(event) => setPipelinePrompt(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Text as="p" secondaryBody>
              {t("agentEditor.dynamic.stagesJsonLabel")}
            </Text>
            <InputTextArea
              rows={8}
              value={stagesJson}
              onChange={(event) => setStagesJson(event.target.value)}
            />
          </div>
        </>
      )}

      {graphSchema === "self_reflect" && (
        <>
          <div className="flex flex-col gap-2">
            <Text as="p" secondaryBody>
              {t("agentEditor.dynamic.reflectionPromptLabel")}
            </Text>
            <InputTextArea
              rows={4}
              value={reflectionPrompt}
              onChange={(event) => setReflectionPrompt(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2 max-w-xs">
            <Text as="p" secondaryBody>
              {t("agentEditor.dynamic.maxIterationsLabel")}
            </Text>
            <InputTypeIn
              value={maxIterations}
              onChange={(event) => setMaxIterations(event.target.value)}
            />
          </div>
        </>
      )}

      <div>
        <Button main onClick={handleSubmit} disabled={isSubmitting}>
          {isSubmitting
            ? t("agentEditor.dynamic.creatingAgent")
            : t("agentEditor.dynamic.createAgent")}
        </Button>
      </div>
    </div>
  );
}
