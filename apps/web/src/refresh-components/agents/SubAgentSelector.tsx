/**
 * SubAgentSelector Component
 * Compact summary + modal workspace for configuring sub-agents.
 */

"use client";

import { useMemo, useState } from "react";
import { useFormikContext } from "formik";
import { useTranslation } from "react-i18next";
import { useAvailableAgents } from "@/hooks/useAvailableAgents";
import Button from "@/refresh-components/buttons/Button";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { Card } from "@/refresh-components/cards";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import SquareButton from "@/refresh-components/buttons/SquareButton";
import * as InputLayouts from "@/layouts/input-layouts";
import {
  SvgArrowUpDot,
  SvgCheck,
  SvgNetworkGraph,
  SvgPlus,
  SvgSliders,
  SvgTrash,
} from "@opal/icons";

interface AvailableAgent {
  id: string;
  name: string;
  graph_schema: string;
  depth: number;
  status: "active" | "inactive";
}

export interface SubAgentConfiguration {
  agent_id: string;
  name: string;
  role: string;
  system_prompt: string;
  mcp_tools: string[];
  model: string | null;
}

interface SubAgentSelectorProps {
  graphSchema: string;
  onError?: (error: string) => void;
}

interface AgentEditorCompositionValues {
  sub_agent_ids?: string[];
  sub_agents?: SubAgentConfiguration[];
  stages?: SubAgentConfiguration[];
}

function getCompositionField(graphSchema: string) {
  return graphSchema === "pipeline" ? "stages" : "sub_agents";
}

function buildDefaultInstruction(agentName: string, role: string) {
  return `You are ${agentName}. Work as the ${role} and complete only the part of the task that matches this responsibility.`;
}

function createConfig(
  agent: AvailableAgent,
  graphSchema: string,
  index: number
): SubAgentConfiguration {
  const role =
    graphSchema === "pipeline" ? `stage_${index + 1}` : "specialist";

  return {
    agent_id: agent.id,
    name: role,
    role,
    system_prompt: buildDefaultInstruction(agent.name, role),
    mcp_tools: [],
    model: null,
  };
}

function normalizeConfig(
  config: Partial<SubAgentConfiguration>,
  agent: AvailableAgent | undefined,
  graphSchema: string,
  index: number
): SubAgentConfiguration {
  const role =
    config.role?.trim() ||
    config.name?.trim() ||
    (graphSchema === "pipeline" ? `stage_${index + 1}` : "specialist");
  const displayName = agent?.name ?? role;

  return {
    agent_id: config.agent_id ?? agent?.id ?? "",
    name: role,
    role,
    system_prompt:
      config.system_prompt?.trim() ||
      buildDefaultInstruction(displayName, role),
    mcp_tools: config.mcp_tools ?? [],
    model: config.model ?? null,
  };
}

function formatAgentMeta(agent: AvailableAgent) {
  return agent.graph_schema;
}

