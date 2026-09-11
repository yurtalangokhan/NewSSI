/**
 * Ported from Langflow (MIT) — src/frontend/src/CustomNodes/GenericNode/components/NodeToolbarComponent
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Trimmed to the actions that mean something in our architecture (see
 * task-27-report.md for the full table):
 * - Delete, Duplicate, Copy — ported
 * - Rename — NOT ported: no field exists in FlowNodeData/WireFlowNode to
 *   persist a per-node display-name override to (same finding as Task
 *   26's report). A local-only rename would silently lose it on reload.
 * - Freeze/disable — evaluated, not ported: Langflow's freeze caches a
 *   vertex's last output, which has no counterpart in our runtime (no
 *   per-node output cache). A real "temporarily bypass this node" need
 *   would be a new feature with backend implications — flagged for P5+,
 *   not invented here.
 * - Code/edit component, Update component, Download/share — dropped per
 *   Task 20's triage (user-authored Python, Langflow component
 *   versioning, and Langflow-product-specific actions respectively).
 *
 * Post-P4 follow-up (flow-canvas-progress.md, "Post-P4 additions"): the
 * first pass rendered all four actions as flat, unlabelled icons — upstream
 * splits its toolbar into always-visible labelled `ToolbarButton`s (Code,
 * Parameters, Freeze/Tool Mode) plus a `Select`-driven "..." dropdown for
 * everything else (Duplicate, Copy, Delete, Save, ...). Restructured to
 * match that two-tier shape using this project's own dropdown primitive
 * (`Popover` + `LineItem`, already established by `ActionsPopover`) rather
 * than upstream's shadcn `Select`. "Parameters" stays the one always-visible
 * labelled button (upstream's `ToolbarButton` icon+label+isActive pattern);
 * Duplicate/Copy/Delete move into the "..." menu, matching upstream's own
 * placement of those three actions inside its dropdown, not its toolbar row.
 *
 * Rendered by `TemplateNode.tsx` only when its node is `selected`, using
 * xyflow's own `NodeToolbar` for positioning above the node.
 *
 * Brief: .tmp/flow-canvas-task-27-brief.md
 */

"use client";

