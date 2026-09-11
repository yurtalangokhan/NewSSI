/**
 * Tests for resolveComponentIcon.ts (25.8's data underpinning).
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import * as OpalIcons from "@opal/icons";
import { resolveComponentIcon } from "../utils/resolveComponentIcon";

describe("resolveComponentIcon", () => {
  it("resolves a known kebab-case icon name to its Svg component", () => {
    expect(resolveComponentIcon("sparkle")).toBe(OpalIcons.SvgSparkle);
    expect(resolveComponentIcon("workflow")).toBe(OpalIcons.SvgWorkflow);
  });

  it("resolves a multi-word kebab-case name", () => {
    expect(resolveComponentIcon("linked-dots")).toBe(OpalIcons.SvgLinkedDots);
  });

  it("25.8 — falls back to a generic icon for an unknown name, never throws", () => {
    expect(() => resolveComponentIcon("does-not-exist-anywhere")).not.toThrow();
    expect(resolveComponentIcon("does-not-exist-anywhere")).toBe(
      OpalIcons.SvgBlocks
    );
  });

  it("falls back for a null/undefined icon field", () => {
    expect(resolveComponentIcon(null)).toBe(OpalIcons.SvgBlocks);
    expect(resolveComponentIcon(undefined)).toBe(OpalIcons.SvgBlocks);
  });
});
