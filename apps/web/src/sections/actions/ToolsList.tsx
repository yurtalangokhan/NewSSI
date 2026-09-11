"use client";

import React from "react";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import { Button as OpalButton } from "@opal/components";
import FadingEdgeContainer from "@/refresh-components/FadingEdgeContainer";
import ToolItemSkeleton from "@/sections/actions/skeleton/ToolItemSkeleton";
import EnabledCount from "@/refresh-components/EnabledCount";
import { SvgEye, SvgXCircle } from "@opal/icons";
import Button from "@/refresh-components/buttons/Button";
import { useTranslation } from "react-i18next";

export interface ToolsListProps {
  // Loading state
  isFetching?: boolean;

  // Tool count for footer
  totalCount?: number;
  enabledCount?: number;
  showOnlyEnabled?: boolean;
  onToggleShowOnlyEnabled?: () => void;
  onUpdateToolsStatus?: (enabled: boolean) => void;

  // Empty state of filtered tools
  isEmpty?: boolean;
  searchQuery?: string;
  emptyMessage?: string;
  emptySearchMessage?: string;

  // Content
  children?: React.ReactNode;

  // Left action (for refresh button and last verified text)
  leftAction?: React.ReactNode;

  // Styling
  className?: string;
}

const ToolsList: React.FC<ToolsListProps> = ({
  isFetching = false,
  totalCount,
  enabledCount = 0,
  showOnlyEnabled = false,
  onToggleShowOnlyEnabled,
  onUpdateToolsStatus,
  isEmpty = false,
  searchQuery,
  emptyMessage,
  emptySearchMessage,
  children,
  leftAction,
  className,
}) => {
  const { t } = useTranslation();
  const resolvedEmptyMessage = emptyMessage ?? t("tools.noToolsAvailable");
  const resolvedEmptySearchMessage =
    emptySearchMessage ?? t("tools.noToolsFound");
  const showFooter =
    totalCount !== undefined && enabledCount !== undefined && totalCount > 0;

  return (
    <>
      <FadingEdgeContainer
        direction="bottom"
        className={cn(
          "flex flex-col gap-1 items-start max-h-[30vh] overflow-y-auto",
          className
        )}
      >
        {isFetching ? (
          Array.from({ length: 5 }).map((_, index) => (
            <ToolItemSkeleton key={`skeleton-${index}`} />
          ))
        ) : isEmpty ? (
          <div className="flex items-center justify-center w-full py-8">
            <Text as="p" text03 mainUiBody>
              {searchQuery ? resolvedEmptySearchMessage : resolvedEmptyMessage}
            </Text>
          </div>
        ) : (
          children
        )}
      </FadingEdgeContainer>

      {/* Footer showing enabled tool count with filter toggle */}
      {showFooter && !(totalCount === 0) && !isFetching && (
        <div className="pt-2 px-2">
          <div className="flex items-center justify-between gap-2 w-full">
            {/* Left action area */}
            {leftAction}

            {/* Right action area */}
            <div className="flex items-center gap-1 ml-auto">
              {enabledCount > 0 && (
                <EnabledCount
                  enabledCount={enabledCount}
                  totalCount={totalCount}
                  name="tool"
                />
              )}
              {onToggleShowOnlyEnabled && enabledCount > 0 && (
                <OpalButton
                  icon={SvgEye}
                  prominence="tertiary"
                  size="sm"
                  onClick={onToggleShowOnlyEnabled}
                  transient={showOnlyEnabled}
                  tooltip={
                    showOnlyEnabled
                      ? t("tools.showAllTools")
                      : t("tools.showOnlyEnabled")
                  }
                  aria-label={
                    showOnlyEnabled
                      ? t("tools.showAllTools")
                      : t("tools.showOnlyEnabledTools")
                  }
                />
              )}
              {onUpdateToolsStatus && enabledCount > 0 && (
                <OpalButton
                  icon={SvgXCircle}
                  prominence="tertiary"
                  size="sm"
                  onClick={() => onUpdateToolsStatus(false)}
                  tooltip={t("tools.disableAllTools")}
                  aria-label={t("tools.disableAllTools")}
                />
              )}
              {onUpdateToolsStatus && enabledCount === 0 && (
                <Button tertiary onClick={() => onUpdateToolsStatus(true)}>
                  {t("tools.enableAllTools")}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
ToolsList.displayName = "ToolsList";

export default ToolsList;
