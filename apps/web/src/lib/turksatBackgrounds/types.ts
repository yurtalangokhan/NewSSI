/**
 * Shared types for the TÜRKSAT animated chat background engine.
 *
 * The engine is framework-free by design (ported from the approved design
 * artifact) so it can be driven by a single React wrapper
 * (`TurksatBackgroundCanvas`) without any canvas logic living in JSX.
 */

export type TurksatCompany = "bilisim" | "uydu" | "kablo";
export type TurksatMode = "light" | "dark";

/** Canvas 2D context, widened with the (still non-standard) letter-spacing API. */
export type Ctx2D = CanvasRenderingContext2D & { letterSpacing?: string };

export interface Point {
  x: number;
  y: number;
}

/** A polyline plus its cumulative per-segment lengths, for `along()`. */
export interface Path {
  pts: Point[];
  seg: number[];
  L: number;
}

/**
 * Layout environment a scene is drawn into. The virtual frame is always
 * 1440x900 (see `constants.ts`) — `Painter` handles fitting that frame to
 * the real container, so scenes never see the real pixel size.
 */
export interface Env {
  company: TurksatCompany;
  dark: boolean;
  /** Virtual frame width: `VIRTUAL_W` or wider, matching the window's aspect
   * (the height is always `VIRTUAL_H`). */
  w: number;
  /** Horizontal center of the frame. */
  /** Virtual frame height: `VIRTUAL_H` or taller (the authored scene is
   * centered in it — see `top`/`bottom`). */
  h: number;
  /** Frame edges in scene coordinates: `top` is <= 0 and `bottom` >=
   * `VIRTUAL_H` when the frame is taller than the scene. Backgrounds fill
   * `top`..`bottom` and footers anchor to `bottom`. */
  top: number;
  bottom: number;
  cx: number;
  /** Width of the (implied) centered message column used for composition. */
  colW: number;
  colL: number;
  colR: number;
}

/**
 * A scene owns its own per-instance state `S`, built once in `init` and
 * mutated by `update`/`frame` every tick. `static` paints everything that
 * never changes frame-to-frame into an offscreen cache; `frame` paints only
 * the animated layer on top of it every tick.
 */
export interface Scene<S = unknown> {
  /** Where the scene sits vertically when the frame is taller than the
   * authored 900 (a narrow window): 0 = on the top edge, 1 = on the bottom
   * edge. Defaults to centered (0.5). Anchor to the edge the scene's ground
   * or heaviest content rests on. */
  anchorY?: number;
  /** Where the crop should anchor when the container's aspect ratio doesn't
   * match the virtual frame's (fractions of the 1440x900 frame). Defaults to
   * the geometric center `{x: 0.5, y: 0.5}` when omitted. See `Painter`. */
  focal?: Point;
  init(env: Env): S;
  static(ctx: Ctx2D, env: Env, st: S): void;
  frame(ctx: Ctx2D, env: Env, t: number, st: S): void;
  /** Advances animation-only state (e.g. particle emitters). Called once per
   * tick before `frame`, and repeatedly during `Painter.build()` to warm up
   * state that accumulates over time (e.g. a trail buffer). */
  update?(st: S, env: Env, t: number, dt: number): void;
  /** One-time warm-up of an accumulating buffer, run once after `update` has
   * been fast-forwarded during `build()`. */
  prefill?(st: S, env: Env): void;
}
