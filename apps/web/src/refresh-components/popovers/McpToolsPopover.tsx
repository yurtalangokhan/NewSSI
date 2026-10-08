"use client";

import React, { useMemo, useState } from "react";
import {
  AgentToolEntry,
  knowledgeSourceKind,
  resolveAgentTools,
} from "@/lib/api/domains/agents/agentTools";
import { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import Popover from "@/refresh-components/Popover";
import Chip from "@/refresh-components/Chip";
import Text from "@/refresh-components/texts/Text";
import { Button, Tag } from "@opal/components";
import { SvgActions, SvgGlobe, SvgSearch } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface McpToolsPopoverProps {
  selectedAgent?: MinimalPersonaSnapshot;
  disabled?: boolean;
}

function toolIcon(name: string) {
  if (knowledgeSourceKind(name) || name.includes("search")) return SvgSearch;
  if (name.includes("web") || name.includes("fetch")) return SvgGlobe;
  return SvgActions;
}

interface ToolRowProps {
  tool: AgentToolEntry;
  badge?: string;
  activeLabel: string;
}

function ToolRow({ tool, badge, activeLabel }: ToolRowProps) {
  const IconComponent = toolIcon(tool.name);
  return (
    <div className="px-3 py-2 hover:bg-background-tint-01 transition-colors flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0">
        <div className="w-6 h-6 rounded-08 bg-action-link-01 flex items-center justify-center shrink-0 text-action-link-05">
          <IconComponent size={13} />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Text as="p" secondaryAction text05 className="truncate">
              {tool.displayName}
            </Text>
            {badge && <Tag title={badge} color="purple" />}
          </div>
          {!badge && tool.description && (
            <Text
              as="p"
              secondaryBody
              text03
              className="truncate max-w-[240px]"
            >
              {tool.description}
            </Text>
          )}
        </div>
      </div>
      <Tag title={activeLabel} color="green" />
    </div>
  );
}

export default function McpToolsPopover({
  selectedAgent,
  disabled = false,
}: McpToolsPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const tools = useMemo(
    () => resolveAgentTools(selectedAgent),
    [selectedAgent]
  );

  const knowledgeSources = tools.filter((tool) =>
    knowledgeSourceKind(tool.name)
  );
  const otherTools = tools.filter((tool) => !knowledgeSourceKind(tool.name));
  const showsKnowledge = knowledgeSources.length > 0;
  const activeLabel = t("inputBar.mcpToolsActive");

  const buttonLabel = showsKnowledge
    ? `${t("inputBar.knowledgeSourcesButton")} (${knowledgeSources.length})`
    : `${t("inputBar.mcpToolsButton")} (${tools.length})`;
  const countLabel = showsKnowledge
    ? t("inputBar.knowledgeSourcesCount", { count: knowledgeSources.length })
    : t("inputBar.toolsCount", { count: tools.length });
  const HeaderIcon = showsKnowledge ? SvgSearch : SvgActions;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <div data-testid="mcp-tools-toggle">
          <Button
            icon={HeaderIcon}
            onClick={() => setOpen((prev) => !prev)}
            variant="select"
            selected={open}
            disabled={disabled}
            tooltip={t(
              showsKnowledge
                ? "inputBar.knowledgeSourcesTooltip"
                : "inputBar.mcpToolsTooltip"
            )}
          >
            {buttonLabel}
          </Button>
        </div>
      </Popover.Trigger>
      <Popover.Content side="top" align="start" width="xl">
        <Popover.Menu>
          <div className="px-3 py-2.5 border-b border-border-01 bg-background-tint-01">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <HeaderIcon
                  size={14}
                  className="text-action-link-05 shrink-0"
                />
                <Text secondaryAction text05>
                  {t(
                    showsKnowledge
                      ? "inputBar.knowledgeSourcesTitle"
                      : "inputBar.mcpToolsTitle"
                  )}
                </Text>
              </div>
              <Chip>{countLabel}</Chip>
            </div>
            <Text as="p" secondaryBody text03 className="mt-1">
              {t(
                showsKnowledge
                  ? "inputBar.knowledgeSourcesDescription"
                  : "inputBar.mcpToolsDescription"
              )}
            </Text>
          </div>

          {tools.length === 0 ? (
            <div className="py-5 px-4 text-center">
              <SvgActions
                size={22}
                className="mx-auto text-text-03 opacity-40 mb-2"
              />
              <Text as="p" secondaryAction text04>
                {t("inputBar.noMcpTools")}
              </Text>
              <Text as="p" secondaryBody text03 className="mt-1">
                {t("inputBar.noMcpToolsHint")}
              </Text>
            </div>
          ) : (
            <div className="max-h-[260px] overflow-y-auto divide-y divide-border-01 py-1">
              {(showsKnowledge ? knowledgeSources : tools).map((tool) => (
                <ToolRow
                  key={tool.key}
                  tool={tool}
                  badge={knowledgeSourceKind(tool.name)}
                  activeLabel={activeLabel}
                />
              ))}
              {showsKnowledge && otherTools.length > 0 && (
                <>
                  <div className="px-3 pt-2.5 pb-1">
                    <Text figureSmallLabel text03>
                      {t("inputBar.otherToolsSection")}
                    </Text>
                  </div>
                  {otherTools.map((tool) => (
                    <ToolRow
                      key={tool.key}
                      tool={tool}
                      activeLabel={activeLabel}
                    />
                  ))}
                </>
              )}
            </div>
          )}
        </Popover.Menu>
      </Popover.Content>
    </Popover>
  );
}
