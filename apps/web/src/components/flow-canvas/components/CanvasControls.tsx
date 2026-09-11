/**
 * Langflow's canvas control cluster.
 *
 * Note on provenance, so the next reader isn't misled: unlike the node,
 * edge and sidebar ports, the upstream file
 * (`components/core/canvasControlsComponent/`) is *not* in
 * `vendor/langflow` — Task 20 vendored `components/core/parameterRenderComponent`
 * only. What *is* vendored is the exact class string Langflow applies to
 * this cluster, in
 * `pages/FlowPage/components/PageComponent/MemoizedComponents.tsx:52-55`:
 *
 *   react-flow__controls !top-auto !m-2 flex gap-1.5 rounded-md
 *   border border-secondary-hover bg-canvas-panel p-0.5 text-primary shadow
 *   transition-all duration-300 [&>button]:border-0 [&>button]:bg-canvas-panel
 *   hover:[&>button]:bg-accent
 *
 * The container styling below is that string; the buttons inside are
 * built to match it, not copied from a file this repo doesn't have.
 */

"use client";

import { Panel, useReactFlow, useStore as useRfStore } from "@xyflow/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
// `@opal/icons` has no unlock glyph — the lock button conveys state
// through its active styling instead. Checked against
// lib/opal/src/icons/index.ts, not assumed.
import {
  SvgExpand,
  SvgLock,
  SvgMaximize2,
  SvgMinimize2,
  SvgMinus,
  SvgPlus,
  SvgStickyNote,
} from "@opal/icons";

/** Fullscreen is *not* the browser Fullscreen API here: `next.config.js`
 * ships a deny-all `Permissions-Policy` including `fullscreen=()`, so
 * `requestFullscreen()` throws "Disallowed by permissions policy" on this
 * origin. That header is deliberate hardening and isn't this component's
 * to relax, so the canvas expands to fill the viewport instead. The only
 * visible difference is that the browser's own chrome stays put.
 *
 * State lives in the flow store (see `FlowStore.isFullscreen`) and the
 * class is applied by `FlowCanvas` through React — not by reaching into
 * the DOM from here, which would strand a `position: fixed` element over
 * the app if this component unmounted while expanded. */

function ControlButton({
  label,
  onClick,
  active,
  compact,
  children,
  testId,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  compact?: boolean;
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <SimpleTooltip tooltip={label} side="top">
      <button
        type="button"
        aria-label={label}
        data-testid={testId}
        onClick={onClick}
        className={cn(
          "flex items-center justify-center rounded border-0 bg-canvas-panel text-primary transition-colors hover:bg-accent",
          compact ? "h-6 w-6" : "h-7 w-7",
          active && "bg-accent"
        )}
      >
        {children}
      </button>
    </SimpleTooltip>
  );
}

export type CanvasControlsProps = {
  locked?: boolean;
  onToggleLock?: () => void;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
  onAddNote?: () => void;
  compact?: boolean;
};