export default function SubAgentSelector({
  graphSchema,
  onError,
}: SubAgentSelectorProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const { values, setFieldValue } =
    useFormikContext<AgentEditorCompositionValues>();
  const compositionField = getCompositionField(graphSchema);

  const { agents, isLoading, error } = useAvailableAgents({
    schema: graphSchema,
    enabled: graphSchema === "supervisor" || graphSchema === "pipeline",
  });

  const subAgentIds = values.sub_agent_ids ?? [];
  const currentConfigs = (values[compositionField] ??
    []) as SubAgentConfiguration[];

  const selectedAgents = useMemo(() => {
    const agentMap = new Map(agents.map((agent) => [agent.id, agent]));
    return subAgentIds
      .map((agentId) => agentMap.get(agentId))
      .filter((agent): agent is AvailableAgent => Boolean(agent));
  }, [agents, subAgentIds]);

  const selectedRows = useMemo(() => {
    const configMap = new Map(
      currentConfigs
        .filter((config) => config.agent_id)
        .map((config) => [config.agent_id, config])
    );

    return selectedAgents.map((agent, index) => ({
      agent,
      config: normalizeConfig(
        configMap.get(agent.id) ?? { agent_id: agent.id },
        agent,
        graphSchema,
        index
      ),
    }));
  }, [currentConfigs, graphSchema, selectedAgents]);

  const availableAgents = useMemo(() => {
    return agents.filter((agent) => !subAgentIds.includes(agent.id));
  }, [agents, subAgentIds]);

  function setComposition(
    nextIds: string[],
    nextConfigs: SubAgentConfiguration[]
  ) {
    setFieldValue("sub_agent_ids", nextIds);
    setFieldValue(compositionField, nextConfigs);

    if (compositionField === "sub_agents") {
      setFieldValue("stages", []);
    } else {
      setFieldValue("sub_agents", []);
    }
  }

  function handleSelectAgent(agentId: string) {
    const agent = agents.find((candidate) => candidate.id === agentId);
    if (!agent || subAgentIds.includes(agentId)) {
      return;
    }

    setComposition(
      [...subAgentIds, agentId],
      [
        ...selectedRows.map((row) => row.config),
        createConfig(agent, graphSchema, selectedRows.length),
      ]
    );
  }

  function handleRemoveAgent(agentId: string) {
    setComposition(
      subAgentIds.filter((id) => id !== agentId),
      selectedRows
        .filter((row) => row.agent.id !== agentId)
        .map((row) => row.config)
    );
  }

  function handleUpdateAgent(
    agentId: string,
    updates: Partial<SubAgentConfiguration>
  ) {
    setFieldValue(
      compositionField,
      selectedRows.map((row) =>
        row.agent.id === agentId ? { ...row.config, ...updates } : row.config
      )
    );
  }

  function handleMove(agentId: string, direction: -1 | 1) {
    const currentIndex = subAgentIds.indexOf(agentId);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= subAgentIds.length) {
      return;
    }

    const nextIds = [...subAgentIds];
    const [movedId] = nextIds.splice(currentIndex, 1);
    if (!movedId) {
      return;
    }
    nextIds.splice(nextIndex, 0, movedId);

    const configMap = new Map(
      selectedRows.map((row) => [row.agent.id, row.config])
    );
    setComposition(
      nextIds,
      nextIds
        .map((id) => configMap.get(id))
        .filter((config): config is SubAgentConfiguration => Boolean(config))
    );
  }

  if (error) {
    onError?.(String(error));
    return (
      <Card className="border border-border bg-background-neutral-02 p-4">
        <Text className="text-red-700 dark:text-red-300">
          {t("agentEditor.errorLoadingAvailableAgents")}
        </Text>
      </Card>
    );
  }

  const selectedLabel =
    selectedRows.length > 0
      ? t("agentEditor.agentsSelected", { count: selectedRows.length })
      : t("agentEditor.noSelectedSubAgentsShort");
  const modeLabel =
    graphSchema === "pipeline"
      ? t("agentEditor.pipelineOrder")
      : t("agentEditor.supervisorRoles");

  return (
    <InputLayouts.Vertical
      name="sub_agents_selector"
      title={t("agentEditor.subAgentPanelTitle")}
      description={t("agentEditor.selectSubAgentsDescription")}
    >
      <Card className="overflow-hidden border border-border bg-background-neutral-00">
        <div className="flex flex-col">
          <div className="flex flex-col gap-3 p-3 md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-08 bg-background-neutral-03">
                <SvgNetworkGraph className="h-5 w-5 stroke-text-02" />
              </div>
              <div className="min-w-0">
                <Text mainUiAction text03>
                  {modeLabel}
                </Text>
                <Text mainUiMuted text04 className="block">
                  {selectedLabel}
                  {availableAgents.length > 0 &&
                    ` · ${t("agentEditor.availableSubAgents", {
                      count: availableAgents.length,
                    })}`}
                </Text>
              </div>
            </div>

            <Button
              secondary
              type="button"
              leftIcon={selectedRows.length > 0 ? SvgSliders : SvgPlus}
              onClick={() => setIsOpen(true)}
            >
              {selectedRows.length > 0
                ? t("agentEditor.manageSubAgents")
                : t("agentEditor.addSubAgent")}
            </Button>
          </div>

          {selectedRows.length > 0 && (
            <div className="border-t border-border bg-background-neutral-02 px-3 py-2">
              <div className="flex flex-wrap gap-1.5">
                {selectedRows.slice(0, 5).map(({ agent, config }, index) => (
                  <div
                    key={agent.id}
                    className="flex max-w-full items-center gap-1.5 rounded-08 border border-border bg-background-neutral-00 px-2 py-1"
                  >
                    {graphSchema === "pipeline" && (
                      <Text mainUiMuted text04>
                        {index + 1}
                      </Text>
                    )}
                    <Text mainUiAction text04 className="truncate">
                      {config.role}
                    </Text>
                    <Text mainUiMuted text04 className="truncate">
                      {agent.name}
                    </Text>
                  </div>
                ))}
                {selectedRows.length > 5 && (
                  <div className="rounded-08 border border-border bg-background-neutral-00 px-2 py-1">
                    <Text mainUiMuted text04>
                      +{selectedRows.length - 5}
                    </Text>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </Card>

      <Modal open={isOpen} onOpenChange={setIsOpen}>
        <Modal.Content
          width="lg"
          height="lg"
          background="gray"
          preventAccidentalClose={false}
        >
          <Modal.Header
            icon={SvgNetworkGraph}
            title={t("agentEditor.subAgentModalTitle")}
            description={t("agentEditor.subAgentModalDescription")}
            onClose={() => setIsOpen(false)}
          />

          <Modal.Body padding={0.75}>
            <div className="grid min-h-[34rem] grid-cols-1 gap-3 lg:grid-cols-[minmax(16rem,0.78fr)_minmax(0,1.22fr)]">
              <div className="flex min-h-0 flex-col rounded-08 border border-border bg-background-neutral-00">
                <div className="border-b border-border p-3">
                  <Text mainUiAction text03>
                    {t("agentEditor.availableAgentsPanel")}
                  </Text>
                  <Text mainUiMuted text04 className="block">
                    {t("agentEditor.availableSubAgents", {
                      count: availableAgents.length,
                    })}
                  </Text>
                </div>

                <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
                  {isLoading ? (
                    <div className="flex flex-1 items-center justify-center">
                      <SimpleLoader />
                    </div>
                  ) : availableAgents.length > 0 ? (
                    <>
                      <InputSelect value="" onValueChange={handleSelectAgent}>
                        <InputSelect.Trigger
                          placeholder={t("agentEditor.chooseSubAgent")}
                        />
                        <InputSelect.Content>
                          {availableAgents.map((agent) => (
                            <InputSelect.Item key={agent.id} value={agent.id}>
                              <div className="flex min-w-0 items-center gap-2">
                                <Text mainUiBody text03 className="truncate">
                                  {agent.name}
                                </Text>
                                <Text mainUiMuted text04 className="shrink-0">
                                  {agent.graph_schema}
                                </Text>
                              </div>
                            </InputSelect.Item>
                          ))}
                        </InputSelect.Content>
                      </InputSelect>

                      <div className="flex min-h-0 flex-col gap-1.5 overflow-y-auto pr-1">
                        {availableAgents.map((agent) => (
                          <button
                            key={agent.id}
                            type="button"
                            className="flex w-full items-start justify-between gap-2 rounded-08 border border-border bg-background-neutral-02 p-2 text-left hover:bg-background-neutral-03"
                            onClick={() => handleSelectAgent(agent.id)}
                          >
                            <span className="min-w-0">
                              <Text mainUiAction text03 className="block truncate">
                                {agent.name}
                              </Text>
                              <Text mainUiMuted text04>
                                {formatAgentMeta(agent)}
                              </Text>
                            </span>
                            <SvgPlus className="mt-0.5 h-4 w-4 shrink-0 stroke-text-03" />
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-1 items-center rounded-08 border border-dashed border-border bg-background-neutral-02 p-4">
                      <Text mainUiMuted text03>
                        {t("agentEditor.noAvailableAgents")}
                      </Text>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex min-h-0 flex-col rounded-08 border border-border bg-background-neutral-00">
                <div className="flex items-center justify-between gap-3 border-b border-border p-3">
                  <div>
                    <Text mainUiAction text03>
                      {t("agentEditor.selectedSubAgents")}
                    </Text>
                    <Text mainUiMuted text04 className="block">
                      {selectedRows.length > 0
                        ? modeLabel
                        : t("agentEditor.noSelectedSubAgents")}
                    </Text>
                  </div>
                  <Text mainUiMuted text04>
                    {selectedRows.length}
                  </Text>
                </div>

                {selectedRows.length === 0 ? (
                  <div className="flex flex-1 items-center justify-center p-6">
                    <div className="max-w-sm text-center">
                      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-08 bg-background-neutral-03">
                        <SvgNetworkGraph className="h-5 w-5 stroke-text-02" />
                      </div>
                      <Text mainUiAction text03>
                        {t("agentEditor.noSelectedSubAgents")}
                      </Text>
                      <Text mainUiMuted text04 className="mt-1 block">
                        {t("agentEditor.noSelectedSubAgentsHint")}
                      </Text>
                    </div>
                  </div>
                ) : (
                  <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
                    {selectedRows.map(({ agent, config }, index) => (
                      <div
                        key={agent.id}
                        className="rounded-08 border border-border bg-background-neutral-02 p-3"
                      >
                        <div className="flex flex-col gap-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex min-w-0 items-start gap-2">
                              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-08 bg-background-neutral-00">
                                {graphSchema === "pipeline" ? (
                                  <Text mainUiAction text04>
                                    {index + 1}
                                  </Text>
                                ) : (
                                  <SvgCheck className="h-4 w-4 stroke-text-02" />
                                )}
                              </div>
                              <div className="min-w-0">
                                <Text mainUiAction text03 className="truncate">
                                  {agent.name}
                                </Text>
                                <Text mainUiMuted text04 className="block">
                                  {formatAgentMeta(agent)}
                                </Text>
                              </div>
                            </div>

                            <div className="flex shrink-0 items-center gap-1">
                              {graphSchema === "pipeline" && (
                                <>
                                  <SquareButton
                                    icon={SvgArrowUpDot}
                                    disabled={index === 0}
                                    onClick={() => handleMove(agent.id, -1)}
                                    title={t("agentEditor.moveSubAgentUp")}
                                  />
                                  <SquareButton
                                    icon={SvgArrowUpDot}
                                    disabled={
                                      index === selectedRows.length - 1
                                    }
                                    onClick={() => handleMove(agent.id, 1)}
                                    title={t("agentEditor.moveSubAgentDown")}
                                    className="rotate-180"
                                  />
                                </>
                              )}
                              <SquareButton
                                icon={SvgTrash}
                                onClick={() => handleRemoveAgent(agent.id)}
                                title={t("agentEditor.removeSubAgent")}
                              />
                            </div>
                          </div>

                          <div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)]">
                            <div className="flex flex-col gap-1.5">
                              <Text mainUiMuted text04>
                                {t("agentEditor.subAgentRoleLabel")}
                              </Text>
                              <InputTypeIn
                                value={config.role}
                                showClearButton={false}
                                onChange={(event) => {
                                  const role = event.target.value;
                                  handleUpdateAgent(agent.id, {
                                    role,
                                    name: role,
                                  });
                                }}
                                placeholder={
                                  graphSchema === "pipeline"
                                    ? t("agentEditor.pipelineStagePlaceholder")
                                    : t("agentEditor.subAgentRolePlaceholder")
                                }
                              />
                            </div>

                            <div className="flex flex-col gap-1.5">
                              <Text mainUiMuted text04>
                                {t("agentEditor.subAgentInstructionLabel")}
                              </Text>
                              <InputTextArea
                                rows={3}
                                autoResize
                                maxRows={7}
                                value={config.system_prompt}
                                onChange={(event) =>
                                  handleUpdateAgent(agent.id, {
                                    system_prompt: event.target.value,
                                  })
                                }
                                placeholder={t(
                                  "agentEditor.subAgentInstructionPlaceholder"
                                )}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Modal.Body>

          <Modal.Footer>
            <Button
              type="button"
              secondary
              onClick={() => setIsOpen(false)}
            >
              {t("agentEditor.applySubAgentChanges")}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </InputLayouts.Vertical>
  );
}
