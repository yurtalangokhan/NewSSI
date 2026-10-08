import {
  MAX_FRAME_ASPECT,
  MIN_FRAME_ASPECT,
  VIRTUAL_H,
  VIRTUAL_W,
} from "./constants";
import { DEFAULT_COLUMN_CSS_PX } from "./column";
import { makeEnv } from "./env";
import { bilisim } from "./scenes/bilisim";
import { kablo } from "./scenes/kablo";
import { uydu } from "./scenes/uydu";
import type { Ctx2D, Env, Scene, TurksatCompany } from "./types";

const SCENES: Record<TurksatCompany, Scene> = { bilisim, uydu, kablo };

/** Seconds of animation fast-forwarded once at build time so buffers that
 * accumulate over time (Kablo's QAM trail, Bilişim's in-flight pulses) don't
 * start empty on every mount. Matches the source artifact's warm-up. */
const WARM_UP_SECONDS = 4;
const WARM_UP_STEP = 1 / 30;

/** Longest single tick the animation loop will advance by — guards against
 * a huge `dt` after the tab was backgrounded and just came back. */
const MAX_TICK_SECONDS = 0.05;

const MAX_DPR = 2;

/** Ceiling on device pixels for both the visible canvas and the offscreen
 * static layer (a 4K frame). Browsers cap canvas area — mobile Safari at
 * ~16.7M pixels — and past it the canvas silently renders nothing; a
 * decorative background also has no need to repaint more than this per frame. */
export const MAX_CANVAS_PIXELS = 3840 * 2160;

function get2DContext(canvas: HTMLCanvasElement): Ctx2D | null {
  return canvas.getContext("2d") as Ctx2D | null;
}

/**
 * Drives one TÜRKSAT background scene into a `<canvas>` element.
 *
 * Every scene is authored at a fixed 1440x900 virtual frame (see
 * `constants.ts`). `build()` fits that frame to the canvas's real pixel size
 * with a `cover` transform — scaled uniformly and cropped, anchored at the
 * scene's `focal` point instead of the geometric center — the same way a
 * `background-size: cover` image behaves, but keeping each scene's subject
 * in view across aspect ratios instead of an arbitrary center crop.
 *
 * Rendering is split into a static offscreen layer (painted once per
 * `build()`) and a per-tick animated layer, so a tick only re-draws what
 * actually moves.
 */