import { useState, type SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { NodeToolbar as XyNodeToolbar, Position } from "@xyflow/react";
import { useStore, type StoreApi } from "zustand";
import { cn } from "@/lib/utils";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import LineItem from "@/refresh-components/buttons/LineItem";
import Popover from "@/refresh-components/Popover";
import Text from "@/refresh-components/texts/Text";
import {
  SvgCopy,
  SvgMaximize2,
  SvgMinimize2,
  SvgMoreHorizontal,
  SvgPlug,
  SvgSliders,
  SvgTrash,
} from "@opal/icons";
import type { FlowStore } from "../stores/flowStore";

/** Duplicate and Copy are different actions and must not share a glyph.
 * Langflow distinguishes them with lucide's `Copy` / `CopyPlus`; there is
 * no `CopyPlus` equivalent in `@opal/icons`, so this composes the same
 * idea — the copy glyph with a plus badge — rather than shipping two
 * identical buttons. */
function SvgCopyPlus(props: SVGProps<SVGSVGElement>) {
  return (
    <span className="relative inline-flex">
      <SvgCopy {...props} />
      <svg
        viewBox="0 0 8 8"
        aria-hidden
        className="absolute -bottom-0.5 -right-0.5 h-2 w-2"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
      >
        <path d="M4 1.5v5M1.5 4h5" />
      </svg>
    </span>
  );
}

export type NodeToolbarProps = {
  nodeId: string;
  store: StoreApi<FlowStore>;
  hasParameters?: boolean;
  hasToolMode?: boolean;
  toolModeValue?: boolean;
  onToolModeChange?: (value: boolean) => void;
};

export function NodeToolbar({
  nodeId,
  store,
  hasParameters = true,
  hasToolMode = false,
  toolModeValue = false,
  onToolModeChange,
}: NodeToolbarProps) {
  const { t } = useTranslation();
  const takeSnapshot = useStore(store, (s) => s.takeSnapshot);
  const setNodes = useStore(store, (s) => s.setNodes);
  const setEdges = useStore(store, (s) => s.setEdges);
  const setClipboard = useStore(store, (s) => s.setClipboard);
  const paste = useStore(store, (s) => s.paste);
  const isInspectorOpen = useStore(store, (s) => s.isInspectorOpen);
  const setInspectorOpen = useStore(store, (s) => s.setInspectorOpen);
  const isMinimized = useStore(store, (s) => s.minimizedNodeIds.has(nodeId));
  const toggleMinimized = useStore(store, (s) => s.toggleMinimized);
  const [menuOpen, setMenuOpen] = useState(false);

  function handleDelete() {
    takeSnapshot();
    setNodes((current) => current.filter((n) => n.id !== nodeId));
    setEdges((current) =>
      current.filter((e) => e.source !== nodeId && e.target !== nodeId)
    );
    setMenuOpen(false);
  }

  function handleDuplicate() {
    const node = store.getState().nodes.find((n) => n.id === nodeId);
    if (!node) return;
    takeSnapshot();
    paste(
      { nodes: [node], edges: [] },
      { x: node.position.x + 40, y: node.position.y + 40 }
    );
    setMenuOpen(false);
  }

  function handleCopy() {
    const node = store.getState().nodes.find((n) => n.id === nodeId);
    if (!node) return;
    setClipboard({ nodes: [node], edges: [] });
    setMenuOpen(false);
  }

  function handleToolModeToggle() {
    if (!onToolModeChange) return;
    takeSnapshot();
    onToolModeChange(!toolModeValue);
  }

  return (
    <XyNodeToolbar nodeId={nodeId} position={Position.Top}>
      <div
        className="nodrag flex items-center gap-1 rounded-08 border border-canvas-border bg-canvas-panel p-1 shadow-md"
        data-testid={`node-toolbar-${nodeId}`}
      >
        {hasToolMode && (
          <Button
            internal
            size="md"
            aria-pressed={toolModeValue}
            aria-label={t(
              "flowCanvas.nodeToolbar.toolMode",
              "Use as agent tool"
            )}
            className={cn(toolModeValue && "bg-background-tint-02")}
            onClick={handleToolModeToggle}
            data-testid={`node-toolbar-tool-mode-${nodeId}`}
          >
            <span className="flex items-center gap-1.5">
              <SvgPlug className="h-4 w-4 button-main-internal-icon" />
              <Text
                secondaryAction
                className="whitespace-nowrap button-main-internal-text"
              >
                {t("flowCanvas.nodeToolbar.toolMode", "Use as agent tool")}
              </Text>
              {/* Visual only — a real <Switch> here would nest a <button>
                  inside this one. The click target is this whole button,
                  matching upstream's own toggle-inside-a-div-role-button
                  (nodeToolbarComponent/index.tsx `showToogle={false}`). */}
              <span
                aria-hidden="true"
                className={cn(
                  "pointer-events-none inline-flex h-[1.125rem] w-[2rem] shrink-0 items-center rounded-full transition-colors",
                  toolModeValue ? "switch-normal-checked" : "switch-normal"
                )}
              >
                <span
                  className={cn(
                    "block h-[0.875rem] w-[0.875rem] rounded-full switch-thumb transition-transform",
                    toolModeValue ? "translate-x-[15px]" : "translate-x-[1px]"
                  )}
                />
              </span>
            </span>
          </Button>
        )}

        {hasParameters ? (
          <>
            <Button
              internal
              size="md"
              aria-pressed={isInspectorOpen}
              aria-label={
                isInspectorOpen
                  ? t("flowCanvas.nodeToolbar.hideDetails", "Hide node details")
                  : t("flowCanvas.nodeToolbar.showDetails", "Show node details")
              }
              className={cn(isInspectorOpen && "bg-background-tint-02")}
              onClick={() => setInspectorOpen(!isInspectorOpen)}
            >
              <span className="flex items-center gap-1.5">
                <SvgSliders className="h-4 w-4 button-main-internal-icon" />
                <Text
                  secondaryAction
                  className="whitespace-nowrap button-main-internal-text"
                >
                  {t("flowCanvas.nodeToolbar.parameters", "Parameters")}
                </Text>
              </span>
            </Button>

            <Popover open={menuOpen} onOpenChange={setMenuOpen}>
              <Popover.Trigger asChild>
                <div>
                  <IconButton
                    icon={SvgMoreHorizontal}
                    tooltip={t(
                      "flowCanvas.nodeToolbar.moreActions",
                      "More actions"
                    )}
                    aria-label={t(
                      "flowCanvas.nodeToolbar.moreActions",
                      "More actions"
                    )}
                    small
                  />
                </div>
              </Popover.Trigger>
              <Popover.Content align="start" width="md">
                <Popover.Menu>
                  <LineItem
                    icon={SvgCopyPlus}
                    aria-label={t(
                      "flowCanvas.nodeToolbar.duplicate",
                      "Duplicate"
                    )}
                    onClick={handleDuplicate}
                    rightChildren={
                      <span className="text-[10px] font-medium tracking-tight text-muted-foreground ml-auto pl-3">
                        {typeof window !== "undefined" &&
                        /macintosh|mac os x/i.test(navigator.userAgent)
                          ? "⌘D"
                          : "Ctrl+D"}
                      </span>
                    }
                  >
                    {t("flowCanvas.nodeToolbar.duplicate", "Duplicate")}
                  </LineItem>
                  <LineItem
                    icon={SvgCopy}
                    aria-label={t("flowCanvas.nodeToolbar.copy", "Copy")}
                    onClick={handleCopy}
                    rightChildren={
                      <span className="text-[10px] font-medium tracking-tight text-muted-foreground ml-auto pl-3">
                        {typeof window !== "undefined" &&
                        /macintosh|mac os x/i.test(navigator.userAgent)
                          ? "⌘C"
                          : "Ctrl+C"}
                      </span>
                    }
                  >
                    {t("flowCanvas.nodeToolbar.copy", "Copy")}
                  </LineItem>
                  <LineItem
                    icon={isMinimized ? SvgMaximize2 : SvgMinimize2}
                    aria-label={
                      isMinimized
                        ? t("flowCanvas.nodeToolbar.expand", "Expand")
                        : t("flowCanvas.nodeToolbar.minimize", "Minimize")
                    }
                    onClick={() => {
                      toggleMinimized(nodeId);
                      setMenuOpen(false);
                    }}
                    rightChildren={
                      <span className="text-[10px] font-medium tracking-tight text-muted-foreground ml-auto pl-3">
                        M
                      </span>
                    }
                  >
                    {isMinimized
                      ? t("flowCanvas.nodeToolbar.expand", "Expand")
                      : t("flowCanvas.nodeToolbar.minimize", "Minimize")}
                  </LineItem>
                  {null}
                  <LineItem
                    danger
                    icon={SvgTrash}
                    aria-label={t("flowCanvas.nodeToolbar.delete", "Delete")}
                    onClick={handleDelete}
                    rightChildren={
                      <span className="text-[10px] font-medium tracking-tight text-destructive/80 ml-auto pl-3">
                        {typeof window !== "undefined" &&
                        /macintosh|mac os x/i.test(navigator.userAgent)
                          ? "⌫"
                          : "Del"}
                      </span>
                    }
                  >
                    {t("flowCanvas.nodeToolbar.delete", "Delete")}
                  </LineItem>
                </Popover.Menu>
              </Popover.Content>
            </Popover>
          </>
        ) : (
          <div className="flex items-center gap-0.5">
            <IconButton
              icon={SvgCopyPlus}
              tooltip={t("flowCanvas.nodeToolbar.duplicate", "Duplicate")}
              aria-label={t("flowCanvas.nodeToolbar.duplicate", "Duplicate")}
              onClick={handleDuplicate}
              small
            />
            <IconButton
              icon={SvgCopy}
              tooltip={t("flowCanvas.nodeToolbar.copy", "Copy")}
              aria-label={t("flowCanvas.nodeToolbar.copy", "Copy")}
              onClick={handleCopy}
              small
            />
            <IconButton
              icon={isMinimized ? SvgMaximize2 : SvgMinimize2}
              tooltip={
                isMinimized
                  ? t("flowCanvas.nodeToolbar.expand", "Expand")
                  : t("flowCanvas.nodeToolbar.minimize", "Minimize")
              }
              aria-label={
                isMinimized
                  ? t("flowCanvas.nodeToolbar.expand", "Expand")
                  : t("flowCanvas.nodeToolbar.minimize", "Minimize")
              }
              onClick={() => toggleMinimized(nodeId)}
              small
            />
            <IconButton
              icon={SvgTrash}
              tooltip={t("flowCanvas.nodeToolbar.delete", "Delete")}
              aria-label={t("flowCanvas.nodeToolbar.delete", "Delete")}
              onClick={handleDelete}
              small
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            />
          </div>
        )}
      </div>
    </XyNodeToolbar>
  );
}
