/**
 * Extracted from `nodes/NodeHandle.tsx` (see that file's header for the full
 * upstream/Post-P4 history of the glow shadow) so `PortDot` — the palette
 * hover preview, which renders outside xyflow's node tree and cannot reuse
 * `<XyHandle>` — draws the same dot/glow visuals from one source instead of
 * a second copy of the same magic numbers.
 */

import type { CSSProperties } from "react";

/** upstream :108-124 — `getNeonShadow`, minus the null/muted branches. See
 * NodeHandle.tsx's Post-P4 bugfix note: the active branch's ring must stay
 * the same 3px width as the resting ring, or the transition reads as the
 * handle shrinking rather than glowing. */
export function neonShadow(color: string, isActive: boolean): string {
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

/** The 10×10 coloured dot's own style — background, size, transition and
 * glow shadow. Positioning (how the dot sits relative to its container) is
 * deliberately NOT part of this: `NodeHandle` centers it inside a 32×32
 * xyflow hit area, `PortDot` sits inline next to palette text — two
 * different layouts sharing one set of glow visuals. */
export function handleDotStyle(
  color: string,
  glowing: boolean
): CSSProperties & Record<"--lf-handle-glow-color", string> {
  return {
    background: color,
    width: "10px",
    height: "10px",
    transition: "all 0.2s",
    boxShadow: neonShadow(color, glowing),
    "--lf-handle-glow-color": color,
  } as CSSProperties & Record<"--lf-handle-glow-color", string>;
}
