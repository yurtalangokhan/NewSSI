/**
 * Ported from Langflow (MIT) —
 * vendor/langflow/CustomNodes/GenericNode/components/handleRenderComponent/index.tsx
 *
 * The visual design is Langflow's, carried over rather than reinterpreted:
 * a 32×32 transparent hit area (`BASE_HANDLE_STYLES`, upstream :23-31)
 * wrapping a 10×10 coloured dot with a 3px ring, and a neon glow on hover.
 * The class string on the inner dot is upstream's verbatim.
 *
 * Post-P4 follow-up: upstream's `isNullHandle` / `isMuted` / `openHandle`
 * states all derive from `useFlowStore`'s `handleDragging` + `filterEdge`
 * machinery, which drives Langflow's "glow every handle you *can* connect
 * to, dim the rest, while dragging" behaviour. The glow half is now ported
 * (`isPotentialTarget`, computed by `TemplateNode` from xyflow's own
 * `useConnection()` against the same `handlesCompatible` Task 22 already
 * uses for the real accept/reject decision — one source of truth, not a
 * second parallel one). Dimming incompatible handles was not asked for and
 * is left for later. Hover glow, sizing, colour and ring are all upstream's.
 *
 * Handle `id` stays the plain `Handle.name` string (P1's Handle model),
 * never Langflow's `scapedJSONStringfy` descriptor — Tasks 21/23 settled
 * that our edges carry plain handle names.
 */

"use client";

import { useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Handle as XyHandle, Position } from "@xyflow/react";
import { cn } from "@/lib/utils";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import type { Handle as HandleSpec } from "../types/componentTemplate";
import { portColor } from "../utils/portColors";

/** vendor/langflow/.../handleRenderComponent/index.tsx:23-31, verbatim. */
const BASE_HANDLE_STYLES = {
  width: "32px",
  height: "32px",
  position: "absolute" as const,
  zIndex: 30,
  background: "transparent",
  border: "none",
};

/** upstream :108-124 — `getNeonShadow`, minus the null/muted branches.
 *
 * Bugfix (Post-P4): the active branch's first layer was `0 0 0 1px
 * hsl(var(--border))` — a *thinner*, duller ring than the resting state's
 * `0 0 0 3px ${color}`. Since the dot itself never changes size, replacing
 * a bold 3px coloured ring with a faint 1px grey one reads to the eye as
 * the handle *shrinking*, not glowing — confirmed live (hover showed a
 * "shrink" with no visible glow). Upstream's real first layer is `0 0 0
 * 3px hsl(var(--node-ring))` (`--lf-node-ring` here) in every keyframe of
 * its pulse animation — the ring is kept, not thinned, precisely so the
 * transition never reads as shrinking. */
function neonShadow(color: string, isActive: boolean): string {
  if (!isActive) return `0 0 0 3px ${color}`;
  return [
    "0 0 0 3px hsl(var(--lf-node-ring))",
    `0 0 2px ${color}`,
    `0 0 4px ${color}`,
    `0 0 6px ${color}`,
    `0 0 8px ${color}`,
    `0 0 10px ${color}`,
    `0 0 15px ${color}`,
    `0 0 20px ${color}`,
  ].join(", ");
}

export type NodeHandleProps = {
  handle: HandleSpec;
  direction: "source" | "target";
  /** True while a connection is being dragged (or click-armed) from a
   * handle this one can legally accept — glows the same way hover does,
   * without waiting for the pointer to actually reach it. */
  isPotentialTarget?: boolean;
  /** A plain click (no drag) doesn't reliably surface through xyflow's own
   * `connectionClickStartHandle` for this glow (its `dragThreshold`-gated
   * pointer machinery only ever populates `state.connection` once the
   * pointer has actually moved) — this fires on every click regardless, so
   * `TemplateNode`'s own `activeClickHandle` store field is the source of
   * truth for "armed by a single click" instead. Purely additive: xyflow's
   * real click-to-connect (the actual edge-forming behaviour) is untouched
   * and keeps working off its own internal state. */
  onHandleClick?: () => void;
};

export function NodeHandle({
  handle,
  direction,
  isPotentialTarget,
  onHandleClick,
}: NodeHandleProps) {
  const { t } = useTranslation();
  const [isHovered, setIsHovered] = useState(false);
  const left = direction === "target";
  const color = portColor(handle.types);
  const glowing = isHovered || !!isPotentialTarget;
  const fallbackLabel = handle.name
    ? handle.name.charAt(0).toUpperCase() + handle.name.slice(1)
    : "";
  const label = t(`flowCanvas.handles.${handle.name}`, fallbackLabel);

  return (
    <SimpleTooltip
      tooltip={`${label} (${handle.types.join(", ")})`}
      side={left ? "left" : "right"}
    >
      <XyHandle
        type={direction}
        position={left ? Position.Left : Position.Right}
        id={handle.name}
        // Rendered inside its own row (see TemplateNode's HandleRow), so
        // xyflow measures the dot against that row and the handle lands on
        // the card's border level with its label — upstream's arrangement.
        style={{
          ...BASE_HANDLE_STYLES,
          top: "50%",
          [left ? "left" : "right"]: "-16px",
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={onHandleClick}
        data-testid={`handle-${direction}-${handle.name}`}
      >
        {/* upstream :156-161 — class string verbatim, plus `lf-handle-glow`
            (langflow-theme.css) for the pulse animation upstream drives via
            a dynamically-injected per-node <style> tag (`pulseNeon-${id}`)
            — done here with one shared `@keyframes` reading the colour off
            `--lf-handle-glow-color` instead, so it doesn't need a DOM-mutating
            effect per handle. */}
        <div
          className={cn(
            "noflow nowheel nopan noselect pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 cursor-crosshair rounded-full",
            glowing && "lf-handle-glow"
          )}
          style={
            {
              background: color,
              width: "10px",
              height: "10px",
              transition: "all 0.2s",
              boxShadow: neonShadow(color, glowing),
              "--lf-handle-glow-color": color,
            } as CSSProperties
          }
          data-testid={`div-handle-${direction}-${handle.name}`}
        />
      </XyHandle>
    </SimpleTooltip>
  );
}
