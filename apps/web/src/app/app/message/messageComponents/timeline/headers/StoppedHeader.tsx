import React from "react";
import { SvgFold, SvgExpand } from "@opal/icons";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { cn, noProp } from "@/lib/utils";
import { useTranslation } from "react-i18next";

export interface StoppedHeaderProps {
  totalSteps: number;
  collapsible: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  hasStageSections?: boolean;
}

/** Header when user stopped/cancelled */
export const StoppedHeader = React.memo(function StoppedHeader({
  totalSteps,
  collapsible,
  isExpanded,
  onToggle,
  hasStageSections = false,
}: StoppedHeaderProps) {
  const { t } = useTranslation();
  const isInteractive = collapsible && (totalSteps > 0 || hasStageSections);

  return (
    <div
      role={isInteractive ? "button" : undefined}
      onClick={isInteractive ? onToggle : undefined}
      className={cn(
        "flex items-center justify-between w-full rounded-12",
        isInteractive ? "cursor-pointer" : "cursor-default"
      )}
      aria-disabled={isInteractive ? undefined : true}
    >
      <div className="px-[var(--timeline-header-text-padding-x)] py-[var(--timeline-header-text-padding-y)]">
        <Text as="p" mainUiAction text03>
          {t("timeline.interruptedThinking")}
        </Text>
      </div>

      {isInteractive &&
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
