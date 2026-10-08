import {
  INITIAL_VIEWPORT,
  MAX_SCALE,
  MIN_SCALE,
  PAN_STEP,
  WHEEL_LINE_PX,
  keyToViewportAction,
  normalizeWheelDelta,
  viewportReducer,
} from "@/components/mermaid/mermaidViewport";

describe("normalizeWheelDelta", () => {
  it("keeps pixel deltas and converts lines and pages", () => {
    expect(normalizeWheelDelta(120, 0, 800)).toBe(120);
    expect(normalizeWheelDelta(3, 1, 800)).toBe(3 * WHEEL_LINE_PX);
    expect(normalizeWheelDelta(1, 2, 800)).toBe(800);
    // jsdom reports no layout, so a page delta needs its own fallback.
    expect(normalizeWheelDelta(1, 2, 0)).toBeGreaterThan(WHEEL_LINE_PX);
  });
});

describe("viewportReducer", () => {
  it("zooms in steps and clamps to the scale limits", () => {
    let viewport = INITIAL_VIEWPORT;
    viewport = viewportReducer(viewport, { type: "zoomIn" });
    expect(viewport.scale).toBeCloseTo(1.25);

    for (let i = 0; i < 20; i += 1)
      viewport = viewportReducer(viewport, { type: "zoomIn" });
    expect(viewport.scale).toBe(MAX_SCALE);

    for (let i = 0; i < 40; i += 1)
      viewport = viewportReducer(viewport, { type: "zoomOut" });
    expect(viewport.scale).toBe(MIN_SCALE);
  });

  it("keeps the point under the cursor fixed while wheel-zooming", () => {
    const deltaY = -Math.log(2) / 0.002; // doubles the scale
    const next = viewportReducer(INITIAL_VIEWPORT, {
      type: "wheel",
      deltaY,
      originX: 100,
      originY: 50,
    });

    expect(next.scale).toBeCloseTo(2);
    // content point (100, 50) must still sit at screen (100, 50)
    expect(next.x + next.scale * 100).toBeCloseTo(100);
    expect(next.y + next.scale * 50).toBeCloseTo(50);
  });

  it("pans and resets", () => {
    const panned = viewportReducer(INITIAL_VIEWPORT, {
      type: "pan",
      dx: 20,
      dy: -5,
    });
    expect(panned).toEqual({ scale: 1, x: 20, y: -5 });
    expect(viewportReducer(panned, { type: "reset" })).toEqual(
      INITIAL_VIEWPORT
    );
  });
});

describe("keyToViewportAction", () => {
  it("maps zoom, reset and arrow keys", () => {
    expect(keyToViewportAction("+")).toEqual({ type: "zoomIn" });
    expect(keyToViewportAction("=")).toEqual({ type: "zoomIn" });
    expect(keyToViewportAction("-")).toEqual({ type: "zoomOut" });
    expect(keyToViewportAction("0")).toEqual({ type: "reset" });
    expect(keyToViewportAction("ArrowLeft")).toEqual({
      type: "pan",
      dx: PAN_STEP,
      dy: 0,
    });
    expect(keyToViewportAction("ArrowDown")).toEqual({
      type: "pan",
      dx: 0,
      dy: -PAN_STEP,
    });
    expect(keyToViewportAction("a")).toBeNull();
  });
});
