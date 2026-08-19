"use client";

import { ToolSnapshot } from "@/lib/tools/interfaces";
import { getIconForAction } from "@/app/app/services/actionUtils";
import Text from "@/refresh-components/texts/Text";
import IconButton from "@/refresh-components/buttons/IconButton";
import { SvgInfoSmall } from "@opal/icons";

export interface StaticToolListItemProps {
  tool: ToolSnapshot;
}

/**
 * A read-only row for tools that are simply attached to the agent (built-in
 * tools-service tools, RAG-derived tools) rather than individually
 * configurable. Unlike ActionLineItem, it isn't clickable and doesn't offer
 * enable/disable or force-pin controls — it just names the tool and, if a
 * description exists, exposes it behind a small info affordance.
 */
export default function StaticToolListItem({ tool }: StaticToolListItemProps) {
  const Icon = getIconForAction(tool);
  const label = tool.display_name || tool.name;

  return (
    <div
      data-testid={`static-tool-${tool.name}`}
      className="flex flex-row w-full items-center gap-2 p-2"
    >
      <Icon className="h-[1rem] w-[1rem] shrink-0 stroke-text-03" />
      <Text mainUiMuted className="flex-1 truncate text-left">
        {label}
      </Text>
      {tool.description && (
        <IconButton
          icon={SvgInfoSmall}
          internal
          small
          tooltip={tool.description}
          aria-label={tool.description}
          className="shrink-0"
        />
      )}
    </div>
  );
}
