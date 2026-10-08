/**
 * "Güney Göğü" (Southern Sky) — the sky Gölbaşı's ground station antennas
 * actually see. The geostationary belt is drawn as a real arc in that sky
 * (from Gölbaşı's latitude/longitude), Türksat's satellites sit on it at
 * their real azimuth/elevation, stars sweep east-to-west while the
 * satellites hold still, and a single signal path runs uplink (red) through
 * 42°E and back down (gold) to a second dish.
 */
import { DEG, MONO, TAU, VIRTUAL_H, VIRTUAL_W } from "../constants";
import {
  calmAt,
  circle,
  fillSpacedText,
  hexA,
  poly,
  rng,
  sampleXs,
  text,
} from "../utils";
import { paletteFor, type UyduPalette } from "../palette";
import type { Ctx2D, Point, Scene } from "../types";

const H = VIRTUAL_H;

interface Dish {
  x: number;
  h: number;
  D: number;
  target: number;
  role?: "up" | "down";
  base: number;
  piv: Point;
  th: number;
}

interface Slot {
  lon: number;
  names: string;
  n: number;
  az: number;
  el: number;
  x: number;
  y: number;
}

interface Star {
  dec: number;
  ha0: number;
  s: number;
  ph: number;
  f: number;
  b: number;
}

interface UyduState {
  horizon: number;
  kx: number;
  ky: number;
  P: (az: number, el: number) => Point;
  geo: (dl: number) => { az: number; el: number };
  sky: (dec: number, ha: number) => { alt: number; az: number };
  arc: Point[];
  ceq: Point[];
  slots: Slot[];
  stars: Star[];
  dishes: Dish[];
  siteLon: number;
}

