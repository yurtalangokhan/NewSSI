/**
 * A small colored port indicator, styled identically to the real on-canvas
 * `NodeHandle` dot (via `utils/handleVisuals.ts`) but with no `<XyHandle>` —
 * usable anywhere, in particular the component palette, which renders
 * outside xyflow's node tree entirely.
 */

"use client";

import { cn } from "@/lib/utils";
import { portColor } from "../utils/portColors";
import { handleDotStyle } from "../utils/handleVisuals";

export type PortDotProps = {
  types: readonly string[];
  /** Mirrors `NodeHandle`'s hover/potential-target glow — set while this
   * port's component is being previewed and has a compatible counterpart. */
  glowing?: boolean;
  testId?: string;
};

export function PortDot({ types, glowing = false, testId }: PortDotProps) {
  const color = portColor(types);
  const { boxShadow, ...dotStyle } = handleDotStyle(color, glowing);
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block shrink-0 animate-in rounded-full fade-in zoom-in-50 duration-150",
        glowing && "lf-handle-glow"
      )}
      style={{
        ...dotStyle,
        // A ring in the row's own hover background separates the dot from
        // the icon/label it sits next to — matches NodeHandle's `--lf-*`
        // token convention rather than a hardcoded color, so it still reads
        // correctly in dark mode.
        boxShadow: `0 0 0 2px hsl(var(--lf-muted, 240 5% 96%)), ${boxShadow}`,
      }}
      data-testid={testId}
    />
  );
}
