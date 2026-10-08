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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { StoreApi } from "zustand";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import type { ComponentTemplate } from "../types/componentTemplate";
import type { PortType } from "../types/flow";
import type { FlowStore } from "../stores/flowStore";
import { resolveComponentIcon } from "../utils/resolveComponentIcon";
import { getEffectiveOutputHandles } from "../utils/templateSchema";
import { PortDot } from "./PortDot";

export const FLOW_COMPONENT_DRAG_MIME_TYPE =
  "application/x-flow-component-type";

export type ComponentSidebarItemProps = {
  template: ComponentTemplate;
  /**
   * Fired when the user has completed a deliberate, atomic activation of
   * this item — currently only the Enter/Space keyboard path. NOT fired from
   * native `dragstart`: that event only means a drag session started, not
   * that it landed on the canvas, so recording usage there produced a
   * phantom "Recently used" entry for drags that never completed. The
   * confirmed-drop path (`useDropHandler`) records usage on its own once a
   * node is actually added.
   */
  onUsed?: (componentType: string) => void;
  /**
   * Optional so existing/standalone renders (and the row's own unit test)
   * keep working with no canvas mounted. Without it, hovering shows no port
   * dots and cannot glow anything — there is no store to publish to.
   */
  store?: StoreApi<FlowStore>;
};

/** upstream :215 — the grip appears on hover/focus and is invisible
 * otherwise (`sm:opacity-0`, then `group-hover/draggable:opacity-100`). */
function DragGrip() {
  return (
    <span
      aria-hidden
      className="grid shrink-0 grid-cols-2 gap-[2px] opacity-0 transition-opacity group-hover/draggable:opacity-100 group-focus/draggable:opacity-100"
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
  onUsed,
  store,
}: ComponentSidebarItemProps) {
  const { t } = useTranslation();
  const [isHovered, setIsHovered] = useState(false);
  const displayName = t(
    `flowCanvas.components.${template.type}.name`,
    template.display_name
  );
  const description = t(
    `flowCanvas.components.${template.type}.description`,
    template.description || template.display_name
  );
  const Icon = resolveComponentIcon(template.icon);
  // getEffectiveOutputHandles(..., {}) — the resting-state outputs with no
  // values set, i.e. exactly what this component would show the instant
  // it's dropped (design spec: flow-canvas-connect-ux, decision 6).
  const outputHandles = getEffectiveOutputHandles(template, {});
  const outputTypes = outputHandles.flatMap((h) => h.types) as PortType[];

  const handleHoverStart = () => {
    setIsHovered(true);
    if (outputTypes.length > 0) {
      store
        ?.getState()
        .setPaletteHoverOrigin({ types: outputTypes, handleType: "source" });
    }
  };
  const handleHoverEnd = () => {
    setIsHovered(false);
    if (outputTypes.length > 0) {
      store?.getState().setPaletteHoverOrigin(null);
    }
  };

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
            onUsed?.(template.type);
          }
        }}
        onDragStart={(event) => {
          event.dataTransfer.setData(
            FLOW_COMPONENT_DRAG_MIME_TYPE,
            template.type
          );
          event.dataTransfer.setData("text/plain", template.type);
          event.dataTransfer.effectAllowed = "move";
        }}
        onMouseEnter={handleHoverStart}
        onMouseLeave={handleHoverEnd}
        className="group/draggable flex h-8 cursor-grab select-none items-center gap-2 rounded-md px-2 text-canvas-fg outline-none ring-ring hover:bg-muted focus-visible:ring-1 active:cursor-grabbing"
      >
        <Icon className="h-[18px] w-[18px] shrink-0 text-muted-foreground" />
        <span className="truncate text-sm font-normal">{displayName}</span>
        {template.lifecycle !== "stable" && (
          <span className="shrink-0 text-xs uppercase text-muted-foreground">
            {t(
              `flowCanvas.sidebar.lifecycle.${template.lifecycle}`,
              template.lifecycle
            )}
          </span>
        )}
        {/* One wrapper carries the `ml-auto` push so the port-dot preview and
            the drag grip stay grouped at the row's right edge together —
            the dots sit immediately left of the grip, not wherever they'd
            otherwise fall next to the label. */}
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {isHovered && outputHandles.length > 0 && (
            // Each dot's ring extends ~3px past its own edge (box-shadow
            // paints outside the box, unlike a border, so flex's own gap
            // doesn't fully account for it) — gap-1 let two rings overlap
            // into one blob; gap-2 clears it.
            <span className="flex items-center gap-2.5">
              {outputHandles.map((h) => (
                <PortDot
                  key={h.name}
                  types={h.types}
                  testId={`sidebar-item-${template.type}-port-${h.name}`}
                />
              ))}
            </span>
          )}
          <DragGrip />
        </span>
      </div>
    </SimpleTooltip>
  );
}
