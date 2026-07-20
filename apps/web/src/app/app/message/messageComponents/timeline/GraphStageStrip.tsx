"use client";

import React, { useMemo } from "react";
import { SvgWorkflow } from "@opal/icons";
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import Text from "@/refresh-components/texts/Text";
import Tag from "@/refresh-components/buttons/Tag";
import { cn } from "@/lib/utils";

interface StageDefinition {
  key: string;
  label: string;
}

interface StageProgress {
  activeStageName: string | null;
  completedStageNames: Set<string>;
}

export interface GraphStageStripProps {
  agent: MinimalPersonaSnapshot;
  packets: Packet[];
}

function getStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function extractStageLabel(stage: Record<string, unknown>, index: number): string {
  return (
    getStringValue(stage.name) ??
    getStringValue(stage.title) ??
    getStringValue(stage.label) ??
    getStringValue(stage.stage_name) ??
    `Stage ${index + 1}`
  );
}

function getStageDefinitions(agent: MinimalPersonaSnapshot): StageDefinition[] {
  const stageSource =
    Array.isArray(agent.stages) && agent.stages.length > 0
      ? agent.stages
      : Array.isArray(agent.sub_agents) && agent.sub_agents.length > 0
        ? agent.sub_agents
        : [];

  return stageSource
    .map((stage, index) => {
      if (!stage || typeof stage !== "object" || Array.isArray(stage)) {
        return null;
      }

      const stageLabel = extractStageLabel(stage, index);
      return {
        key: `${index}-${stageLabel}`,
        label: stageLabel,
      };
    })
    .filter((stage): stage is StageDefinition => stage !== null);
}

function getStageProgress(
  packets: Packet[],
  stageDefinitions: StageDefinition[]
): StageProgress {
  const knownStageNames = new Set(stageDefinitions.map((stage) => stage.label));
  const completedStageNames = new Set<string>();
  let activeStageName: string | null = null;

  for (const packet of packets) {
    if (
      packet.obj.type !== PacketType.GRAPH_STAGE_START &&
      packet.obj.type !== PacketType.GRAPH_STAGE_END
    ) {
      continue;
    }

    const stageName = getStringValue((packet.obj as { stage_name?: unknown }).stage_name);
    if (!stageName) {
      continue;
    }

    if (stageDefinitions.length > 0 && !knownStageNames.has(stageName)) {
      continue;
    }

    if (packet.obj.type === PacketType.GRAPH_STAGE_START) {
      if (activeStageName && activeStageName !== stageName) {
        completedStageNames.add(activeStageName);
      }
      activeStageName = stageName;
      continue;
    }

    completedStageNames.add(stageName);
    if (activeStageName === stageName) {
      activeStageName = null;
    }
  }

  return {
    activeStageName,
    completedStageNames,
  };
}

export default function GraphStageStrip({
  agent,
  packets,
}: GraphStageStripProps) {
  const stageDefinitions = useMemo(() => getStageDefinitions(agent), [agent]);
  const { activeStageName, completedStageNames } = useMemo(
    () => getStageProgress(packets, stageDefinitions),
    [packets, stageDefinitions]
  );

  if (stageDefinitions.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2 rounded-12 border border-border-01 bg-background-tint-00 px-3 py-2">
      <div className="flex items-center gap-2">
        <SvgWorkflow className="size-4 stroke-text-03" />
        <Text as="p" secondaryBody text03>
          Graph stages
        </Text>
      </div>

      <div className="flex flex-wrap gap-2">
        {stageDefinitions.map((stage) => {
          const isActive = stage.label === activeStageName;
          const isCompleted = completedStageNames.has(stage.label) && !isActive;

          return (
            <Tag
              key={stage.key}
              label={stage.label}
              variant="editable"
              className={cn(
                "border border-transparent",
                isActive && "border-border-01 bg-background-tint-03",
                isCompleted && "opacity-80"
              )}
            />
          );
        })}
      </div>
    </div>
  );
}