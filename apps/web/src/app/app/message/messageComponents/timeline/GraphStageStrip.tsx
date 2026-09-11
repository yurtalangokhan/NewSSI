"use client";

import { buildNodeExecutionData } from "./nodeExecutionData";

import React, { useMemo, useState } from "react";
import {
  SvgWorkflow,
  SvgMenu,
  SvgNetworkGraph,
  SvgArrowRight,
  SvgCheck,
  SvgLoader,
  SvgTerminal,
} from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { useAppBackground } from "@/providers/AppBackgroundProvider";
import { createFlowStore } from "@/components/flow-canvas/stores/flowStore";
import { useLoadFlowIntoStore } from "@/components/flow-canvas/hooks/useLoadFlowIntoStore";

import { formatRunTime } from "@/components/flow-canvas/utils/formatRunTime";
import { GraphStageCanvas } from "./GraphStageCanvas";
import { useTranslation } from "react-i18next";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import {
  buildNodeRunStatus,
  flowVersionNoFromPackets,
  getCallSequence,
  getFlowStageDefinitions,
  getStageDefinitions,
  getStageProgress,
  getToolNameToNodeId,
  getToolNodeIdToAgentNodeId,
  MIN_STAGE_DURATION_MS,
  type GraphStageStripProps,
} from "./graphStageParsing";