export class Painter {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: Ctx2D | null;
  private readonly staticLayer: HTMLCanvasElement;
  private scene: Scene | null = null;
  private env: Env | null = null;
  private state: unknown = null;
  private time = 0;
  /** Device-pixel scale applied to the virtual frame (cover factor × DPR). */
  private deviceScale = 1;
  private offsetX = 0;
  private offsetY = 0;
  /** Device-pixel shift that puts the authored scene's origin inside a
   * taller-than-scene frame. */
  private sceneOffsetY = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = get2DContext(canvas);
    this.staticLayer = document.createElement("canvas");
  }

  /** True once a 2D context was obtained; callers should skip `tick`/`draw`
   * otherwise (a small number of embedded/legacy viewers have no canvas 2D
   * support). */
  get isUsable(): boolean {
    return this.ctx !== null;
  }

  /**
   * (Re)builds the scene for a given company/mode at the given CSS pixel
   * size. Safe to call again on resize or company/mode change — it
   * re-initializes scene state (pulse trails and particles are re-seeded by
   * a warm-up) but, for the same scene and mode, keeps the animation clock.
   */
  build(
    company: TurksatCompany,
    dark: boolean,
    cssW: number,
    cssH: number,
    columnCssPx: number = DEFAULT_COLUMN_CSS_PX
  ): void {
    if (!this.ctx || cssW <= 0 || cssH <= 0) return;

    const scene = SCENES[company];
    const { frameW, frameH } = frameFor(cssW / cssH);
    // `cover`: scale uniformly so the frame fills the container on both axes,
    // then crop the overflow. The frame is grown to the window's aspect ratio
    // (see `frameFor`), so only a phone-narrow or ultra-wide window crops.
    const coverScale = Math.max(cssW / frameW, cssH / frameH);
    const dpr = fitDpr(
      Math.min(MAX_DPR, window.devicePixelRatio || 1),
      // The static layer holds the whole covered frame, which can be larger
      // than the visible canvas when the aspect ratios differ.
      Math.max(cssW * cssH, frameW * frameH * coverScale ** 2)
    );
    this.deviceScale = coverScale * dpr;
    const env = makeEnv({
      company,
      dark,
      width: frameW,
      height: frameH,
      anchorY: scene.anchorY ?? 0.5,
      // The real column covers `columnCssPx` CSS pixels, i.e. this many scene
      // units at the scale the scene is drawn.
      columnWidth: columnCssPx / coverScale,
    });
    this.sceneOffsetY = -env.top * this.deviceScale;

    const deviceW = Math.max(1, Math.round(cssW * dpr));
    const deviceH = Math.max(1, Math.round(cssH * dpr));
    this.canvas.width = deviceW;
    this.canvas.height = deviceH;

    const drawnW = frameW * this.deviceScale;
    const drawnH = frameH * this.deviceScale;
    const focal = scene.focal ?? { x: 0.5, y: 0.5 };
    // The focal point is a fraction of the authored 1440x900 scene; locate it
    // in the (possibly larger) frame before centering it in the container.
    const focalX = (focal.x * VIRTUAL_W) / frameW;
    const focalY = (focal.y * VIRTUAL_H - env.top) / frameH;
    // Center the focal point in the container, then clamp so the frame
    // still fully covers it (the frame is always >= the container on both
    // axes after a `cover` scale, so this range never exposes an edge).
    this.offsetX = clamp(deviceW / 2 - focalX * drawnW, deviceW - drawnW, 0);
    this.offsetY = clamp(deviceH / 2 - focalY * drawnH, deviceH - drawnH, 0);

    this.staticLayer.width = Math.ceil(drawnW);
    this.staticLayer.height = Math.ceil(drawnH);
    const staticCtx = get2DContext(this.staticLayer);
    if (!staticCtx) return;
    staticCtx.setTransform(
      this.deviceScale,
      0,
      0,
      this.deviceScale,
      0,
      this.sceneOffsetY
    );

    const st = scene.init(env);
    scene.static(staticCtx, env, st);

    // A rebuild of the same scene (a resize, the sidebar opening) keeps the
    // animation clock running so its motion continues instead of restarting;
    // only its buffers are re-seeded by the warm-up below.
    const resumeAt =
      this.scene === scene && this.env?.dark === dark ? this.time : null;
    this.scene = scene;
    this.env = env;
    this.state = st;
    this.time = resumeAt === null ? 0 : Math.max(0, resumeAt - WARM_UP_SECONDS);
    if (scene.update) {
      for (let s = 0; s < WARM_UP_SECONDS; s += WARM_UP_STEP) {
        this.time += WARM_UP_STEP;
        scene.update(st, env, this.time, WARM_UP_STEP);
      }
    }
    if (resumeAt !== null) this.time = resumeAt;
    scene.prefill?.(st, env);
  }

  /** Advances the animation by `dtSeconds` and repaints. Call from a rAF
   * loop; the caller owns pausing (reduced motion, hidden tab, off-screen). */
  tick(dtSeconds: number): void {
    if (!this.scene || !this.env) return;
    const dt = Math.min(MAX_TICK_SECONDS, Math.max(0, dtSeconds));
    this.time += dt;
    this.scene.update?.(this.state, this.env, this.time, dt);
    this.draw();
  }

  /** Repaints the current frame without advancing time — used to render one
   * static frame when animation is paused (reduced motion, hidden, initial
   * paint). */
  draw(): void {
    const c = this.ctx;
    if (!c || !this.scene || !this.env) return;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.canvas.width, this.canvas.height);
    c.drawImage(this.staticLayer, this.offsetX, this.offsetY);
    c.setTransform(
      this.deviceScale,
      0,
      0,
      this.deviceScale,
      this.offsetX,
      this.offsetY + this.sceneOffsetY
    );
    this.scene.frame(c, this.env, this.time, this.state);
  }
}

/** Lowers `dpr` just enough that `cssArea * dpr²` stays within the budget. */
function fitDpr(dpr: number, cssArea: number): number {
  const deviceArea = cssArea * dpr * dpr;
  return deviceArea > MAX_CANVAS_PIXELS
    ? dpr * Math.sqrt(MAX_CANVAS_PIXELS / deviceArea)
    : dpr;
}

/**
 * The virtual frame for a container of the given aspect ratio. The authored
 * 1440x900 scene is never cropped: a wider window widens the frame (up to
 * `MAX_FRAME_ASPECT`) and a narrower one makes it taller (down to
 * `MIN_FRAME_ASPECT`), with the scene centered and its backgrounds extended.
 */
function frameFor(aspect: number): { frameW: number; frameH: number } {
  const frameH = clamp(
    VIRTUAL_W / aspect,
    VIRTUAL_H,
    VIRTUAL_W / MIN_FRAME_ASPECT
  );
  const frameW = Math.max(
    VIRTUAL_W,
    Math.min(frameH * aspect, VIRTUAL_H * MAX_FRAME_ASPECT)
  );
  return { frameW, frameH };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
