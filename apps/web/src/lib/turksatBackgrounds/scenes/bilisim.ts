/**
 * "Tek Kapı" (Single Gateway) — Türkiye drawn as its 81 province centers,
 * with every request flowing to a single hub (plate 06, Ankara/e-Devlet) and
 * a response flowing back. Request volume per province is population-shaped,
 * not simulated traffic.
 */
import { DEG, VIRTUAL_H, VIRTUAL_W } from "../constants";
import { ANATOLIA, PROV, PROVINCE_WEIGHT, THRACE } from "../geo";
import { circle, hexA, poly, rng, text } from "../utils";
import { paletteFor } from "../palette";
import type { Point, Scene } from "../types";

const H = VIRTUAL_H;

const ANKARA_PLATE = 6;

interface ProvincePoint extends Point {
  n: number;
  w: number;
}

interface Pulse {
  a: ProvincePoint;
  b: ProvincePoint;
  c: Point;
  t0: number;
  dur: number;
  kind: "req" | "res";
}

interface BilisimState {
  P: (lo: number, la: number) => Point;
  top: number;
  mh: number;
  left: number;
  mw: number;
  prov: ProvincePoint[];
  byN: Record<number, ProvincePoint>;
  hub: ProvincePoint;
  total: number;
  r: () => number;
  pulses: Pulse[];
  acc: number;
  flash: Map<number, number>;
  hubHit?: number;
  rx0: number;
  ry0: number;
  lo0: number;
  lo1: number;
  la0: number;
  la1: number;
}

function makePulse(
  a: ProvincePoint,
  b: ProvincePoint,
  t0: number,
  kind: Pulse["kind"]
): Pulse {
  const d = Math.hypot(b.x - a.x, b.y - a.y);
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  let nx = -(b.y - a.y) / (d || 1);
  let ny = (b.x - a.x) / (d || 1);
  if (ny > 0) {
    nx = -nx;
    ny = -ny;
  }
  return {
    a,
    b,
    c: { x: mx + nx * d * 0.22, y: my + ny * d * 0.22 },
    t0,
    dur: 0.8 + d / 650,
    kind,
  };
}

function bezierPoint(pl: Pulse, e: number): Point {
  const m = 1 - e;
  return {
    x: m * m * pl.a.x + 2 * m * e * pl.c.x + e * e * pl.b.x,
    y: m * m * pl.a.y + 2 * m * e * pl.c.y + e * e * pl.b.y,
  };
}