export default function GraphStageStrip({
  agent,
  packets,
  packetCount,
}: GraphStageStripProps) {
  const effectivePacketCount = packetCount ?? packets.length;
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<"list" | "canvas">("list");
  const isFlowBacked =
    agent.graph_schema === "flow" && Boolean(agent.agent_definition_id);

  const configuredStageDefinitions = useMemo(
    () => getStageDefinitions(agent),
    [agent]
  );

  const pinnedVersionNo = useMemo(
    () => flowVersionNoFromPackets(packets),

    [effectivePacketCount, packets.length]
  );

  const flowStore = useMemo(
    () => createFlowStore(),
    [agent.agent_definition_id]
  );
  const { nodes: flowNodes, edges: flowEdges } = useLoadFlowIntoStore(
    isFlowBacked ? agent.agent_definition_id ?? null : null,
    flowStore,
    {
      source:
        pinnedVersionNo != null ? { versionNo: pinnedVersionNo } : "published",
    }
  );

  const flowStageDefinitions = useMemo(
    () => (isFlowBacked ? getFlowStageDefinitions(flowNodes, flowEdges) : []),
    [isFlowBacked, flowNodes, flowEdges]
  );

  const stageDefinitions =
    configuredStageDefinitions.length > 0
      ? configuredStageDefinitions
      : flowStageDefinitions;

  const toolNameToNodeId = useMemo(
    () => getToolNameToNodeId(flowNodes),
    [flowNodes]
  );

  const toolNodeIdToAgentNodeId = useMemo(
    () => getToolNodeIdToAgentNodeId(flowEdges, flowNodes),
    [flowEdges, flowNodes]
  );

  // One epoch-ms per packet, index-aligned with `packets`. Recomputed purely
  // from `packets` (append-only during a stream) whenever its length changes.
  // A packet with no embedded timestamp (reload replay that lost timing, or a
  // synthetic packet) is anchored to the newest real timestamp seen so far,
  // NOT Date.now() — otherwise a completed run reopened minutes later shows a
  // stage duration of "now - start".
  const packetTimestamps = useMemo(() => {
    const out: number[] = [];
    let lastRealTs = 0;
    for (const packet of packets) {
      const embedded = (packet?.obj as { timestamp?: unknown } | undefined)
        ?.timestamp;
      if (typeof embedded === "number") {
        lastRealTs = Math.max(lastRealTs, embedded);
        out.push(embedded);
      } else {
        out.push(lastRealTs || Date.now());
      }
    }
    return out;
  }, [effectivePacketCount, packets.length]);

  const progress = useMemo(
    () =>
      getStageProgress(
        packets,
        stageDefinitions,
        toolNameToNodeId,
        packetTimestamps
      ),

    [
      effectivePacketCount,
      packets.length,
      stageDefinitions,
      toolNameToNodeId,
      packetTimestamps,
    ]
  );

  const callSequence = useMemo(
    () =>
      getCallSequence(
        packets,
        stageDefinitions,
        toolNameToNodeId,
        toolNodeIdToAgentNodeId,
        progress,
        packetTimestamps
      ),

    [
      effectivePacketCount,
      packets.length,
      stageDefinitions,
      toolNameToNodeId,
      toolNodeIdToAgentNodeId,
      progress,
      packetTimestamps,
    ]
  );

  const nodeRunStatus = useMemo(() => buildNodeRunStatus(progress), [progress]);

  const nodeExecutionData = useMemo(
    () =>
      buildNodeExecutionData(packets, stageDefinitions, flowNodes, flowEdges),
    [
      effectivePacketCount,
      packets.length,
      stageDefinitions,
      flowNodes,
      flowEdges,
    ]
  );

  const { hasBackground } = useAppBackground();

  const translateLabel = (label: string): string => {
    const componentName = t(`flowCanvas.components.${label}.name`, "");
    if (
      componentName &&
      componentName !== `flowCanvas.components.${label}.name`
    ) {
      return componentName;
    }
    const nodeName = t(`flowDesigner.nodes.${label}.name`, "");
    if (nodeName && nodeName !== `flowDesigner.nodes.${label}.name`) {
      return nodeName;
    }
    const stageName = t(`chat.stages.${label.toLowerCase()}`, "");
    if (stageName && stageName !== `chat.stages.${label.toLowerCase()}`) {
      return stageName;
    }
    return label;
  };

  if (stageDefinitions.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-2.5 rounded-12 border border-neutral-200/80 dark:border-neutral-800/80 p-3 transition-all duration-200",
        hasBackground
          ? "backdrop-blur-md bg-neutral-100/70 dark:bg-neutral-900/70 shadow-xs"
          : "bg-neutral-50/90 dark:bg-neutral-900/90 shadow-xs"
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex size-5 items-center justify-center rounded-md bg-blue-500/10 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400">
            <SvgWorkflow className="size-3.5" />
          </div>
          <Text
            as="p"
            secondaryBody
            text03
            className="font-semibold text-xs tracking-wide text-neutral-800 dark:text-neutral-200"
          >
            {t("chat.graphStages", { defaultValue: "Grafik Aşamaları" })}
          </Text>
        </div>
        {isFlowBacked && flowStageDefinitions.length > 0 && (
          <div className="flex gap-1 bg-neutral-200/70 dark:bg-neutral-800/90 p-0.5 rounded-lg border border-neutral-300/60 dark:border-neutral-700/60">
            <button
              type="button"
              aria-label={t("chat.listView", {
                defaultValue: "Liste Görünümü",
              })}
              title={t("chat.listView", { defaultValue: "Liste Görünümü" })}
              onClick={() => setViewMode("list")}
              className={cn(
                "flex items-center justify-center size-6 rounded-md transition-colors",
                viewMode === "list"
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 shadow-2xs"
                  : "text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
              )}
            >
              <SvgMenu className="size-3.5" />
            </button>
            <button
              type="button"
              aria-label={t("chat.canvasView", {
                defaultValue: "Tuval Görünümü",
              })}
              title={t("chat.canvasView", { defaultValue: "Tuval Görünümü" })}
              onClick={() => setViewMode("canvas")}
              className={cn(
                "flex items-center justify-center size-6 rounded-md transition-colors",
                viewMode === "canvas"
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-neutral-100 shadow-2xs"
                  : "text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
              )}
            >
              <SvgNetworkGraph className="size-3.5" />
            </button>
          </div>
        )}
      </div>

      {viewMode === "list" || !isFlowBacked ? (
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          {callSequence.map((entry, index) => {
            const isRunning = entry.status === "running";
            const isDone = entry.status === "done";
            const isPending = entry.status === "pending";
            const durationStr =
              isDone && entry.durationMs
                ? formatRunTime(entry.durationMs)
                : null;
            const displayLabel = translateLabel(entry.label);

            const statusText = isRunning
              ? t("chat.stageRunning", { defaultValue: "Çalışıyor" })
              : isDone
                ? `${t("chat.stageCompleted", {
                    defaultValue: "Tamamlandı",
                  })}: ${durationStr || ""}`
                : t("chat.stagePending", { defaultValue: "Bekliyor" });

            return (
              <div
                key={entry.key}
                data-testid="stage-entry"
                data-status={entry.status}
                className="flex items-center gap-2"
              >
                {index > 0 && (
                  <SvgArrowRight
                    data-testid="stage-arrow"
                    className={cn(
                      "size-3 shrink-0 stroke-neutral-400 dark:stroke-neutral-600 transition-colors",
                      isPending && "opacity-30",
                      isRunning && "stroke-blue-500 dark:stroke-blue-400"
                    )}
                  />
                )}
                <div
                  className={cn(
                    "group relative flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all duration-150",
                    isRunning &&
                      "border-blue-500/80 dark:border-blue-400/80 bg-blue-50/80 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 ring-1 ring-blue-500/30 shadow-xs",
                    isDone &&
                      "border-neutral-200/90 dark:border-neutral-700/80 bg-white/90 dark:bg-neutral-800/90 text-neutral-900 dark:text-neutral-100 shadow-2xs hover:border-neutral-300 dark:hover:border-neutral-600",
                    isPending &&
                      "border-dashed border-neutral-300 dark:border-neutral-800 bg-transparent text-neutral-400 dark:text-neutral-500 opacity-60"
                  )}
                  title={`${displayLabel} (${statusText})`}
                >
                  {isRunning && (
                    <SvgLoader className="size-3.5 animate-spin text-blue-600 dark:text-blue-400 shrink-0" />
                  )}
                  {isDone && (
                    <SvgCheck className="size-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  )}
                  {isPending && (
                    <div className="size-1.5 rounded-full bg-neutral-400 dark:bg-neutral-600 shrink-0" />
                  )}
                  <span>{displayLabel}</span>
                  {entry.callCount > 1 && (
                    <span className="rounded-full bg-blue-100 dark:bg-blue-900/60 text-blue-700 dark:text-blue-300 px-1.5 py-0.2 text-[10px] font-bold">
                      {entry.callCount}x
                    </span>
                  )}
                  {durationStr && (
                    <span className="ml-1 text-[11px] font-medium text-neutral-500 dark:text-neutral-400">
                      {durationStr}
                    </span>
                  )}

                  {/* Embedded agent-level tool calls with Onyx Tooltip */}
                  {entry.tools && entry.tools.length > 0 && (
                    <div className="flex items-center gap-1.5 ml-1 pl-2 border-l border-neutral-200/80 dark:border-neutral-700/80">
                      {entry.tools.map((tool) => {
                        const toolDisplayLabel = translateLabel(tool.label);
                        const toolDuration = tool.durationMs
                          ? formatRunTime(tool.durationMs)
                          : null;
                        return (
                          <TooltipProvider
                            key={tool.toolName}
                            delayDuration={100}
                          >
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span
                                  data-testid="stage-tool-badge"
                                  tabIndex={0}
                                  role="button"
                                  aria-label={`${toolDisplayLabel} ${
                                    toolDuration || ""
                                  }`}
                                  className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-blue-500/10 dark:bg-blue-400/15 border border-blue-500/20 dark:border-blue-400/20 px-1.5 py-0.5 text-[11px] font-medium text-blue-700 dark:text-blue-300 shadow-2xs hover:bg-blue-500/20 dark:hover:bg-blue-400/25 transition-all outline-hidden"
                                >
                                  <SvgTerminal className="size-2.5 opacity-80" />
                                  <span>{toolDisplayLabel}</span>
                                  {tool.callCount > 1 && (
                                    <span className="rounded bg-blue-200/60 dark:bg-blue-800/80 px-1 py-0.1 font-bold text-[9px] text-blue-900 dark:text-blue-200">
                                      {tool.callCount}x
                                    </span>
                                  )}
                                  {toolDuration && (
                                    <span className="opacity-70 text-[10px] font-normal">
                                      {toolDuration}
                                    </span>
                                  )}
                                </span>
                              </TooltipTrigger>
                              <TooltipContent
                                side="top"
                                align="center"
                                className="p-3 min-w-[210px] max-w-[300px] bg-neutral-900/95 dark:bg-neutral-950/95 text-neutral-100 border border-neutral-700/80 dark:border-neutral-800/80 backdrop-blur-md shadow-xl rounded-xl z-tooltip"
                              >
                                {/* Onyx Tooltip Header */}
                                <div className="flex items-center justify-between gap-2 pb-2 border-b border-neutral-800">
                                  <div className="flex items-center gap-1.5">
                                    <div className="flex size-4 items-center justify-center rounded bg-blue-500/20 text-blue-400">
                                      <SvgTerminal className="size-2.5" />
                                    </div>
                                    <span className="font-semibold text-xs text-neutral-100">
                                      {toolDisplayLabel}
                                    </span>
                                  </div>
                                  <span
                                    className={cn(
                                      "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                                      tool.status === "running"
                                        ? "bg-amber-500/20 text-amber-300"
                                        : "bg-emerald-500/20 text-emerald-300"
                                    )}
                                  >
                                    {tool.status === "running"
                                      ? t("chat.stageRunning", {
                                          defaultValue: "Çalışıyor",
                                        })
                                      : t("chat.stageCompleted", {
                                          defaultValue: "Tamamlandı",
                                        })}
                                  </span>
                                </div>

                                {/* Onyx Tooltip Invocations Breakdown */}
                                <div className="pt-2 flex flex-col gap-1.5 text-xs">
                                  {tool.invocations &&
                                  tool.invocations.length > 1 ? (
                                    <>
                                      <div className="text-[11px] font-medium text-neutral-400 flex items-center justify-between">
                                        <span>
                                          {t("chat.callBreakdown", {
                                            defaultValue: "Çağrı Detayları",
                                          })}
                                        </span>
                                        <span>
                                          {tool.callCount}{" "}
                                          {t("chat.calls", {
                                            defaultValue: "çağrı",
                                          })}
                                        </span>
                                      </div>
                                      <div className="flex flex-col gap-1 max-h-[140px] overflow-y-auto pr-0.5">
                                        {tool.invocations.map((inv) => (
                                          <div
                                            key={inv.index}
                                            className="flex items-center justify-between py-1 px-2 rounded-md bg-neutral-800/60 text-[11px]"
                                          >
                                            <span className="text-neutral-300 font-medium">
                                              {t("chat.callIndex", {
                                                index: inv.index,
                                                defaultValue: `Çağrı #${inv.index}`,
                                              })}
                                            </span>
                                            <span className="font-mono text-emerald-400 font-medium">
                                              {inv.durationMs
                                                ? formatRunTime(inv.durationMs)
                                                : formatRunTime(
                                                    MIN_STAGE_DURATION_MS
                                                  )}
                                            </span>
                                          </div>
                                        ))}
                                      </div>
                                      <div className="flex items-center justify-between pt-1.5 border-t border-neutral-800 text-[11px] font-semibold text-neutral-200">
                                        <span>
                                          {t("chat.totalDuration", {
                                            defaultValue: "Toplam Süre",
                                          })}
                                        </span>
                                        <span className="font-mono text-emerald-300">
                                          {tool.durationMs
                                            ? formatRunTime(tool.durationMs)
                                            : formatRunTime(
                                                MIN_STAGE_DURATION_MS
                                              )}
                                        </span>
                                      </div>
                                    </>
                                  ) : (
                                    <div className="flex items-center justify-between py-0.5 text-[11px]">
                                      <span className="text-neutral-400 font-medium">
                                        {t("chat.executionTime", {
                                          defaultValue: "Çalışma Süresi",
                                        })}
                                        :
                                      </span>
                                      <span className="font-mono text-emerald-400 font-semibold">
                                        {tool.durationMs
                                          ? formatRunTime(tool.durationMs)
                                          : tool.invocations?.[0]?.durationMs
                                            ? formatRunTime(
                                                tool.invocations[0].durationMs
                                              )
                                            : formatRunTime(
                                                MIN_STAGE_DURATION_MS
                                              )}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <GraphStageCanvas
          agentDefinitionId={agent.agent_definition_id as string}
          pinnedVersionNo={pinnedVersionNo}
          nodeRunStatus={nodeRunStatus}
          nodeExecutionData={nodeExecutionData}
        />
      )}
    </div>
  );
}
