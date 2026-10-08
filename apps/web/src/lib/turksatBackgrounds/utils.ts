import { MONO, TAU } from "./constants";
import type { Ctx2D, Env, Path, Point } from "./types";

/** Deterministic PRNG (mulberry32-family) so a given scene animates
 * identically on every mount instead of reshuffling its stars/particles. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Box-Muller transform driven by `rng`, for a normal-ish jitter. */
export function gauss(r: () => number): number {
  let u = 0;
  while (!u) u = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * r());
}

/** `#rrggbb` + alpha -> `rgba(...)`, so palette tokens stay hex everywhere
 * except where a scene needs to fade one in or out. */
export function hexA(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  const clamped = Math.max(0, Math.min(1, a));
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${clamped})`;
}

/**
 * Fills `s` with the context's current font, fill, and alignment, spaced by
 * `spacing` px per glyph. Canvas `letterSpacing` is not available in every
 * browser (Safari before 18.4, Firefox before 115), so without it the run is
 * laid out glyph by glyph, keeping the caller's alignment anchored at `x`.
 */
export function fillSpacedText(
  ctx: Ctx2D,
  s: string,
  x: number,
  y: number,
  spacing: number
): void {
  if (!spacing) {
    ctx.fillText(s, x, y);
    return;
  }
  if (typeof ctx.letterSpacing === "string") {
    ctx.letterSpacing = `${spacing}px`;
    ctx.fillText(s, x, y);
    ctx.letterSpacing = "0px";
    return;
  }

  const glyphs = Array.from(s);
  const advances = glyphs.map((g) => ctx.measureText(g).width);
  const total =
    advances.reduce((sum, w) => sum + w, 0) + spacing * (glyphs.length - 1);
  const align = ctx.textAlign;
  let cursor = x;
  if (align === "center") cursor = x - total / 2;
  else if (align === "right" || align === "end") cursor = x - total;

  ctx.textAlign = "left";
  glyphs.forEach((g, i) => {
    ctx.fillText(g, cursor, y);
    cursor += advances[i]! + spacing;
  });
  ctx.textAlign = align;
}

export function text(
  ctx: Ctx2D,
  s: string,
  x: number,
  y: number,
  color: string,
  size = 10,
  align: CanvasTextAlign = "left",
  weight: number | string = 500,
  spacing = 0
): void {
  ctx.font = `${weight} ${size}px ${MONO}`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "alphabetic";
  fillSpacedText(ctx, s, x, y, spacing);
}

export function circle(ctx: Ctx2D, x: number, y: number, r: number): void {
  ctx.beginPath();
  // A negative radius makes `arc()` throw IndexSizeError in every browser.
  ctx.arc(x, y, Math.max(0, r), 0, TAU);
}

export function poly(ctx: Ctx2D, pts: readonly Point[], close = true): void {
  ctx.beginPath();
  pts.forEach((q, i) => (i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y)));
  if (close) ctx.closePath();
}

export function rrect(
  ctx: Ctx2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius: number
): void {
  // `arcTo()` throws IndexSizeError on a negative radius.
  const r = Math.max(0, Math.min(radius, Math.abs(w) / 2, Math.abs(h) / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** Precomputes cumulative segment lengths for `along()`. */
export function measure(pts: readonly Point[]): Path {
  const seg: number[] = [];
  let L = 0;
  for (let i = 1; i < pts.length; i++) {
    // Safe: the loop bound guarantees both indices are within `pts`.
    const curr = pts[i]!;
    const prev = pts[i - 1]!;
    const l = Math.hypot(curr.x - prev.x, curr.y - prev.y);
    seg.push(l);
    L += l;
  }
  return { pts: [...pts], seg, L };
}

/**
 * How much a moving element (a signal pulse, a data particle) should fade
 * under the app's own centered readability panel behind the message column
 * — 1 at the edges, dimmer near the column center. Shared by every scene
 * that animates something crossing the frame horizontally.
 */
export function calmAt(env: Env, x: number): number {
  const d = Math.abs(x - env.cx) / (env.colW / 2);
  return d >= 1 ? 1 : 0.3 + 0.7 * Math.max(0, (d - 0.6) / 0.4);
}

/** Point at fraction `s` (0..1) along a `measure()`d polyline. */
export function along(path: Path, s: number): Point {
  let d = s * path.L;
  for (let i = 0; i < path.seg.length; i++) {
    // Safe: `i` is within `seg`, and `pts.length === seg.length + 1` (see
    // `measure()`), so `pts[i]`/`pts[i + 1]` are always within `pts`.
    const segLen = path.seg[i]!;
    if (d <= segLen || i === path.seg.length - 1) {
      const f = segLen ? Math.min(1, d / segLen) : 0;
      const a = path.pts[i]!;
      const b = path.pts[i + 1]!;
      return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
    }
    d -= segLen;
  }
  return path.pts[0] ?? { x: 0, y: 0 };
}

/** `0, step, 2*step, ...` up to and always including `end`, so a polyline
 * sampled across a frame of any width reaches its right edge exactly instead
 * of stopping at the last whole step. */
export function sampleXs(end: number, step: number): number[] {
  const xs: number[] = [];
  for (let x = 0; x < end; x += step) xs.push(x);
  xs.push(end);
  return xs;
}
