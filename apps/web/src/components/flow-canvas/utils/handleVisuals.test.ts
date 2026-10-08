/**
 * Extracted from `nodes/NodeHandle.tsx` so `PortDot` (the palette hover
 * preview, outside xyflow's node tree) draws its glow from the same source
 * as the real on-canvas handle instead of a second copy of the same magic
 * numbers. Values here must match NodeHandle's pre-extraction behavior
 * exactly — this is a regression guard for the extraction itself.
 */

import { neonShadow, handleDotStyle } from "./handleVisuals";

describe("neonShadow", () => {
  it("returns a plain 3px ring in the resting (non-glowing) state", () => {
    expect(neonShadow("#c026d3", false)).toBe("0 0 0 3px #c026d3");
  });

  it("returns the layered neon glow when active", () => {
    const shadow = neonShadow("#c026d3", true);
    expect(shadow).toContain("0 0 0 3px hsl(var(--lf-node-ring))");
    expect(shadow).toContain("0 0 2px #c026d3");
    expect(shadow).toContain("0 0 20px #c026d3");
  });
});

describe("handleDotStyle", () => {
  it("carries the handle color and resting shadow when not glowing", () => {
    const style = handleDotStyle("#c026d3", false);
    expect(style.background).toBe("#c026d3");
    expect(style.width).toBe("10px");
    expect(style.height).toBe("10px");
    expect(style.boxShadow).toBe(neonShadow("#c026d3", false));
    expect(style["--lf-handle-glow-color" as keyof typeof style]).toBe(
      "#c026d3"
    );
  });

  it("uses the active shadow when glowing", () => {
    const style = handleDotStyle("#c026d3", true);
    expect(style.boxShadow).toBe(neonShadow("#c026d3", true));
  });
});