export const bilisim: Scene<BilisimState> = {
  // The hub (plate 06) sits at the map's horizontal center and a bit below
  // vertical center — see `top = H * 0.585 - mh / 2` below.
  focal: { x: 0.5, y: 0.58 },

  init(env) {
    const cl = Math.cos(39 * DEG);
    const lo0 = 25.6;
    const lo1 = 44.9;
    const la0 = 35.8;
    const la1 = 42.2;
    const k = Math.min(
      (VIRTUAL_W * 0.9) / ((lo1 - lo0) * cl),
      (H * 0.5) / (la1 - la0)
    );
    const mw = (lo1 - lo0) * cl * k;
    const mh = (la1 - la0) * k;
    const left = env.cx - mw / 2;
    const top = H * 0.585 - mh / 2;
    const P = (lo: number, la: number): Point => ({
      x: left + (lo - lo0) * cl * k,
      y: top + (la1 - la) * k,
    });
    const prov: ProvincePoint[] = PROV.map(([n, la, lo]) => ({
      n,
      ...P(lo, la),
      w: PROVINCE_WEIGHT[n] || 0.6,
    }));
    const byN: Record<number, ProvincePoint> = {};
    prov.forEach((q) => {
      byN[q.n] = q;
    });
    const total = prov.reduce(
      (s, q) => s + (q.n === ANKARA_PLATE ? 0 : q.w),
      0
    );
    const rackW = 5 * 22 + 4 * 6;
    const rx0 = env.colR + (env.w - env.colR - rackW) / 2;
    return {
      P,
      top,
      mh,
      left,
      mw,
      prov,
      byN,
      // Safe: plate 6 (Ankara) is always present in `PROV`.
      hub: byN[ANKARA_PLATE]!,
      total,
      r: rng(5),
      pulses: [],
      acc: 0,
      flash: new Map(),
      rx0,
      // Pinned near the frame's top edge, not floating mid-screen.
      ry0: env.top + 100,
      lo0,
      lo1,
      la0,
      la1,
    };
  },

  static(ctx, env, st) {
    const { dark } = env;
    const p = paletteFor("bilisim", env.dark);
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, p.bg0);
    g.addColorStop(1, p.bg1);
    ctx.fillStyle = g;
    ctx.fillRect(0, env.top, env.w, env.h);
    const h = st.hub;
    const rg = ctx.createRadialGradient(h.x, h.y, 0, h.x, h.y, 460);
    rg.addColorStop(0, hexA(p.accent, dark ? 0.14 : 0.09));
    rg.addColorStop(1, hexA(p.accent, 0));
    ctx.fillStyle = rg;
    ctx.fillRect(0, env.top, env.w, env.h);

    // Degree grid.
    ctx.strokeStyle = hexA(p.ink, dark ? 0.09 : 0.1);
    ctx.lineWidth = 1;
    ctx.setLineDash([1, 6]);
    for (let lo = 26; lo <= 44; lo += 2) {
      const a = st.P(lo, st.la1);
      const b = st.P(lo, st.la0);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y - 20);
      ctx.lineTo(b.x, b.y + 20);
      ctx.stroke();
    }
    for (let la = 36; la <= 42; la += 2) {
      const a = st.P(st.lo0, la);
      const b = st.P(st.lo1, la);
      ctx.beginPath();
      ctx.moveTo(a.x - 20, a.y);
      ctx.lineTo(b.x + 20, b.y);
      ctx.stroke();
    }
    // Coastline + border.
    ctx.setLineDash([1.5, 3.5]);
    ctx.strokeStyle = hexA(p.ink, dark ? 0.4 : 0.42);
    [ANATOLIA, THRACE].forEach((pl) => {
      poly(
        ctx,
        pl.map(([lo, la]) => st.P(lo, la))
      );
      ctx.stroke();
    });
    ctx.setLineDash([]);

    // 81 provinces and their plate numbers.
    for (const q of st.prov) {
      if (q.n === ANKARA_PLATE) continue;
      ctx.fillStyle = hexA(p.ink, dark ? 0.85 : 0.78);
      circle(ctx, q.x, q.y, 2.1);
      ctx.fill();
      text(
        ctx,
        String(q.n).padStart(2, "0"),
        q.x + 4,
        q.y - 4,
        hexA(p.ink, dark ? 0.42 : 0.5),
        8.5,
        "left",
        500
      );
    }

    // Data center racks.
    ctx.lineWidth = 1;
    for (let rk = 0; rk < 5; rk++) {
      const x = st.rx0 + rk * 28;
      ctx.strokeStyle = hexA(p.ink, dark ? 0.35 : 0.35);
      ctx.strokeRect(x, st.ry0 - 4, 22, 16 * 9 + 6);
      ctx.strokeStyle = hexA(p.ink, dark ? 0.14 : 0.14);
      for (let i = 0; i < 16; i++) ctx.strokeRect(x + 2, st.ry0 + i * 9, 18, 7);
    }
    text(
      ctx,
      "VERİ MERKEZİ",
      st.rx0,
      st.ry0 + 16 * 9 + 20,
      hexA(p.ink, 0.6),
      9,
      "left",
      600,
      1.2
    );

    // Barcoded document.
    const bx = 32;
    const by = env.bottom - 82;
    const r = rng(81);
    ctx.fillStyle = hexA(p.ink, dark ? 0.55 : 0.62);
    let x = bx;
    while (x < bx + 168) {
      const w = r() < 0.5 ? 1 : r() < 0.6 ? 2 : 3;
      ctx.fillRect(x, by, w, 26);
      x += w + (r() < 0.5 ? 1 : 2);
    }
    text(
      ctx,
      "e-DEVLET · BARKODLU BELGE",
      bx,
      by + 40,
      hexA(p.ink, 0.6),
      8.5,
      "left",
      600,
      0.8
    );
    text(
      ctx,
      "doğrulama kodu ile",
      bx,
      by + 53,
      hexA(p.ink, 0.45),
      8.5,
      "left",
      400
    );

    // Real-world cadence.
    text(
      ctx,
      "81 İL · 1 KAPI · ≈127 ERİŞİM/SN",
      env.w - 32,
      env.bottom - 46,
      hexA(p.ink, 0.62),
      9,
      "right",
      600,
      0.8
    );
    text(
      ctx,
      "2025: yaklaşık 4 milyar erişim",
      env.w - 32,
      env.bottom - 32,
      hexA(p.ink, 0.45),
      8.5,
      "right",
      400
    );
  },

  update(st, _env, t, dt) {
    st.acc += dt;
    while (st.acc > 0.085) {
      st.acc -= 0.085;
      let x = st.r() * st.total;
      // Safe: `prov` always holds all 81 provinces; the loop below picks
      // the one the weighted draw landed on, falling back to the first.
      let q = st.prov[0]!;
      for (const c of st.prov) {
        if (c.n === ANKARA_PLATE) continue;
        x -= c.w;
        if (x <= 0) {
          q = c;
          break;
        }
      }
      st.pulses.push(makePulse(q, st.hub, t, "req"));
    }
    const keep: Pulse[] = [];
    for (const pl of st.pulses) {
      if (t - pl.t0 < pl.dur) {
        keep.push(pl);
        continue;
      }
      if (pl.kind === "req") {
        keep.push(makePulse(st.hub, pl.a, t + 0.06, "res"));
        st.hubHit = t;
      } else {
        st.flash.set(pl.b.n, t);
      }
    }
    st.pulses = keep;
  },

  frame(ctx, env, t, st) {
    const { dark } = env;
    const p = paletteFor("bilisim", env.dark);
    ctx.lineWidth = 1;
    for (const pl of st.pulses) {
      const u = (t - pl.t0) / pl.dur;
      if (u < 0 || u > 1) continue;
      const e = 0.5 - 0.5 * Math.cos(Math.PI * u);
      const col = pl.kind === "req" ? p.ink : p.accent;
      ctx.strokeStyle = hexA(col, (dark ? 0.11 : 0.1) * Math.sin(Math.PI * u));
      ctx.beginPath();
      ctx.moveTo(pl.a.x, pl.a.y);
      ctx.quadraticCurveTo(pl.c.x, pl.c.y, pl.b.x, pl.b.y);
      ctx.stroke();
      for (let j = 6; j >= 0; j--) {
        const e2 = e - j * 0.017;
        if (e2 < 0) continue;
        const q = bezierPoint(pl, e2);
        ctx.fillStyle = hexA(
          col,
          (1 - j / 7) * (pl.kind === "req" ? 0.7 : 0.95)
        );
        circle(ctx, q.x, q.y, j ? 1.2 : 2);
        ctx.fill();
      }
    }
    // `Map` iteration needs ES2015+ (this project targets ES5), so walk it
    // with `forEach` instead of `for...of`.
    st.flash.forEach((tf, n) => {
      const a = 1 - (t - tf) / 0.9;
      if (a <= 0) {
        st.flash.delete(n);
        return;
      }
      const q = st.byN[n];
      if (!q) return;
      ctx.strokeStyle = hexA(p.accent, a * 0.7);
      circle(ctx, q.x, q.y, 2.5 + (1 - a) * 9);
      ctx.stroke();
    });
    // The single gateway: plate 06.
    const h = st.hub;
    for (let i = 0; i < 3; i++) {
      const f = (t * 0.45 + i / 3) % 1;
      ctx.strokeStyle = hexA(p.red, 0.55 * (1 - f));
      circle(ctx, h.x, h.y, 5 + f * 40);
      ctx.stroke();
    }
    const hit = st.hubHit ? Math.max(0, 1 - (t - st.hubHit) / 0.25) : 0;
    ctx.fillStyle = hexA(p.red, 0.18 + 0.15 * hit);
    circle(ctx, h.x, h.y, 9);
    ctx.fill();
    ctx.fillStyle = p.red;
    circle(ctx, h.x, h.y, 3.4);
    ctx.fill();
    text(ctx, "06", h.x + 8, h.y - 8, p.red, 11, "left", 600);
    // Rack activity LEDs.
    for (let rk = 0; rk < 5; rk++) {
      for (let i = 0; i < 16; i++) {
        const hsh = (((rk * 16 + i) * 2654435761) >>> 0) / 4294967296;
        const x = st.rx0 + rk * 28;
        const y = st.ry0 + i * 9;
        const on1 = (t * (0.15 + hsh * 0.5) + hsh * 7) % 1 < 0.85;
        const on2 = (t * (1.2 + hsh * 3) + hsh * 13) % 1 < 0.35;
        ctx.fillStyle = hexA(p.led, on1 ? 0.9 : 0.2);
        ctx.fillRect(x + 4, y + 2.5, 2, 2);
        ctx.fillStyle = hexA(p.accent, on2 ? 0.95 : 0.15);
        ctx.fillRect(x + 8, y + 2.5, 2, 2);
      }
    }
  },
};
