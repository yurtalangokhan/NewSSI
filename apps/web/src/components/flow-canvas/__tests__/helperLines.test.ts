/**
 * Tests for helperLines.ts — ported verbatim from Langflow (pure geometry,
 * no Langflow-specific coupling). Confirms the port preserved behavior
 * exactly (24.7).
 *
 * Brief: .tmp/flow-canvas-task-24-brief.md
 */

import { getHelperLines, getSnapPosition } from "../helpers/helperLines";
import type { CanvasNode } from "../types/flow";

function node(
  id: string,
  x: number,
  y: number,
  measured?: { width: number; height: number }
): CanvasNode {
  return {
    id,
    position: { x, y },
    ...(measured ? { measured } : {}),
    data: { type: "ChatInput", templateVersion: 1, values: {} },
  };
}

describe("getHelperLines (24.7)", () => {
  it("returns no lines when nothing is close enough to align with", () => {
    const dragging = node("a", 500, 500);
    const other = node("b", 0, 0);

    const lines = getHelperLines(dragging, [dragging, other]);

    expect(lines.horizontal).toBeUndefined();
    expect(lines.vertical).toBeUndefined();
  });

  it("detects horizontal alignment when tops are within snap distance", () => {
    // Distinct heights so "top" and "center" alignment don't coincide —
    // with equal default heights they always would (centerY - centerY ==
    // top - top), masking which criterion actually matched.
    const dragging = node("a", 300, 102);
    const other = node("b", 0, 100, { width: 150, height: 300 });

    const lines = getHelperLines(dragging, [dragging, other]);

    expect(lines.horizontal).toBeDefined();
    expect(lines.horizontal!.orientation).toBe("horizontal");
    expect(lines.horizontal!.id).toContain("top");
    expect(lines.horizontal!.position).toBe(100);
  });

  it("detects vertical alignment when lefts are within snap distance", () => {
    const dragging = node("a", 102, 300);
    const other = node("b", 100, 0, { width: 400, height: 50 });

    const lines = getHelperLines(dragging, [dragging, other]);

    expect(lines.vertical).toBeDefined();
    expect(lines.vertical!.orientation).toBe("vertical");
    expect(lines.vertical!.id).toContain("left");
    expect(lines.vertical!.position).toBe(100);
  });

  it("ignores the dragging node itself when comparing", () => {
    const dragging = node("a", 100, 100);

    const lines = getHelperLines(dragging, [dragging]);

    expect(lines.horizontal).toBeUndefined();
    expect(lines.vertical).toBeUndefined();
  });
});

describe("getSnapPosition", () => {
  it("snaps to the aligned top when within range", () => {
    const dragging = node("a", 300, 103);
    const other = node("b", 0, 100, { width: 150, height: 300 });

    const snapped = getSnapPosition(dragging, [dragging, other]);

    expect(snapped.y).toBe(100);
  });

  it("does not modify position when nothing aligns", () => {
    const dragging = node("a", 500, 500);
    const other = node("b", 0, 0);

    const snapped = getSnapPosition(dragging, [dragging, other]);

    expect(snapped).toEqual({ x: 500, y: 500 });
  });
});
