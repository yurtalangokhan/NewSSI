"use client";

import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import { SvgBranch, SvgNetworkGraph, SvgWorkflow } from "@opal/icons";

const GRAPH_SCHEMA_PREVIEW_META: Record<
  string,
  {
    nodeKeys: string[];
    detailKey: string;
    capabilities: {
      tools: boolean;
      memory: boolean;
      subAgents: boolean;
      multiStep: boolean;
    };
  }
> = {
  zero_shot: {
    nodeKeys: ["input", "prompt", "answer"],
    detailKey: "zeroShot",
    capabilities: {
      tools: false,
      memory: false,
      subAgents: false,
      multiStep: false,
    },
  },
  react: {
    nodeKeys: ["input", "reason", "act", "observe", "answer"],
    detailKey: "react",
    capabilities: {
      tools: true,
      memory: true,
      subAgents: false,
      multiStep: true,
    },
  },
  supervisor: {
    nodeKeys: ["input", "supervisor", "subAgents", "review", "answer"],
    detailKey: "supervisor",
    capabilities: {
      tools: false,
      memory: true,
      subAgents: true,
      multiStep: true,
    },
  },
  pipeline: {
    nodeKeys: ["input", "stageOne", "stageTwo", "stageThree", "answer"],
    detailKey: "pipeline",
    capabilities: {
      tools: true,
      memory: true,
      subAgents: false,
      multiStep: true,
    },
  },
  plan_execute: {
    nodeKeys: ["input", "plan", "execute", "synthesize", "answer"],
    detailKey: "planExecute",
    capabilities: {
      tools: true,
      memory: true,
      subAgents: false,
      multiStep: true,
    },
  },
  self_reflect: {
    nodeKeys: ["input", "draft", "critique", "revise", "answer"],
    detailKey: "selfReflect",
    capabilities: {
      tools: false,
      memory: true,
      subAgents: false,
      multiStep: true,
    },
  },
};

interface GraphSchemaPreviewProps {
  graphSchema: string;
  graphSchemaLabel: string;
  agentName?: string;
  brainTypeLabel?: string;
  memoryTypeLabel?: string;
  longTermMemoryEnabled?: boolean;
  selectedToolNames?: string[];
  hasKnowledgeEnabled?: boolean;
  compositionDepth?: number;
  subAgentConfigs?: Array<{
    role?: string;
    name?: string;
    system_prompt?: string;
  }>;
  variant?: "compact" | "hero";
}

