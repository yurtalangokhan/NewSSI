import { createFakeCanvasContext2D } from "@tests/setup/mocks/canvasContext2d";
import {
  MAX_FRAME_ASPECT,
  MIN_FRAME_ASPECT,
  VIRTUAL_H,
  VIRTUAL_W,
} from "./constants";
import { DEFAULT_COLUMN_CSS_PX } from "./column";
import { makeEnv } from "./env";
import type { Ctx2D, Env } from "./types";
import { MAX_CANVAS_PIXELS, Painter } from "./painter";
import { bilisim } from "./scenes/bilisim";
import { kablo } from "./scenes/kablo";
import { uydu } from "./scenes/uydu";
import type { TurksatCompany } from "./types";

const COMPANIES: TurksatCompany[] = ["bilisim", "uydu", "kablo"];
const SCENE_BY_NAME = { bilisim, uydu, kablo };

/** Routes every canvas element's `getContext("2d")` to its own fake context
 * (so the main canvas and Painter's internal offscreen static layer can be
 * spied on independently), or to `null` when `usable` is false. */
function stubCanvasContexts(usable = true) {
  const byCanvas = new WeakMap<HTMLCanvasElement, CanvasRenderingContext2D>();
  jest
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockImplementation(function (this: HTMLCanvasElement, id: string) {
      if (id !== "2d" || !usable) return null;
      if (!byCanvas.has(this)) byCanvas.set(this, createFakeCanvasContext2D());
      return byCanvas.get(this) as CanvasRenderingContext2D;
    } as typeof HTMLCanvasElement.prototype.getContext);
  return byCanvas;
}

function setDpr(dpr: number) {
  Object.defineProperty(window, "devicePixelRatio", {
    value: dpr,
    configurable: true,
    writable: true,
  });
}

