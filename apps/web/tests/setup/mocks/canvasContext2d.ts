/**
 * A minimal fake `CanvasRenderingContext2D` for jsdom, which implements no
 * canvas 2D backend at all (`getContext("2d")` returns `null` there without
 * this). This is a browser-API stub, not a mock of our own code — the same
 * category as this project's existing `matchMedia`/`ResizeObserver`/
 * `IntersectionObserver` polyfills in `tests/setup/jest.setup.ts`.
 *
 * It records nothing and validates nothing by default; it exists purely so
 * real scene-drawing code (which calls dozens of canvas methods) can run
 * against something that returns sane values and never throws. Tests that
 * need to assert *what* was drawn should spy on specific methods after
 * creating the context.
 */
export function createFakeCanvasContext2D(): CanvasRenderingContext2D {
  const gradient: Partial<CanvasGradient> = {
    addColorStop: jest.fn(),
  };

  const ctx: Partial<CanvasRenderingContext2D> & Record<string, unknown> = {
    canvas: document.createElement("canvas"),

    // State
    save: jest.fn(),
    restore: jest.fn(),
    setTransform: jest.fn(),
    translate: jest.fn(),
    rotate: jest.fn(),
    scale: jest.fn(),
    clip: jest.fn(),

    // Path construction
    beginPath: jest.fn(),
    closePath: jest.fn(),
    moveTo: jest.fn(),
    lineTo: jest.fn(),
    quadraticCurveTo: jest.fn(),
    bezierCurveTo: jest.fn(),
    arc: jest.fn(),
    arcTo: jest.fn(),
    rect: jest.fn(),
    fill: jest.fn(),
    stroke: jest.fn(),

    // Rects
    fillRect: jest.fn(),
    strokeRect: jest.fn(),
    clearRect: jest.fn(),

    // Text
    fillText: jest.fn(),
    strokeText: jest.fn(),
    measureText: jest.fn(() => ({ width: 0 }) as TextMetrics),

    // Images
    drawImage: jest.fn(),

    // Gradients
    createLinearGradient: jest.fn(() => gradient as CanvasGradient),
    createRadialGradient: jest.fn(() => gradient as CanvasGradient),

    // Dash
    setLineDash: jest.fn(),
    getLineDash: jest.fn(() => []),

    // Writable style properties the engine assigns directly (not methods).
    fillStyle: "#000000",
    strokeStyle: "#000000",
    lineWidth: 1,
    lineCap: "butt",
    lineJoin: "miter",
    lineDashOffset: 0,
    font: "10px sans-serif",
    textAlign: "start",
    textBaseline: "alphabetic",
    globalAlpha: 1,
    globalCompositeOperation: "source-over",
    // Non-standard but used by `utils.text()` when the runtime supports it;
    // present here so `"letterSpacing" in ctx` is true and the assignment
    // path is exercised too.
    letterSpacing: "0px",
  };

  return ctx as CanvasRenderingContext2D;
}