export function CanvasControls({
  locked,
  onToggleLock,
  isFullscreen,
  onToggleFullscreen,
  onAddNote,
  compact = false,
}: CanvasControlsProps) {
  const { t } = useTranslation();
  const { zoomIn, zoomOut, fitView, zoomTo } = useReactFlow();
  const zoom = useRfStore((s) => s.transform[2]);
  const roundedZoom = Math.round(zoom * 100);
  const formattedZoom = t("flowCanvas.controls.zoomFormat", {
    value: roundedZoom,
    defaultValue: "{{value}}%",
  });
  const [isEditingZoom, setIsEditingZoom] = useState(false);
  const [zoomInputValue, setZoomInputValue] = useState("");
  const zoomInputRef = useRef<HTMLInputElement>(null);

  const handleFit = useCallback(() => fitView({ duration: 200 }), [fitView]);

  const handleResetZoom = useCallback(
    (e?: React.MouseEvent) => {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      setIsEditingZoom(false);
      zoomTo(1, { duration: 200 });
    },
    [zoomTo]
  );

  const applyZoom = useCallback(
    (valStr: string) => {
      setIsEditingZoom(false);
      const clean = valStr.replace(/%/g, "").trim();
      const parsed = parseFloat(clean);
      if (!isNaN(parsed) && parsed > 0) {
        const clamped = Math.min(Math.max(parsed, 25), 200);
        zoomTo(clamped / 100, { duration: 200 });
      }
    },
    [zoomTo]
  );

  useEffect(() => {
    if (isEditingZoom) {
      setZoomInputValue(`${Math.round(zoom * 100)}`);
      requestAnimationFrame(() => {
        if (zoomInputRef.current) {
          zoomInputRef.current.focus();
          zoomInputRef.current.select();
        }
      });
    }
  }, [isEditingZoom, zoom]);

  const iconClass = compact ? "h-3.5 w-3.5" : "h-4 w-4";

  // Langflow floats this cluster at the bottom **centre** of the canvas
  // as one horizontal pill, with the zoom percentage inline — not as a
  // vertical stack in the corner, which is xyflow's default.
  return (
    <Panel
      position="bottom-center"
      data-testid="canvas-controls"
      // Deliberately NOT `react-flow__controls` — xyflow's stylesheet sets
      // `flex-direction: column` on that class, which kept this cluster
      // vertical no matter what `flex` was added alongside it.
      className={cn(
        "!m-0 flex flex-row items-center border border-canvas-border bg-canvas-panel text-primary shadow-md",
        compact
          ? "!mb-2.5 gap-0.5 rounded-md p-0.5 shadow-sm"
          : "!mb-4 gap-1 rounded-lg p-1"
      )}
    >
      <ControlButton
        label={t("flowCanvas.controls.zoomOut", "Zoom Out")}
        onClick={() => zoomOut()}
        testId="canvas-zoom-out"
        compact={compact}
      >
        <SvgMinus className={iconClass} />
      </ControlButton>
      {isEditingZoom ? (
        <input
          ref={zoomInputRef}
          type="text"
          inputMode="numeric"
          value={zoomInputValue}
          onChange={(e) => setZoomInputValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              applyZoom(zoomInputValue);
            } else if (e.key === "Escape") {
              setIsEditingZoom(false);
            }
          }}
          onBlur={() => applyZoom(zoomInputValue)}
          onDoubleClick={handleResetZoom}
          className={cn(
            "rounded border border-border bg-canvas-panel text-center tabular-nums text-primary focus:border-primary focus:outline-none",
            compact ? "h-6 w-10 px-0.5 text-[11px]" : "h-7 w-12 px-1 text-xs"
          )}
          data-testid="canvas-zoom-input"
          aria-label={t(
            "flowCanvas.controls.setZoomAria",
            "Set zoom percentage"
          )}
        />
      ) : (
        <SimpleTooltip
          tooltip={t(
            "flowCanvas.controls.zoomTooltip",
            "Click to edit, double-click for 100%"
          )}
          side="top"
        >
          <button
            type="button"
            onClick={() => setIsEditingZoom(true)}
            onDoubleClick={handleResetZoom}
            className={cn(
              "flex items-center justify-center rounded border-0 bg-canvas-panel tabular-nums text-muted-foreground transition-colors hover:bg-accent hover:text-primary focus:outline-none",
              compact
                ? "h-6 min-w-[2.4rem] px-0.5 text-[11px]"
                : "h-7 min-w-[3rem] px-1 text-xs"
            )}
            data-testid="canvas-zoom-percentage"
            aria-label={t(
              "flowCanvas.controls.zoomPercentageAria",
              "Zoom percentage"
            )}
          >
            {formattedZoom}
          </button>
        </SimpleTooltip>
      )}
      <ControlButton
        label={t("flowCanvas.controls.zoomIn", "Zoom In")}
        onClick={() => zoomIn()}
        testId="canvas-zoom-in"
        compact={compact}
      >
        <SvgPlus className={iconClass} />
      </ControlButton>
      <span
        className={cn("mx-0.5 w-px bg-border", compact ? "h-3" : "h-4")}
        aria-hidden
      />
      <ControlButton
        label={t("flowCanvas.controls.fitView", "Fit View")}
        onClick={handleFit}
        testId="canvas-fit-view"
        compact={compact}
      >
        <SvgExpand className={iconClass} />
      </ControlButton>
      {onAddNote && (
        <ControlButton
          label={t("flowCanvas.controls.addNote", "Add Sticky Note")}
          onClick={onAddNote}
          testId="canvas-add-note"
          compact={compact}
        >
          <SvgStickyNote className={iconClass} />
        </ControlButton>
      )}
      {onToggleFullscreen && (
        <ControlButton
          label={
            isFullscreen
              ? t("flowCanvas.controls.exitFullscreen", "Exit fullscreen (Esc)")
              : t("flowCanvas.controls.fullscreen", "Fullscreen")
          }
          onClick={onToggleFullscreen}
          active={isFullscreen}
          testId="canvas-toggle-fullscreen"
          compact={compact}
        >
          {isFullscreen ? (
            <SvgMinimize2 className={iconClass} />
          ) : (
            <SvgMaximize2 className={iconClass} />
          )}
        </ControlButton>
      )}
      {onToggleLock && (
        <ControlButton
          label={
            locked
              ? t("flowCanvas.controls.unlockCanvas", "Unlock canvas")
              : t("flowCanvas.controls.lockCanvas", "Lock canvas")
          }
          onClick={onToggleLock}
          active={locked}
          testId="canvas-toggle-lock"
          compact={compact}
        >
          <SvgLock className={iconClass} />
        </ControlButton>
      )}
    </Panel>
  );
}
