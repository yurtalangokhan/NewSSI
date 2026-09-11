"use client";

import React from "react";
import { SvgFold, SvgExpand, SvgAddLines, SvgMaximize2 } from "@opal/icons";
import { Button } from "@opal/components";
import Tag from "@/refresh-components/buttons/Tag";
import Text from "@/refresh-components/texts/Text";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { Section } from "@/layouts/general-layouts";
import { ContentAction } from "@opal/layouts";
import { formatDurationSeconds } from "@/lib/time";
import { cn, noProp } from "@/lib/utils";
import MemoriesModal from "@/refresh-components/modals/MemoriesModal";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import { useTranslation } from "react-i18next";

// =============================================================================
// MemoryTagWithTooltip
// =============================================================================

interface MemoryTagWithTooltipProps {
  memoryText: string | null;
  memoryOperation: "add" | "update" | null;
  memoryId: number | null;
  memoryIndex: number | null;
}

function MemoryTagWithTooltip({
  memoryText,
  memoryOperation,
  memoryId,
  memoryIndex,
}: MemoryTagWithTooltipProps) {
  const memoriesModal = useCreateModal();

  const operationLabel =
    memoryOperation === "add" ? "Added to memories" : "Updated memory";

  const tag = <Tag icon={SvgAddLines} label={operationLabel} />;

  if (!memoryText) return tag;

  return (
    <>
      <memoriesModal.Provider>
        <MemoriesModal
          initialTargetMemoryId={memoryId != null ? String(memoryId) : null}
          initialTargetIndex={memoryIndex}
          highlightFirstOnOpen
        />
      </memoriesModal.Provider>
      {memoriesModal.isOpen ? (
        <span>{tag}</span>
      ) : (
        <SimpleTooltip
          delayDuration={0}
          side="bottom"
          className="bg-background-neutral-00 text-text-01 shadow-md max-w-[17.5rem] p-1"
          tooltip={
            <Section flexDirection="column" gap={0.25} height="auto">
              <div className="p-1 w-full">
                <Text as="p" secondaryBody text03>
                  {memoryText}
                </Text>
              </div>
              <ContentAction
                icon={SvgAddLines}
                title={operationLabel}
                sizePreset="secondary"
                variant="body"
                prominence="muted"
                rightChildren={
                  <Button
                    prominence="tertiary"
                    size="sm"
                    icon={SvgMaximize2}
                    onClick={(e) => {
                      e.stopPropagation();
                      memoriesModal.toggle(true);
                    }}
                  />
                }
              />
            </Section>
          }
        >
          <span>{tag}</span>
        </SimpleTooltip>
      )}
    </>
  );
}

// =============================================================================
// CompletedHeader
// =============================================================================

export interface CompletedHeaderProps {
  totalSteps: number;
  collapsible: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  processingDurationSeconds?: number;
  generatedImageCount?: number;
  isMemoryOnly?: boolean;
  memoryText?: string | null;
  memoryOperation?: "add" | "update" | null;
  memoryId?: number | null;
  memoryIndex?: number | null;
  hasStageSections?: boolean;
}

/** Header when completed - handles both collapsed and expanded states */
export const CompletedHeader = React.memo(function CompletedHeader({
  totalSteps,
  collapsible,
  isExpanded,
  onToggle,
  processingDurationSeconds = 0,
  generatedImageCount = 0,
  isMemoryOnly = false,
  memoryText = null,
  memoryOperation = null,
  memoryId = null,
  memoryIndex = null,
  hasStageSections = false,
}: CompletedHeaderProps) {
  const { t } = useTranslation();
  const canToggle = collapsible && (totalSteps > 0 || hasStageSections);

  if (isMemoryOnly) {
    return (
      <div className="flex w-full justify-between">
        <div className="flex items-center px-[var(--timeline-header-text-padding-x)] py-[var(--timeline-header-text-padding-y)]">
          <MemoryTagWithTooltip
            memoryText={memoryText}
            memoryOperation={memoryOperation}
            memoryId={memoryId}
            memoryIndex={memoryIndex}
          />
        </div>
        {canToggle &&
          isExpanded &&
          (totalSteps > 0 ? (
            <Button
              prominence="tertiary"
              size="md"
              onClick={noProp(onToggle)}
              rightIcon={isExpanded ? SvgFold : SvgExpand}
              aria-label={
                isExpanded
                  ? t("timeline.collapseTimeline")
                  : t("timeline.expandTimeline")
              }
              aria-expanded={isExpanded}
            >
              {`${totalSteps} ${
                totalSteps === 1
                  ? t("timeline.stepSingular")
                  : t("timeline.stepPlural")
              }`}
            </Button>
          ) : (
            <Button
              prominence="tertiary"
              size="md"
              onClick={noProp(onToggle)}
              icon={isExpanded ? SvgFold : SvgExpand}
              aria-label={
                isExpanded
                  ? t("timeline.collapseTimeline")
                  : t("timeline.expandTimeline")
              }
              aria-expanded={isExpanded}
            />
          ))}
      </div>
    );
  }

  const durationText = processingDurationSeconds
    ? t("timeline.thoughtForDuration", {
        duration: formatDurationSeconds(processingDurationSeconds),
      })
    : t("timeline.thoughtForSomeTime");

  const imageText =
    generatedImageCount > 0
      ? `Generated ${generatedImageCount} ${
          generatedImageCount === 1 ? "image" : "images"
        }`
      : null;

  return (
    <div
      role={canToggle ? "button" : undefined}
      onClick={canToggle ? onToggle : undefined}
      className={cn(
        "flex items-center justify-between w-full",
        canToggle ? "cursor-pointer" : "cursor-default"
      )}
    >
      <div className="flex items-center gap-2 px-[var(--timeline-header-text-padding-x)] py-[var(--timeline-header-text-padding-y)]">
        <Text as="p" mainUiAction text03>
          {isExpanded ? durationText : imageText ?? durationText}
        </Text>
        {memoryOperation && !isExpanded && (
          <MemoryTagWithTooltip
            memoryText={memoryText}
            memoryOperation={memoryOperation}
            memoryId={memoryId}
            memoryIndex={memoryIndex}
          />
        )}
      </div>

      {canToggle &&
        (totalSteps > 0 ? (
          <Button
            prominence="tertiary"
            size="md"
            onClick={noProp(onToggle)}
            rightIcon={isExpanded ? SvgFold : SvgExpand}
            aria-label={
              isExpanded
                ? t("timeline.collapseTimeline")
                : t("timeline.expandTimeline")
            }
            aria-expanded={isExpanded}
          >
            {`${totalSteps} ${
              totalSteps === 1
                ? t("timeline.stepSingular")
                : t("timeline.stepPlural")
            }`}
          </Button>
        ) : (
          <Button
            prominence="tertiary"
            size="md"
            onClick={noProp(onToggle)}
            icon={isExpanded ? SvgFold : SvgExpand}
            aria-label={
              isExpanded
                ? t("timeline.collapseTimeline")
                : t("timeline.expandTimeline")
            }
            aria-expanded={isExpanded}
          />
        ))}
    </div>
  );
});