export default function GraphSchemaPreview({
  graphSchema,
  graphSchemaLabel,
  agentName,
  brainTypeLabel,
  memoryTypeLabel,
  longTermMemoryEnabled = false,
  selectedToolNames = [],
  hasKnowledgeEnabled = false,
  compositionDepth = 0,
  subAgentConfigs = [],
  variant = "compact",
}: GraphSchemaPreviewProps) {
  const { t } = useTranslation();
  const schemaPreview = (GRAPH_SCHEMA_PREVIEW_META[graphSchema] ??
    GRAPH_SCHEMA_PREVIEW_META.zero_shot)!;
  const isHero = variant === "hero";
  const toolCount = selectedToolNames.length + (hasKnowledgeEnabled ? 1 : 0);
  const visibleToolNames = [
    ...(hasKnowledgeEnabled ? [t("agentEditor.graphPreviewKnowledge")] : []),
    ...selectedToolNames,
  ].slice(0, 4);
  const hiddenToolCount = Math.max(toolCount - visibleToolNames.length, 0);
  const resolvedAgentName =
    agentName?.trim() || t("agentEditor.graphPreviewUnnamedAgent");
  const memorySelected = longTermMemoryEnabled || !!memoryTypeLabel?.trim();
  const compositionLabel =
    graphSchema === "pipeline"
      ? t("agentEditor.graphPreviewStages")
      : t("agentEditor.graphPreviewSubAgents");
  const visibleSubAgentConfigs = subAgentConfigs.slice(0, 6);
  const hiddenSubAgentCount = Math.max(
    subAgentConfigs.length - visibleSubAgentConfigs.length,
    0
  );
  const previewNodeKeys =
    graphSchema === "pipeline" && subAgentConfigs.length > 0
      ? [
          "input",
          ...subAgentConfigs.map((_, index) => `configuredStage:${index}`),
          "answer",
        ]
      : schemaPreview.nodeKeys;
  const capabilityItems = [
    {
      label: t("agentEditor.graphPreviewTools"),
      enabled: schemaPreview.capabilities.tools || toolCount > 0,
      value:
        toolCount > 0
          ? t("agentEditor.graphPreviewToolCount", { count: toolCount })
          : undefined,
    },
    {
      label: t("agentEditor.graphPreviewMemory"),
      enabled: schemaPreview.capabilities.memory || memorySelected,
      value: memorySelected
        ? longTermMemoryEnabled
          ? t("agentEditor.graphPreviewLongTermMemory")
          : memoryTypeLabel
        : schemaPreview.capabilities.memory
          ? t("agentEditor.graphPreviewAvailable")
          : undefined,
    },
    {
      label: compositionLabel,
      enabled:
        schemaPreview.capabilities.subAgents ||
        graphSchema === "pipeline" ||
        subAgentConfigs.length > 0,
      value:
        subAgentConfigs.length > 0
          ? t("agentEditor.graphPreviewSubAgentCount", {
              count: subAgentConfigs.length,
            })
          : schemaPreview.capabilities.subAgents || graphSchema === "pipeline"
            ? t("agentEditor.graphPreviewSchemaManaged")
            : undefined,
    },
    {
      label: t("agentEditor.graphPreviewMultiStep"),
      enabled: schemaPreview.capabilities.multiStep,
      value: schemaPreview.capabilities.multiStep
        ? t("agentEditor.graphPreviewSchemaManaged")
        : undefined,
    },
  ];

  return (
    <div
      className={cn(
        "graph-preview-card rounded-08 border border-border-01 bg-background-tint-00",
        isHero ? "p-4 md:p-5" : "p-3"
      )}
    >
      <style>{`
        @keyframes graphPreviewIn {
          from {
            opacity: 0;
            transform: translateY(-0.375rem);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes graphFlow {
          from {
            transform: translateX(-0.375rem);
            opacity: 0;
          }
          20% {
            opacity: 1;
          }
          to {
            transform: translateX(0.75rem);
            opacity: 0;
          }
        }

        @keyframes graphNodePulse {
          0%,
          100% {
            box-shadow: 0 0 0 0 color-mix(in srgb, var(--text-03) 20%, transparent);
          }
          50% {
            box-shadow: 0 0 0 0.25rem color-mix(in srgb, var(--text-03) 8%, transparent);
          }
        }

        .graph-preview-card {
          animation: graphPreviewIn 180ms ease-out;
        }

        .graph-flow-dot {
          animation: graphFlow 1.25s ease-in-out infinite;
        }

        .graph-node-pulse {
          animation: graphNodePulse 1.8s ease-in-out infinite;
        }

        @media (prefers-reduced-motion: reduce) {
          .graph-preview-card,
          .graph-flow-dot,
          .graph-node-pulse {
            animation: none;
          }
        }
      `}</style>
      <div className={cn("flex flex-col", isHero ? "gap-4" : "gap-3")}>
        <div
          className={cn(
            "flex gap-3",
            isHero
              ? "flex-col md:flex-row md:items-start md:justify-between"
              : "items-center"
          )}
        >
          <div className="flex items-start gap-3">
            <div
              className={cn(
                "flex shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-00",
                isHero ? "h-10 w-10" : "h-7 w-7"
              )}
            >
              <SvgNetworkGraph
                className={cn("stroke-text-04", isHero ? "h-5 w-5" : "h-4 w-4")}
              />
            </div>
            <div className="min-w-0">
              {isHero && (
                <Text as="p" figureSmallLabel text03>
                  {t("agentEditor.graphPreviewHeroEyebrow")}
                </Text>
              )}
              <Text as="p" mainUiAction text05>
                {isHero
                  ? resolvedAgentName
                  : t("agentEditor.graphPreviewTitle", {
                      schema: graphSchemaLabel,
                    })}
              </Text>
              {isHero && (
                <Text as="p" secondaryAction text04>
                  {t("agentEditor.graphPreviewTitle", {
                    schema: graphSchemaLabel,
                  })}
                </Text>
              )}
              <Text as="p" secondaryBody text03>
                {t(
                  `agentEditor.graphPreviewDetails.${schemaPreview.detailKey}`
                )}
              </Text>
            </div>
          </div>

          {isHero && (
            <div className="grid grid-cols-2 gap-2 md:min-w-72">
              <div className="rounded-08 border border-border-01 bg-background-neutral-00 px-3 py-2">
                <Text as="p" figureSmallLabel text03>
                  {t("agentEditor.brainTypeLabel")}
                </Text>
                <Text as="p" secondaryAction text05>
                  {brainTypeLabel || t("agentEditor.graphPreviewDefaultBrain")}
                </Text>
              </div>
              <div className="rounded-08 border border-border-01 bg-background-neutral-00 px-3 py-2">
                <Text as="p" figureSmallLabel text03>
                  {t("agentEditor.graphPreviewTooling")}
                </Text>
                <Text as="p" secondaryAction text05>
                  {toolCount > 0
                    ? t("agentEditor.graphPreviewToolCount", {
                        count: toolCount,
                      })
                    : t("agentEditor.graphPreviewNotUsed")}
                </Text>
              </div>
            </div>
          )}
        </div>

        <div
          className={cn(
            "flex flex-col gap-2 overflow-hidden rounded-08 border border-border-01 bg-background-neutral-00",
            isHero ? "p-3" : "p-2"
          )}
        >
          <div className="flex items-center gap-1.5">
            <SvgWorkflow className="h-3.5 w-3.5 stroke-text-03" />
            <Text as="p" figureSmallLabel text03>
              {t("agentEditor.graphPreviewExecutionPath")}
            </Text>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-1">
            {previewNodeKeys.map((nodeKey, index) => {
              const configuredStageIndex = nodeKey.startsWith(
                "configuredStage:"
              )
                ? Number(nodeKey.split(":")[1])
                : null;
              const configuredStage =
                configuredStageIndex !== null
                  ? subAgentConfigs[configuredStageIndex]
                  : undefined;
              const nodeLabel = configuredStage
                ? configuredStage.role?.trim() ||
                  configuredStage.name?.trim() ||
                  `Stage ${configuredStageIndex! + 1}`
                : t(`agentEditor.graphPreviewNodes.${nodeKey}`);
              const isBranchNode =
                graphSchema === "supervisor" && nodeKey === "subAgents";
              const isLoopNode =
                (graphSchema === "react" && nodeKey === "observe") ||
                (graphSchema === "self_reflect" && nodeKey === "revise");

              return (
                <div
                  key={`${graphSchema}-${nodeKey}`}
                  className={cn(
                    "relative flex min-h-16 flex-1 items-center",
                    isHero
                      ? "min-w-[7.5rem] md:min-w-[8rem]"
                      : "min-w-[6.5rem] md:min-w-[7.5rem]"
                  )}
                >
                  {index > 0 && (
                    <div className="absolute -left-2 top-1/2 h-px w-2 bg-border-02">
                      <div className="graph-flow-dot absolute -top-[0.1875rem] left-0 h-1.5 w-1.5 rounded-full bg-text-03" />
                    </div>
                  )}
                  <div
                    className={cn(
                      "flex h-full w-full items-center gap-2 rounded-08 border border-border-01 bg-background-tint-00",
                      isHero ? "px-2.5 py-2.5" : "px-2 py-2"
                    )}
                  >
                    <div
                      className={cn(
                        "flex shrink-0 items-center justify-center rounded-08 bg-background-neutral-02",
                        isHero ? "graph-node-pulse h-8 w-8" : "h-6 w-6"
                      )}
                    >
                      {isBranchNode ? (
                        <SvgBranch className="h-3.5 w-3.5 stroke-text-04" />
                      ) : (
                        <Text as="span" figureSmallValue text04>
                          {index + 1}
                        </Text>
                      )}
                    </div>
                    <div className="min-w-0">
                      <Text
                        as="p"
                        secondaryAction
                        text05
                        className="line-clamp-2"
                      >
                        {nodeLabel}
                      </Text>
                      {isLoopNode && (
                        <Text as="p" figureSmallLabel text03>
                          {t("agentEditor.graphPreviewLoop")}
                        </Text>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {isHero &&
          (graphSchema === "supervisor" || graphSchema === "pipeline") && (
            <div className="rounded-08 border border-border-01 bg-background-neutral-00 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-1.5">
                  <SvgBranch className="h-3.5 w-3.5 shrink-0 stroke-text-03" />
                  <Text as="p" figureSmallLabel text03>
                    {t("agentEditor.graphPreviewConfiguredTeam")}
                  </Text>
                </div>
                <Text as="p" figureSmallLabel text03>
                  {compositionDepth > 1
                    ? t("agentEditor.hierarchyDepth", {
                        depth: compositionDepth,
                      })
                    : subAgentConfigs.length > 0
                      ? t("agentEditor.graphPreviewSubAgentCount", {
                          count: subAgentConfigs.length,
                        })
                      : compositionLabel}
                </Text>
              </div>

              {visibleSubAgentConfigs.length > 0 ? (
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {visibleSubAgentConfigs.map((config, index) => {
                    const title =
                      config.role?.trim() ||
                      config.name?.trim() ||
                      (graphSchema === "pipeline"
                        ? `Stage ${index + 1}`
                        : `Specialist ${index + 1}`);
                    const instruction = config.system_prompt?.trim();

                    return (
                      <div
                        key={`${title}-${index}`}
                        className="rounded-08 border border-border-01 bg-background-tint-00 px-3 py-2"
                      >
                        <div className="flex items-start gap-2">
                          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-08 bg-background-neutral-02">
                            <Text as="span" figureSmallValue text04>
                              {index + 1}
                            </Text>
                          </div>
                          <div className="min-w-0">
                            <Text as="p" secondaryAction text05>
                              {title}
                            </Text>
                            {instruction && (
                              <>
                                <Text as="p" figureSmallLabel text03>
                                  {t(
                                    "agentEditor.graphPreviewInstructionPreview"
                                  )}
                                </Text>
                                <Text
                                  as="p"
                                  secondaryBody
                                  text03
                                  className="line-clamp-2"
                                >
                                  {instruction}
                                </Text>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {hiddenSubAgentCount > 0 && (
                    <div className="flex items-center rounded-08 border border-border-01 bg-background-tint-00 px-3 py-2">
                      <Text as="p" secondaryAction text04>
                        +{hiddenSubAgentCount}
                      </Text>
                    </div>
                  )}
                </div>
              ) : (
                <div className="rounded-08 border border-dashed border-border-01 bg-background-tint-00 px-3 py-3">
                  <Text as="p" secondaryBody text03>
                    {t("agentEditor.graphPreviewNoSubAgents")}
                  </Text>
                </div>
              )}
            </div>
          )}

        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {capabilityItems.map((item) => (
            <div
              key={item.label}
              className={cn(
                "rounded-08 border px-2 py-1.5",
                item.enabled
                  ? "border-border-02 bg-background-neutral-00"
                  : "border-border-01 bg-background-tint-00 opacity-60"
              )}
            >
              <Text as="p" figureSmallLabel text03>
                {item.label}
              </Text>
              <Text as="p" secondaryAction text05>
                {item.value ??
                  (item.enabled
                    ? t("agentEditor.graphPreviewEnabled")
                    : t("agentEditor.graphPreviewNotUsed"))}
              </Text>
            </div>
          ))}
        </div>

        {isHero && (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            <div className="rounded-08 border border-border-01 bg-background-neutral-00 px-3 py-2">
              <Text as="p" secondaryAction text05>
                {t("agentEditor.graphPreviewToolsInfoTitle")}
              </Text>
              <Text as="p" secondaryBody text03>
                {visibleToolNames.length > 0
                  ? t("agentEditor.graphPreviewToolsInfoWithTools", {
                      tools: visibleToolNames.join(", "),
                      count: hiddenToolCount,
                    })
                  : t("agentEditor.graphPreviewToolsInfoEmpty")}
              </Text>
            </div>
            <div className="rounded-08 border border-border-01 bg-background-neutral-00 px-3 py-2">
              <Text as="p" secondaryAction text05>
                {t("agentEditor.graphPreviewMemoryInfoTitle")}
              </Text>
              <Text as="p" secondaryBody text03>
                {memorySelected
                  ? t("agentEditor.graphPreviewMemoryInfoEnabled")
                  : t("agentEditor.graphPreviewMemoryInfoDisabled")}
              </Text>
            </div>
            <div className="rounded-08 border border-border-01 bg-background-neutral-00 px-3 py-2">
              <Text as="p" secondaryAction text05>
                {t("agentEditor.graphPreviewFlowInfoTitle")}
              </Text>
              <Text as="p" secondaryBody text03>
                {t(
                  schemaPreview.capabilities.subAgents
                    ? "agentEditor.graphPreviewFlowInfoSubAgents"
                    : schemaPreview.capabilities.multiStep
                      ? "agentEditor.graphPreviewFlowInfoMultiStep"
                      : "agentEditor.graphPreviewFlowInfoDirect"
                )}
              </Text>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