function drawDish(ctx: Ctx2D, d: Dish, p: UyduPalette, dark: boolean): void {
  const { piv, D, base } = d;
  const f = D * 0.42;
  const c = D * 0.12;
  const half = D / 2;
  ctx.lineWidth = 1;
  ctx.fillStyle = p.dish;
  ctx.strokeStyle = hexA(p.ink, dark ? 0.55 : 0.6);
  ctx.beginPath();
  ctx.moveTo(piv.x - 4, piv.y);
  ctx.lineTo(piv.x + 4, piv.y);
  ctx.lineTo(piv.x + 12, base);
  ctx.lineTo(piv.x - 12, base);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.save();
  ctx.translate(piv.x, piv.y);
  ctx.rotate(d.th);
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(-c - 3, 0);
  ctx.stroke();
  ctx.beginPath();
  for (let i = 0; i <= 28; i++) {
    const y = -half + (i / 28) * D;
    const x = (y * y) / (4 * f) - c;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  for (let i = 28; i >= 0; i--) {
    const y = -half + (i / 28) * D;
    ctx.lineTo((y * y) / (4 * f) - c - 3.5, y);
  }
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  const rimX = (half * half) / (4 * f) - c;
  const fx = f - c;
  ctx.beginPath();
  ctx.moveTo(rimX, -half + 2);
  ctx.lineTo(fx, 0);
  ctx.moveTo(rimX, half - 2);
  ctx.lineTo(fx, 0);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(fx + 2, 0, Math.max(2.5, D * 0.06), Math.PI / 2, Math.PI * 1.5);
  ctx.stroke();
  ctx.restore();
}

function dishFocus(d: Dish): Point {
  const fx = d.D * 0.3;
  return { x: d.piv.x + fx * Math.cos(d.th), y: d.piv.y + fx * Math.sin(d.th) };
}

export const uydu: Scene<UyduState> = {
  // The horizon and ground rest on the frame's bottom edge; a taller frame
  // adds sky above them (the stars and the arc's zenith), not empty ground.
  anchorY: 1,
  // Slightly left of center: the 42°E slot (the busiest orbital position)
  // and most of the uplink beam sit around x≈599/1440. Only windows narrower
  // than 16:10 crop (the sides); wider ones widen the frame instead, so `y`
  // stays near-neutral.
  focal: { x: 0.46, y: 0.52 },
  init(env) {
    const r = rng(11);
    const phi = 39.79 * DEG;
    const siteLon = 32.81;
    const horizon = 772;
    const kx = (VIRTUAL_W * 0.96) / 160;
    const ky = (horizon - 72) / 43.9;
    // Facing south: east is to the left, west to the right.
    const P = (az: number, el: number): Point => ({
      x: env.cx + (az - 180) * kx,
      y: horizon - el * ky,
    });
    const geo = (dl: number) => {
      const d = dl * DEG;
      const cg = Math.cos(phi) * Math.cos(d);
      const g = Math.acos(cg);
      return {
        az: 180 - Math.atan2(Math.tan(d), Math.sin(phi)) / DEG,
        el: Math.atan2(cg - 0.1513, Math.sin(g)) / DEG,
      };
    };
    const sky = (dec: number, ha: number) => {
      const sd = Math.sin(dec);
      const cd = Math.cos(dec);
      const ch = Math.cos(ha);
      const alt = Math.asin(Math.sin(phi) * sd + Math.cos(phi) * cd * ch);
      const az = Math.atan2(
        -cd * Math.sin(ha),
        sd * Math.cos(phi) - cd * ch * Math.sin(phi)
      );
      return { alt: alt / DEG, az: (az / DEG + 360) % 360 };
    };
    const arc: Point[] = [];
    for (let d = -81; d <= 81; d += 1) {
      const g = geo(d);
      if (g.el >= 0) arc.push(P(g.az, g.el));
    }
    const ceq: Point[] = [];
    for (let h = -90; h <= 90; h += 2) {
      const s = sky(0, h * DEG);
      if (s.alt >= 0) ceq.push(P(s.az, s.alt));
    }
    const slots: Slot[] = [
      { lon: 31, names: "5A", n: 1 },
      { lon: 42, names: "3A · 4A · 5B · 6A", n: 4 },
      { lon: 50, names: "4B", n: 1 },
    ].map((s) => {
      const g = geo(s.lon - siteLon);
      return { ...s, az: g.az, el: g.el, ...P(g.az, g.el) };
    });
    const stars: Star[] = [];
    const n = env.dark ? 460 : 220;
    for (let i = 0; i < n; i++) {
      stars.push({
        dec: (-50 + r() * 100) * DEG,
        ha0: r() * TAU,
        s: 0.45 + r() * r() * 1.7,
        ph: r() * TAU,
        f: 0.4 + r() * 1.6,
        b: 0.35 + r() * 0.65,
      });
    }
    const dishes: Dish[] = [
      { x: 84, h: 46, D: 86, target: 1, role: "up" as const },
      { x: 190, h: 30, D: 54, target: 2 },
      { x: env.w - 92, h: 44, D: 80, target: 1, role: "down" as const },
      { x: env.w - 200, h: 28, D: 48, target: 0 },
    ].map((d) => {
      const base = horizon + 42;
      const piv = { x: d.x, y: base - d.h };
      // Safe: `target` is always one of the 3 fixed slot indices above.
      const S = slots[d.target]!;
      return { ...d, base, piv, th: Math.atan2(S.y - piv.y, S.x - piv.x) };
    });
    return {
      horizon,
      kx,
      ky,
      P,
      geo,
      sky,
      arc,
      ceq,
      slots,
      stars,
      dishes,
      siteLon,
    };
  },

  static(ctx, env, st) {
    const { dark } = env;
    const p = paletteFor("uydu", env.dark);
    const hz = st.horizon;
    let g = ctx.createLinearGradient(0, 0, 0, hz);
    g.addColorStop(0, p.sky0);
    g.addColorStop(1, p.sky1);
    ctx.fillStyle = g;
    ctx.fillRect(0, env.top, env.w, env.h);
    g = ctx.createRadialGradient(env.cx, hz + 40, 0, env.cx, hz + 40, 760);
    g.addColorStop(0, hexA(p.gold, dark ? 0.12 : 0.1));
    g.addColorStop(1, hexA(p.gold, 0));
    ctx.fillStyle = g;
    ctx.fillRect(0, env.top, env.w, hz - env.top);

    // Sky grid: elevation rings and azimuth spokes.
    ctx.lineWidth = 1;
    ctx.setLineDash([1, 6]);
    ctx.strokeStyle = hexA(p.ink, dark ? 0.16 : 0.18);
    [10, 20, 30, 40].forEach((el) => {
      const y = hz - el * st.ky;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(env.w, y);
      ctx.stroke();
    });
    for (let az = 90; az <= 270; az += 15) {
      const q = st.P(az, 0);
      if (q.x < 0 || q.x > env.w) continue;
      ctx.beginPath();
      ctx.moveTo(q.x, hz);
      ctx.lineTo(q.x, 0);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    [10, 20, 30, 40].forEach((el) =>
      text(
        ctx,
        `EL ${el}°`,
        14,
        hz - el * st.ky - 5,
        hexA(p.ink, 0.5),
        9,
        "left",
        500
      )
    );

    // Celestial equator.
    ctx.setLineDash([2, 5]);
    ctx.strokeStyle = hexA(p.ink, dark ? 0.38 : 0.38);
    poly(ctx, st.ceq, false);
    ctx.stroke();
    ctx.setLineDash([]);
    const cq = st.ceq.find((q) => q.x > 40 && q.y < hz - 60);
    if (cq)
      text(
        ctx,
        "gök ekvatoru",
        cq.x + 6,
        cq.y - 6,
        hexA(p.ink, 0.5),
        9,
        "left",
        400
      );

    // Geostationary belt.
    if (dark) {
      ctx.strokeStyle = hexA(p.gold, 0.1);
      ctx.lineWidth = 7;
      poly(ctx, st.arc, false);
      ctx.stroke();
    }
    ctx.strokeStyle = hexA(p.gold, dark ? 0.72 : 0.78);
    ctx.lineWidth = 1.4;
    poly(ctx, st.arc, false);
    ctx.stroke();
    ctx.lineWidth = 1;
    for (let lon = -40; lon <= 100; lon += 10) {
      const gg = st.geo(lon - st.siteLon);
      if (gg.el < 3) continue;
      const q = st.P(gg.az, gg.el);
      ctx.strokeStyle = hexA(p.gold, 0.65);
      ctx.beginPath();
      ctx.moveTo(q.x, q.y - 3);
      ctx.lineTo(q.x, q.y + 4);
      ctx.stroke();
      if (lon % 20 === 0 && (lon <= 20 || lon >= 60)) {
        text(
          ctx,
          lon === 0 ? "0°" : lon > 0 ? `${lon}°D` : `${-lon}°B`,
          q.x,
          q.y + 17,
          hexA(p.gold, 0.75),
          8.5,
          "center",
          500
        );
      }
    }
    // The belt runs right-to-left; label from the first point in the right
    // margin, angled to follow the arc there.
    const li = st.arc.findIndex((q) => q.x < env.colR + 60);
    if (li > 0 && li < st.arc.length - 1) {
      // Safe: the `if` bounds guarantee `li - 1`, `li`, and `li + 1` are all
      // within `st.arc`.
      const a = st.arc[li - 1]!;
      const b = st.arc[li + 1]!;
      const q = st.arc[li]!;
      ctx.save();
      ctx.translate(q.x, q.y);
      ctx.rotate(Math.atan2(a.y - b.y, a.x - b.x));
      ctx.font = `600 9px ${MONO}`;
      ctx.fillStyle = hexA(p.gold, 0.85);
      ctx.textAlign = "left";
      ctx.textBaseline = "bottom";
      fillSpacedText(ctx, "YER DURAĞAN KUŞAK · 35 786 km", 6, -6, 1);
      ctx.restore();
    }

    // Ground.
    ctx.beginPath();
    const groundXs = sampleXs(env.w, 16);
    const groundY = (x: number) =>
      hz + 2.5 * Math.sin(x * 0.012) + 2 * Math.sin(x * 0.033 + 1.2);
    ctx.moveTo(0, env.bottom);
    ctx.lineTo(0, hz);
    groundXs.forEach((x) => ctx.lineTo(x, groundY(x)));
    ctx.lineTo(env.w, env.bottom);
    ctx.closePath();
    g = ctx.createLinearGradient(0, hz, 0, env.bottom);
    g.addColorStop(0, p.ground1);
    g.addColorStop(1, p.ground0);
    ctx.fillStyle = g;
    ctx.fill();
    ctx.strokeStyle = hexA(p.ink, dark ? 0.4 : 0.45);
    ctx.beginPath();
    groundXs.forEach((x) =>
      x ? ctx.lineTo(x, groundY(x)) : ctx.moveTo(x, groundY(x))
    );
    ctx.stroke();
    (
      [
        [90, "D"],
        [135, "GD"],
        [180, "G"],
        [225, "GB"],
        [270, "B"],
      ] as const
    ).forEach(([az, s]) => {
      const q = st.P(az, 0);
      if (q.x < 40 || q.x > env.w - 40) return;
      text(
        ctx,
        `${s} ${az}°`,
        q.x,
        hz - 9,
        hexA(p.ink, 0.6),
        9,
        "center",
        600,
        0.6
      );
    });

    // Which way each fixed dish points.
    ctx.setLineDash([2, 6]);
    for (const d of st.dishes) {
      if (d.role) continue;
      const F = dishFocus(d);
      // Safe: `target` is always one of the 3 fixed slot indices from `init`.
      const S = st.slots[d.target]!;
      ctx.strokeStyle = hexA(p.gold, dark ? 0.22 : 0.28);
      ctx.beginPath();
      ctx.moveTo(F.x, F.y);
      ctx.lineTo(S.x, S.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    for (const d of st.dishes) drawDish(ctx, d, p, dark);

    // Orbital slots.
    for (const s of st.slots) {
      text(
        ctx,
        `${s.lon}°D`,
        s.x,
        s.y - 30,
        hexA(p.ink, 0.92),
        11.5,
        "center",
        600,
        0.5
      );
      text(ctx, s.names, s.x, s.y - 17, hexA(p.ink, 0.62), 9.5, "center", 500);
      text(
        ctx,
        `AZ ${Math.round(s.az)}° · EL ${s.el.toFixed(1).replace(".", ",")}°`,
        s.x,
        s.y + 26,
        hexA(p.gold, 0.9),
        9,
        "center",
        500
      );
    }
    text(
      ctx,
      "GÖLBAŞI YER İSTASYONU",
      32,
      env.bottom - 34,
      hexA(p.ink, 0.75),
      9,
      "left",
      600,
      1
    );
    text(
      ctx,
      "39,79°K · 32,81°D · güneye bakış",
      32,
      env.bottom - 20,
      hexA(p.ink, 0.5),
      8.5,
      "left",
      400
    );
    text(
      ctx,
      "UPLINK → 42°D → DOWNLINK",
      env.w - 32,
      env.bottom - 34,
      hexA(p.ink, 0.7),
      9,
      "right",
      600,
      1
    );
    text(
      ctx,
      "Ku · Ka bant",
      env.w - 32,
      env.bottom - 20,
      hexA(p.ink, 0.5),
      8.5,
      "right",
      400
    );
  },

  frame(ctx, env, t, st) {
    const { dark } = env;
    const p = paletteFor("uydu", env.dark);
    const ha = t * 0.25 * DEG;
    const hz = st.horizon;
    // Stars sweep with the real sky motion; satellites hold still.
    for (const s of st.stars) {
      const q = st.sky(s.dec, s.ha0 + ha);
      if (q.alt < 0.8) continue;
      const x = env.cx + (q.az - 180) * st.kx;
      const y = hz - q.alt * st.ky;
      if (x < -4 || x > env.w + 4 || y < env.top - 4) continue;
      const tw = 0.55 + 0.45 * Math.sin(t * s.f + s.ph);
      const fade = Math.min(1, q.alt / 6);
      if (dark) {
        ctx.fillStyle = hexA("#DCE6FF", s.b * tw * 0.85 * fade);
        ctx.fillRect(x - s.s / 2, y - s.s / 2, s.s, s.s);
      } else {
        const k = 1.3 + s.s;
        ctx.strokeStyle = hexA(p.ink, (0.06 + 0.2 * s.b * tw) * fade);
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(x - k, y);
        ctx.lineTo(x + k, y);
        ctx.moveTo(x, y - k);
        ctx.lineTo(x, y + k);
        ctx.stroke();
      }
    }
    // Signal path: uplink red, downlink gold.
    // Safe: `slots` always holds exactly the 3 orbital positions built in `init`.
    const S = st.slots[1]!;
    const up = st.dishes.find((d) => d.role === "up")!;
    const dn = st.dishes.find((d) => d.role === "down")!;
    const A = dishFocus(up);
    const B = dishFocus(dn);
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 5]);
    ctx.lineDashOffset = -t * 16;
    ctx.strokeStyle = hexA(p.red, dark ? 0.45 : 0.5);
    ctx.beginPath();
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(S.x, S.y);
    ctx.stroke();
    ctx.lineDashOffset = -t * 16;
    ctx.strokeStyle = hexA(p.gold, dark ? 0.5 : 0.55);
    ctx.beginPath();
    ctx.moveTo(S.x, S.y);
    ctx.lineTo(B.x, B.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineDashOffset = 0;
    for (let i = 0; i < 3; i++) {
      const f = (t * 0.16 + i / 3) % 1;
      (
        [
          [A, S, p.red],
          [S, B, p.gold],
        ] as const
      ).forEach(([a, b, col]) => {
        const x = a.x + (b.x - a.x) * f;
        const y = a.y + (b.y - a.y) * f;
        const k = calmAt(env, x);
        ctx.fillStyle = hexA(col, 0.16 * k);
        circle(ctx, x, y, 6);
        ctx.fill();
        ctx.fillStyle = hexA(col, 0.95 * k);
        circle(ctx, x, y, 2.1);
        ctx.fill();
      });
    }
    const fp = 0.5 + 0.5 * Math.sin(t * 2.4);
    ctx.fillStyle = hexA(p.red, 0.25 + 0.4 * fp);
    circle(ctx, A.x, A.y, 3.2);
    ctx.fill();
    ctx.fillStyle = hexA(p.gold, 0.25 + 0.4 * (1 - fp));
    circle(ctx, B.x, B.y, 3.2);
    ctx.fill();
    // Satellites and their station-keeping boxes.
    for (const s of st.slots) {
      ctx.strokeStyle = hexA(p.ink, dark ? 0.45 : 0.5);
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.strokeRect(s.x - 14, s.y - 14, 28, 28);
      ctx.setLineDash([]);
      const offs: ReadonlyArray<readonly [number, number]> =
        s.n === 1
          ? [[0, 0]]
          : [
              [-5.5, -5],
              [5, -5.5],
              [-5, 5.5],
              [5.5, 5],
            ];
      offs.forEach(([ox, oy], j) => {
        const x = s.x + ox;
        const y = s.y + oy;
        const L = s.n === 1 ? 7 : 4.5;
        const b = (Math.sin(t * 1.7 + j * 2.1 + s.lon) + 1) / 2;
        ctx.fillStyle = hexA(p.gold, 0.14 + 0.2 * b);
        circle(ctx, x, y, s.n === 1 ? 7 : 4.5);
        ctx.fill();
        ctx.strokeStyle = hexA(p.gold, 0.95);
        ctx.lineWidth = s.n === 1 ? 1.6 : 1.2;
        ctx.beginPath();
        ctx.moveTo(x - L, y);
        ctx.lineTo(x + L, y);
        ctx.stroke();
        ctx.fillStyle = p.gold;
        const bs = s.n === 1 ? 3.4 : 2.4;
        ctx.fillRect(x - bs / 2, y - bs / 2, bs, bs);
      });
    }
  },
};
