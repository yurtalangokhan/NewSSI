"use client";

import type { ComponentType, SVGProps } from "react";
import { SvgBubbleText, SvgCpu, SvgHardDrive, SvgWorkflow } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

export interface AgentPreviewFact {
  label: string;
  value: string;
}

/**
 * Parses the flat "Model: X · Tools: N · Memory: on/off\n<prompt>" string
 * produced by the backend (build_agent_preview_text) into structured rows.
 */
export function parseAgentPreview(preview: string): {
  facts: AgentPreviewFact[];
  prompt?: string;
} {
  const [header, ...rest] = preview.split("\n");
  const prompt = rest.length > 0 ? rest.join("\n") : undefined;
  const facts = (header ?? "").split(" · ").map((segment) => {
    const separatorIndex = segment.indexOf(": ");
    if (separatorIndex === -1) {
      return { label: segment, value: "" };
    }
    return {
      label: segment.slice(0, separatorIndex),
      value: segment.slice(separatorIndex + 2),
    };
  });
  return { facts, prompt };
}

const FACT_ICONS: Record<string, IconComponent> = {
  Model: SvgCpu,
  Tools: SvgWorkflow,
  Memory: SvgHardDrive,
};

export interface AgentPreviewTooltipProps {
  preview: string;
}

export default function AgentPreviewTooltip({
  preview,
}: AgentPreviewTooltipProps) {
  const { facts, prompt } = parseAgentPreview(preview);

  return (
    <div className="flex max-w-xs flex-col gap-1.5">
      <div className="flex flex-col gap-1">
        {facts.map(({ label, value }) => {
          const Icon = FACT_ICONS[label] ?? SvgCpu;
          const isMemory = label === "Memory";
          return (
            <div key={label} className="flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5 shrink-0 text-text-light-03" />
              <Text as="span" secondaryBody className="text-text-light-03">
                {label}:
              </Text>
              <Text
                as="span"
                secondaryBody
                className={
                  isMemory && value === "on"
                    ? "text-status-success-05"
                    : "text-text-light-05"
                }
              >
                {value}
              </Text>
            </div>
          );
        })}
      </div>
      {prompt && (
        <div
          data-testid="agent-preview-prompt"
          className="flex items-start gap-1.5 border-t border-border-inverted-02 pt-1.5"
        >
          <SvgBubbleText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-light-03" />
          <Text
            as="span"
            secondaryBody
            className="text-text-light-03 line-clamp-3"
          >
            {prompt}
          </Text>
        </div>
      )}
    </div>
  );
}
