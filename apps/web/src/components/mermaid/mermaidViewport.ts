/**
 * Zoom/pan state for the fullscreen viewer. The content is flex-centred in
 * the canvas with `transform-origin: center`, so origins are measured from
 * the canvas centre. Zooming about a point keeps that point fixed:
 * t' = o - (o - t) * (s' / s).
 */
export interface Viewport {
  scale: number;
  x: number;
  y: number;
}

export const MIN_SCALE = 0.25;
export const MAX_SCALE = 4;
export const ZOOM_STEP = 1.25;
export const PAN_STEP = 40;
const WHEEL_SENSITIVITY = 0.002;

/** Firefox and some mice report wheel deltas in lines or pages, not pixels. */
export const WHEEL_LINE_PX = 16;
const WHEEL_PAGE_FALLBACK_PX = 400;

export function normalizeWheelDelta(
  delta: number,
  deltaMode: number,
  pageSize: number
): number {
  if (deltaMode === 1) return delta * WHEEL_LINE_PX;
  if (deltaMode === 2) return delta * (pageSize || WHEEL_PAGE_FALLBACK_PX);
  return delta;
}

export const INITIAL_VIEWPORT: Viewport = { scale: 1, x: 0, y: 0 };

export type ViewportAction =
  | { type: "zoomIn" }
  | { type: "zoomOut" }
  | { type: "reset" }
  /** Ctrl/meta+wheel or trackpad pinch: zoom around the cursor. */
  | { type: "wheel"; deltaY: number; originX: number; originY: number }
  | { type: "pan"; dx: number; dy: number };

function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

function zoomAround(
  viewport: Viewport,
  nextScale: number,
  originX: number,
  originY: number
): Viewport {
  const scale = clampScale(nextScale);
  const ratio = scale / viewport.scale;
  return {
    scale,
    x: originX - (originX - viewport.x) * ratio,
    y: originY - (originY - viewport.y) * ratio,
  };
}

export function viewportReducer(
  viewport: Viewport,
  action: ViewportAction
): Viewport {
  switch (action.type) {
    case "zoomIn":
      return zoomAround(viewport, viewport.scale * ZOOM_STEP, 0, 0);
    case "zoomOut":
      return zoomAround(viewport, viewport.scale / ZOOM_STEP, 0, 0);
    case "reset":
      return INITIAL_VIEWPORT;
    case "wheel":
      return zoomAround(
        viewport,
        viewport.scale * Math.exp(-action.deltaY * WHEEL_SENSITIVITY),
        action.originX,
        action.originY
      );
    case "pan":
      return {
        ...viewport,
        x: viewport.x + action.dx,
        y: viewport.y + action.dy,
      };
    default:
      return viewport;
  }
}

/** Arrow keys move the view, so the content moves the opposite way. */
export function keyToViewportAction(key: string): ViewportAction | null {
  switch (key) {
    case "+":
    case "=":
      return { type: "zoomIn" };
    case "-":
    case "_":
      return { type: "zoomOut" };
    case "0":
      return { type: "reset" };
    case "ArrowLeft":
      return { type: "pan", dx: PAN_STEP, dy: 0 };
    case "ArrowRight":
      return { type: "pan", dx: -PAN_STEP, dy: 0 };
    case "ArrowUp":
      return { type: "pan", dx: 0, dy: PAN_STEP };
    case "ArrowDown":
      return { type: "pan", dx: 0, dy: -PAN_STEP };
    default:
      return null;
  }
}
