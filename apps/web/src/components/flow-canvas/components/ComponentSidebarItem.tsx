/**
 * One draggable entry in the component palette. Sets the drag payload key
 * FlowCanvas.tsx (Task 24) reads on drop —
 * "application/x-flow-component-type" — the documented contract between
 * these two tasks.
 *
 * Row styling ported verbatim from Langflow (MIT) —
 * vendor/langflow/pages/FlowPage/components/flowSidebarComponent/components/sidebarDraggableComponent.tsx:142-147:
 *   group/draggable flex cursor-grab items-center gap-2 rounded-md
 *   bg-muted p-1 px-2 hover:bg-secondary-hover/75
 * plus its `h-[18px] w-[18px] shrink-0` icon (:171) and
 * `truncate text-sm font-normal` label (:177).
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

"use client";

import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { useTranslation } from "react-i18next";
import type { ComponentTemplate } from "../types/componentTemplate";
import { resolveComponentIcon } from "../utils/resolveComponentIcon";

export const FLOW_COMPONENT_DRAG_MIME_TYPE =
  "application/x-flow-component-type";

export type ComponentSidebarItemProps = {
  template: ComponentTemplate;
  onDragStart?: (componentType: string) => void;
};

/** upstream :215 — the grip appears on hover/focus and is invisible
 * otherwise (`sm:opacity-0`, then `group-hover/draggable:opacity-100`). */
function DragGrip() {
  return (
    <span
      aria-hidden
      className="ml-auto grid shrink-0 grid-cols-2 gap-[2px] opacity-0 transition-opacity group-hover/draggable:opacity-100 group-focus/draggable:opacity-100"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <span
          key={i}
          className="h-[2px] w-[2px] rounded-full bg-muted-foreground"
        />
      ))}
    </span>
  );
}

export function ComponentSidebarItem({
  template,
  onDragStart,
}: ComponentSidebarItemProps) {
  const { t } = useTranslation();
  const displayName = t(
    `flowCanvas.components.${template.type}.name`,
    template.display_name
  );
  const description = t(
    `flowCanvas.components.${template.type}.description`,
    template.description || template.display_name
  );
  const Icon = resolveComponentIcon(template.icon);

  return (
    <SimpleTooltip tooltip={description}>
      <div
        role="button"
        tabIndex={0}
        draggable
        data-testid={`sidebar-item-${template.type}`}
        aria-label={displayName}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onDragStart?.(template.type);
          }
        }}
        onDragStart={(event) => {
          event.dataTransfer.setData(
            FLOW_COMPONENT_DRAG_MIME_TYPE,
            template.type
          );
          event.dataTransfer.setData("text/plain", template.type);
          event.dataTransfer.effectAllowed = "move";
          onDragStart?.(template.type);
        }}
        className="group/draggable flex h-8 cursor-grab select-none items-center gap-2 rounded-md px-2 text-canvas-fg outline-none ring-ring hover:bg-muted focus-visible:ring-1 active:cursor-grabbing"
      >
        <Icon className="h-[18px] w-[18px] shrink-0 text-muted-foreground" />
        <span className="truncate text-sm font-normal">{displayName}</span>
        {template.lifecycle !== "stable" && (
          <span className="shrink-0 text-xs uppercase text-muted-foreground">
            {template.lifecycle}
          </span>
        )}
        <DragGrip />
      </div>
    </SimpleTooltip>
  );
}
