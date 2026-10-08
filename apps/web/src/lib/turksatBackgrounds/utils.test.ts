/**
 * @jest-environment jsdom
 */
import { createFakeCanvasContext2D } from "@tests/setup/mocks/canvasContext2d";
import type { Ctx2D } from "./types";
import {
  along,
  circle,
  fillSpacedText,
  gauss,
  hexA,
  measure,
  rrect,
  rng,
  sampleXs,
} from "./utils";

/** A context whose runtime has no canvas `letterSpacing` (Safari before 18.4,
 * older Firefox) and gives every glyph a 5px advance. */
function ctxWithoutLetterSpacing(): Ctx2D {
  const ctx = createFakeCanvasContext2D() as Ctx2D;
  Reflect.deleteProperty(ctx, "letterSpacing");
  (ctx.measureText as jest.Mock).mockImplementation((s: string) => ({
    width: s.length * 5,
  }));
  return ctx;
}

describe("rng", () => {
  it("is deterministic for a given seed", () => {
    const a = rng(11);
    const b = rng(11);
    const seqA = [a(), a(), a()];
    const seqB = [b(), b(), b()];
    expect(seqA).toEqual(seqB);
  });

  it("produces values in [0, 1)", () => {
    const r = rng(42);
    for (let i = 0; i < 50; i++) {
      const v = r();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("differs across seeds", () => {
    const a = rng(1)();
    const b = rng(2)();
    expect(a).not.toBe(b);
  });
});

describe("gauss", () => {
  it("is finite and centers near zero over many samples", () => {
    const r = rng(7);
    let sum = 0;
    const n = 2000;
    for (let i = 0; i < n; i++) {
      const v = gauss(r);
      expect(Number.isFinite(v)).toBe(true);
      sum += v;
    }
    expect(Math.abs(sum / n)).toBeLessThan(0.15);
  });
});

describe("hexA", () => {
  it("converts a hex color and alpha to rgba", () => {
    expect(hexA("#D3121D", 0.5)).toBe("rgba(211,18,29,0.5)");
  });

  it("clamps alpha into [0, 1]", () => {
    expect(hexA("#000000", 2)).toBe("rgba(0,0,0,1)");
    expect(hexA("#FFFFFF", -1)).toBe("rgba(255,255,255,0)");
  });
});

describe("measure/along", () => {
  const path = measure([
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 },
  ]);

  it("sums segment lengths into the total length", () => {
    expect(path.seg).toEqual([10, 10]);
    expect(path.L).toBe(20);
  });

  it("returns the start point at s=0", () => {
    expect(along(path, 0)).toEqual({ x: 0, y: 0 });
  });

  it("returns the end point at s=1", () => {
    expect(along(path, 1)).toEqual({ x: 10, y: 10 });
  });

  it("interpolates within a segment", () => {
    expect(along(path, 0.25)).toEqual({ x: 5, y: 0 });
  });

  it("interpolates across the second segment", () => {
    expect(along(path, 0.75)).toEqual({ x: 10, y: 5 });
  });
});

describe("fillSpacedText", () => {
  it("delegates to the native letterSpacing when the runtime has it", () => {
    const ctx = createFakeCanvasContext2D() as Ctx2D;
    const seen: string[] = [];
    (ctx.fillText as jest.Mock).mockImplementation(() =>
      seen.push(ctx.letterSpacing ?? "")
    );

    fillSpacedText(ctx, "AB", 10, 20, 2);

    expect(ctx.fillText).toHaveBeenCalledTimes(1);
    expect(ctx.fillText).toHaveBeenCalledWith("AB", 10, 20);
    expect(seen).toEqual(["2px"]);
    expect(ctx.letterSpacing).toBe("0px");
  });

  it("spaces glyphs by hand, left-aligned, when letterSpacing is unsupported", () => {
    const ctx = ctxWithoutLetterSpacing();
    ctx.textAlign = "left";

    fillSpacedText(ctx, "ABC", 10, 20, 2);

    const xs = (ctx.fillText as jest.Mock).mock.calls.map(([, x]) => x);
    expect(xs).toEqual([10, 17, 24]); // advance 5 + spacing 2 per glyph
    expect((ctx.fillText as jest.Mock).mock.calls.map(([g]) => g)).toEqual([
      "A",
      "B",
      "C",
    ]);
  });

  it("keeps a centered run centered on x, and restores the caller's alignment", () => {
    const ctx = ctxWithoutLetterSpacing();
    ctx.textAlign = "center";

    fillSpacedText(ctx, "ABC", 100, 0, 2);

    // total = 3*5 + 2*2 = 19, so it starts at 100 - 9.5
    const xs = (ctx.fillText as jest.Mock).mock.calls.map(([, x]) => x);
    expect(xs[0]).toBeCloseTo(90.5);
    expect(ctx.textAlign).toBe("center");
  });

  it("right-aligns a manually spaced run so its last glyph ends at x", () => {
    const ctx = ctxWithoutLetterSpacing();
    ctx.textAlign = "right";

    fillSpacedText(ctx, "AB", 50, 0, 2);

    const xs = (ctx.fillText as jest.Mock).mock.calls.map(([, x]) => x);
    expect(xs[0]).toBeCloseTo(50 - 12); // total = 2*5 + 2
  });

  it("draws the string in one call when no spacing is requested", () => {
    const ctx = ctxWithoutLetterSpacing();

    fillSpacedText(ctx, "ABC", 1, 2, 0);

    expect(ctx.fillText).toHaveBeenCalledTimes(1);
  });
});

describe("shape helpers", () => {
  it("never passes a negative radius to arc(), which browsers reject with IndexSizeError", () => {
    const ctx = createFakeCanvasContext2D() as Ctx2D;

    circle(ctx, 5, 5, -3);

    expect((ctx.arc as jest.Mock).mock.calls[0][2]).toBe(0);
  });

  it("caps a rounded-rect radius at half the shorter side and floors it at zero", () => {
    const ctx = createFakeCanvasContext2D() as Ctx2D;

    rrect(ctx, 0, 0, 10, 4, 99);
    rrect(ctx, 0, 0, 10, 4, -5);

    const radii = (ctx.arcTo as jest.Mock).mock.calls.map((c) => c[4]);
    expect(radii.slice(0, 4)).toEqual([2, 2, 2, 2]);
    expect(radii.slice(4)).toEqual([0, 0, 0, 0]);
  });
});

describe("sampleXs", () => {
  it("steps from zero and ends exactly on the last whole step", () => {
    expect(sampleXs(48, 16)).toEqual([0, 16, 32, 48]);
  });

  it("appends the edge when the width is not a multiple of the step", () => {
    expect(sampleXs(50, 16)).toEqual([0, 16, 32, 48, 50]);
  });
});
