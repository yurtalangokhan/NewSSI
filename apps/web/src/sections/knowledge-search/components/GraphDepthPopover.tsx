"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgCheck, SvgChevronDown } from "@opal/icons";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import BlankIcon from "@/sections/knowledge-search/components/BlankIcon";
import type { GraphDepth } from "@/sections/knowledge-search/model/searchState";

const DEPTHS: readonly GraphDepth[] = [1, 2, 3];

interface GraphDepthPopoverProps {
  depth: GraphDepth;
  onDepthChange: (depth: GraphDepth) => void;
  /** Without `graph:read` the neighborhood cannot be expanded. */
  disabled: boolean;
}

/** How many hops around the matched entities the graph view shows. */
export default function GraphDepthPopover({
  depth,
  onDepthChange,
  disabled,
}: GraphDepthPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          prominence="secondary"
          size="md"
          rightIcon={SvgChevronDown}
          disabled={disabled}
          tooltip={
            disabled ? t("knowledgeSearch.graph.noPermission") : undefined
          }
        >
          {t("knowledgeSearch.graph.depth", { depth })}
        </Button>
      </Popover.Trigger>
      <Popover.Content align="start" width="md">
        <PopoverMenu>
          {DEPTHS.map((option) => (
            <LineItem
              key={option}
              icon={option === depth ? SvgCheck : BlankIcon}
              selected={option === depth}
              emphasized
              onClick={() => {
                onDepthChange(option);
                setOpen(false);
              }}
            >
              {t("knowledgeSearch.graph.depthOption", { count: option })}
            </LineItem>
          ))}
        </PopoverMenu>
      </Popover.Content>
    </Popover>
  );
}