describe("Painter", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe.each(COMPANIES)("scene: %s", (company) => {
    it.each([true, false])(
      "builds, ticks, and draws without throwing (dark=%s)",
      (dark) => {
        stubCanvasContexts();
        setDpr(1);
        const canvas = document.createElement("canvas");
        const painter = new Painter(canvas);

        expect(() => {
          painter.build(company, dark, 800, 600);
          painter.tick(1 / 60);
          painter.tick(1 / 60);
          painter.draw();
        }).not.toThrow();

        expect(painter.isUsable).toBe(true);
      }
    );
  });

  it("sizes the canvas to the CSS size times the device pixel ratio", () => {
    stubCanvasContexts();
    setDpr(2);
    const canvas = document.createElement("canvas");
    const painter = new Painter(canvas);

    painter.build("bilisim", false, 800, 600);

    expect(canvas.width).toBe(1600);
    expect(canvas.height).toBe(1200);
  });

  it("caps the device pixel ratio at 2 even when the display reports more", () => {
    stubCanvasContexts();
    setDpr(3);
    const canvas = document.createElement("canvas");
    const painter = new Painter(canvas);

    painter.build("bilisim", false, 800, 600);

    expect(canvas.width).toBe(1600); // 800 * 2 (capped), not 800 * 3
  });

  it("keeps the canvas and its static layer within a pixel budget on very large high-DPR screens", () => {
    // 3840x2160 at 2x would be ~33M device pixels — beyond what mobile Safari
    // (16.7M) will allocate, at which point the canvas silently renders blank.
    stubCanvasContexts();
    setDpr(2);
    const createElement = document.createElement.bind(document);
    const created: HTMLCanvasElement[] = [];
    jest.spyOn(document, "createElement").mockImplementation(((tag: string) => {
      const el = createElement(tag);
      if (tag === "canvas") created.push(el as HTMLCanvasElement);
      return el;
    }) as typeof document.createElement);
    const canvas = document.createElement("canvas");
    const painter = new Painter(canvas);
    const staticLayer = created[1]!; // [0] is the visible canvas above

    painter.build("bilisim", false, 3840, 2160);

    expect(canvas.width * canvas.height).toBeLessThanOrEqual(MAX_CANVAS_PIXELS);
    expect(staticLayer.width * staticLayer.height).toBeLessThanOrEqual(
      MAX_CANVAS_PIXELS
    );
  });

  it("keeps the canvas at the requested aspect ratio when it lowers resolution", () => {
    stubCanvasContexts();
    setDpr(2);
    const canvas = document.createElement("canvas");

    new Painter(canvas).build("bilisim", false, 3840, 2160);

    expect(canvas.width / canvas.height).toBeCloseTo(3840 / 2160, 2);
  });

  it("never exposes an edge: the blitted static layer always covers the canvas", () => {
    const byCanvas = stubCanvasContexts();
    setDpr(1);
    const canvas = document.createElement("canvas");
    const painter = new Painter(canvas);

    // A narrow, tall viewport (mobile portrait) — aspect ratio far from the
    // scene's native 1440x900, so the cover crop is heavily horizontal.
    painter.build("uydu", true, 390, 844);
    painter.draw();

    const mainCtx = byCanvas.get(canvas)!;
    const drawImage = mainCtx.drawImage as jest.Mock;
    expect(drawImage).toHaveBeenCalled();
    const [staticLayer, offsetX, offsetY] = drawImage.mock.calls.at(-1)!;
    const layer = staticLayer as HTMLCanvasElement;

    // The offset must place the static layer so it fully covers the canvas on
    // both axes — i.e. offset <= 0 and offset + layer size >= canvas size.
    expect(offsetX).toBeLessThanOrEqual(0);
    expect(offsetX + layer.width).toBeGreaterThanOrEqual(canvas.width);
    expect(offsetY).toBeLessThanOrEqual(0);
    expect(offsetY + layer.height).toBeGreaterThanOrEqual(canvas.height);
  });

  describe("frame fitting", () => {
    function initEnvFor(cssW: number, cssH: number): Env {
      stubCanvasContexts();
      setDpr(1);
      const init = jest.spyOn(bilisim, "init");
      new Painter(document.createElement("canvas")).build(
        "bilisim",
        false,
        cssW,
        cssH
      );
      return init.mock.calls.at(-1)![0];
    }

    it("widens the virtual frame for a window wider than the authored 16:10 instead of cropping top and bottom", () => {
      // A normal (non-fullscreen) desktop window: browser chrome makes it ~2:1.
      const env = initEnvFor(1920, 950);

      expect(env.w).toBeCloseTo((VIRTUAL_H * 1920) / 950, 1);
      expect(env.w).toBeGreaterThan(VIRTUAL_W);
    });

    it("shows the whole scene height when the window is wider than 16:10", () => {
      const byCanvas = stubCanvasContexts();
      setDpr(1);
      const canvas = document.createElement("canvas");
      const painter = new Painter(canvas);

      painter.build("kablo", false, 1920, 950);
      painter.draw();

      const drawImage = (
        byCanvas.get(canvas)!.drawImage as jest.Mock
      ).mock.calls.at(-1)!;
      const [staticLayer, , offsetY] = drawImage;
      expect(offsetY).toBe(0);
      expect((staticLayer as HTMLCanvasElement).height).toBe(canvas.height);
    });

    it("shows the whole authored width of a window narrower than 16:10 by extending the frame downward and upward, not cropping the sides", () => {
      // Half of a 16:9 monitor snapped side by side.
      const env = initEnvFor(960, 1080);

      expect(env.w).toBe(VIRTUAL_W);
      expect(env.h).toBeCloseTo(VIRTUAL_W / (960 / 1080), 1);
      // The authored 900-high scene sits centered in the taller frame.
      expect(env.top).toBeCloseTo(-(env.h - VIRTUAL_H) / 2, 1);
      expect(env.bottom).toBeCloseTo(env.top + env.h, 1);
    });

    it("does not offset the static layer sideways when the whole width fits", () => {
      const byCanvas = stubCanvasContexts();
      setDpr(1);
      const canvas = document.createElement("canvas");
      const painter = new Painter(canvas);

      painter.build("kablo", false, 960, 1080);
      painter.draw();

      const [, offsetX, offsetY] = (
        byCanvas.get(canvas)!.drawImage as jest.Mock
      ).mock.calls.at(-1)!;
      expect(offsetX).toBe(0);
      expect(offsetY).toBe(0);
    });

    it("rests the ground-based scenes on the frame's bottom edge in a taller frame, so their ground and captions stay at the screen bottom", () => {
      for (const scene of ["uydu", "kablo"] as const) {
        stubCanvasContexts();
        setDpr(1);
        const init = jest.spyOn(SCENE_BY_NAME[scene], "init");
        new Painter(document.createElement("canvas")).build(
          scene,
          false,
          960,
          1080
        );
        const env = init.mock.calls.at(-1)![0];

        expect(env.bottom).toBe(VIRTUAL_H);
        expect(env.top).toBeLessThan(0);
      }
    });

    it("centers the map scene in a taller frame", () => {
      const env = initEnvFor(960, 1080);

      expect(env.top).toBeCloseTo(-(env.h - VIRTUAL_H) / 2, 1);
    });

    it("pins the Kablo schedule strip to the frame's top edge, in both the still and the animated layer, instead of letting it float mid-screen", () => {
      const env = makeEnv({
        company: "kablo",
        dark: false,
        width: VIRTUAL_W,
        height: 1620,
        anchorY: kablo.anchorY ?? 0.5,
        columnWidth: 840,
      });
      const state = kablo.init(env);

      for (const draw of [
        (c: Ctx2D) => kablo.static(c, env, state),
        (c: Ctx2D) => kablo.frame(c, env, 0, state),
      ]) {
        const ctx = createFakeCanvasContext2D() as Ctx2D;
        draw(ctx);
        expect(
          (ctx.translate as jest.Mock).mock.calls.some(
            ([x, y]) => x === 0 && y === env.top
          )
        ).toBe(true);
      }
    });

    it("keeps the authored frame for a 4:3 window", () => {
      const env = initEnvFor(1024, 768);

      expect(env.w).toBe(VIRTUAL_W);
      expect(env.h).toBeCloseTo(VIRTUAL_W / (1024 / 768), 1);
    });

    it("stops extending at a portrait ratio and crops the sides there instead, so a phone keeps a legible scale", () => {
      const env = initEnvFor(390, 844);

      expect(env.w).toBe(VIRTUAL_W);
      expect(env.h).toBe(VIRTUAL_W / MIN_FRAME_ASPECT);
    });

    it("stops widening at an ultra-wide ratio rather than stretching the scene without bound", () => {
      const env = initEnvFor(5000, 500);

      expect(env.w).toBeLessThanOrEqual(VIRTUAL_H * MAX_FRAME_ASPECT + 0.001);
      expect(env.h).toBe(VIRTUAL_H);
    });
  });

  describe("message column", () => {
    function envFor(cssW: number, cssH: number, columnCssPx?: number): Env {
      stubCanvasContexts();
      setDpr(1);
      const init = jest.spyOn(bilisim, "init");
      new Painter(document.createElement("canvas")).build(
        "bilisim",
        false,
        cssW,
        cssH,
        columnCssPx
      );
      return init.mock.calls.at(-1)![0];
    }

    it("covers the same on-screen width as the real column at any scale", () => {
      // 1920x1080 draws the 900-high scene at 1.2x, so an 840px column spans
      // 700 scene units.
      const env = envFor(1920, 1080, 840);

      expect(env.colW * 1.2).toBeCloseTo(840, 1);
    });

    it("takes more scene units where the scene is drawn smaller", () => {
      const large = envFor(1920, 1080, 840).colW;
      const small = envFor(1440, 900, 840).colW;

      expect(small).toBeGreaterThan(large);
    });

    it("defaults to the design column width when none is measured", () => {
      const env = envFor(1440, 900);

      expect(env.colW).toBe(DEFAULT_COLUMN_CSS_PX);
    });
  });

  describe("rebuilding on resize", () => {
    function lastFrameTime(spy: jest.SpyInstance): number {
      return spy.mock.calls.at(-1)![2];
    }

    function tickedPainter() {
      stubCanvasContexts();
      setDpr(1);
      const painter = new Painter(document.createElement("canvas"));
      painter.build("bilisim", false, 1440, 900);
      for (let i = 0; i < 60; i++) painter.tick(1 / 60);
      return painter;
    }

    it("keeps the animation clock running instead of restarting the scene, so opening the sidebar does not reset the motion", () => {
      const painter = tickedPainter();
      const frame = jest.spyOn(bilisim, "frame");
      painter.draw();
      const before = lastFrameTime(frame);

      painter.build("bilisim", false, 1100, 900);
      painter.draw();

      expect(lastFrameTime(frame)).toBeCloseTo(before, 1);
      expect(before).toBeGreaterThan(4.5);
    });

    it("starts a different scene's clock fresh", () => {
      const painter = tickedPainter();
      const frame = jest.spyOn(uydu, "frame");

      painter.build("uydu", false, 1440, 900);
      painter.draw();

      expect(lastFrameTime(frame)).toBeLessThan(4.5);
    });

    it("starts the clock fresh when only the color mode changes", () => {
      const painter = tickedPainter();
      const frame = jest.spyOn(bilisim, "frame");

      painter.build("bilisim", true, 1440, 900);
      painter.draw();

      expect(lastFrameTime(frame)).toBeLessThan(4.5);
    });
  });

  it("does not throw when no 2D context is available and reports itself unusable", () => {
    stubCanvasContexts(false);
    const canvas = document.createElement("canvas");
    const painter = new Painter(canvas);

    expect(painter.isUsable).toBe(false);
    expect(() => {
      painter.build("kablo", false, 800, 600);
      painter.tick(1 / 60);
      painter.draw();
    }).not.toThrow();
  });

  it("ignores a zero-size build instead of producing an empty/NaN canvas", () => {
    stubCanvasContexts();
    setDpr(1);
    const canvas = document.createElement("canvas");
    const painter = new Painter(canvas);

    expect(() => painter.build("bilisim", false, 0, 0)).not.toThrow();
  });

  describe("tick", () => {
    it("hands the scene the same clamped step it advances time by, so a tab returning from the background cannot teleport particles", () => {
      stubCanvasContexts();
      setDpr(1);
      const painter = new Painter(document.createElement("canvas"));
      painter.build("bilisim", false, 800, 600);
      const update = jest.spyOn(bilisim, "update");

      painter.tick(5);

      const [, , , dt] = update.mock.calls.at(-1)!;
      expect(dt).toBeLessThanOrEqual(0.05);
    });

    it("never hands the scene a negative step", () => {
      stubCanvasContexts();
      setDpr(1);
      const painter = new Painter(document.createElement("canvas"));
      painter.build("bilisim", false, 800, 600);
      const update = jest.spyOn(bilisim, "update");

      painter.tick(-1);

      const [, , , dt] = update.mock.calls.at(-1)!;
      expect(dt).toBe(0);
    });
  });
});
