/**
 * "Bütün Ev" (The Whole Home) — what Türksat Kablo actually puts in a
 * subscriber's home: Kablonet (fiber/cable internet + Wi-Fi), KabloTV (the
 * set-top box and its EPG), KabloSes (the landline phone off the modem), and
 * the wall outlet + building entry cable that feeds all of it.
 */
import { DEG, MONO, VIRTUAL_H } from "../constants";
import {
  along,
  calmAt,
  circle,
  hexA,
  measure,
  poly,
  rng,
  rrect,
  text,
} from "../utils";
import { paletteFor } from "../palette";
import type { Path, Point, Scene } from "../types";

const H = VIRTUAL_H;

const SCREENS: ReadonlyArray<readonly [string, string, string]> = [
  ["#10355A", "#0E7C74", "#F2A65A"],
  ["#2B1B4A", "#8A2C4F", "#FFB36B"],
  ["#0D3B2E", "#2F7D4F", "#D7E36B"],
  ["#0B2A4A", "#1C5FA8", "#8FD3FF"],
];
const GAUGE_MARKS = [0, 100, 250, 500, 750, 1000];
/** Smallest x for the modem cluster's centre: its Wi-Fi rings reach ~142
 * units left of the modem, plus a margin. */
const CLUSTER_LEFT_MIN = 208;
/** Smallest gap between the TV cluster's centre and the right edge. */
const CLUSTER_RIGHT_MARGIN = 130;
const LEDS = ["POWER", "DS", "US", "ONLINE", "2.4G", "5G", "TEL 1"];

interface EpgBlock {
  m0: number;
  m1: number;
  title: string;
}

interface KabloState {
  M: { x: number; y: number; w: number; h: number };
  phone: Point;
  gauge: { x: number; y: number; r: number };
  tv: { x: number; y: number; w: number; h: number };
  con: { x: number; y: number; w: number };
  box: { x: number; y: number; w: number; h: number };
  remote: Point;
  outlet: { x: number; y: number; w: number; h: number };
  tvJ: Point;
  dataJ: Point;
  mcx: number;
  entry: Path;
  tvLine: Path;
  dataLine: Path;
  floorY: number;
  epg: EpgBlock[][];
  ex0: number;
  ex1: number;
}

/** Maps a minute offset (0..180) onto the EPG strip's x range. */
function epgX(st: KabloState, m: number): number {
  return st.ex0 + (Math.max(0, Math.min(180, m)) / 180) * (st.ex1 - st.ex0);
}

/** Angle for a given Mbps reading on the 300°-sweep speed gauge. */
function gaugeAngle(v: number): number {
  let i = 0;
  // Safe: `i` only ever reaches 0..4, so `i` and `i + 1` both stay within
  // `GAUGE_MARKS` (6 marks, indices 0..5).
  while (i < 4 && v > GAUGE_MARKS[i + 1]!) i++;
  const f =
    (i + (v - GAUGE_MARKS[i]!) / (GAUGE_MARKS[i + 1]! - GAUGE_MARKS[i]!)) / 5;
  return 135 * DEG + 270 * DEG * Math.max(0, Math.min(1, f));
}

export const kablo: Scene<KabloState> = {
  // Everything stands on the floor, so the scene rests on the frame's bottom
  // edge; the schedule strip is pinned to the top edge instead (see the EPG
  // blocks), leaving the middle — behind the message column — open.
  anchorY: 1,
  // Roughly the midpoint between the modem cluster (left third) and the
  // TV cluster (right third) — already near the frame's horizontal center.
  focal: { x: 0.5, y: 0.46 },

  init(env) {
    const r = rng(23);
    // Centre each side cluster in the space beside the message column, but
    // never so close to an edge that its Wi-Fi rings (left) or TV set (right)
    // would be clipped by it.
    const Lc = Math.max(env.colL / 2, CLUSTER_LEFT_MIN);
    const Rc = Math.min((env.colR + env.w) / 2, env.w - CLUSTER_RIGHT_MARGIN);
    const floorY = 884;
    const M = { x: Lc - 90, y: 560, w: 72, h: 210 };
    const phone: Point = { x: Lc + 40, y: 742 };
    const gauge = { x: Lc, y: 268, r: 66 };
    const tv = { x: Rc - 98, y: 290, w: 196, h: 116 };
    const con = { x: Rc - 106, y: 505, w: 212 };
    const box = { x: Rc - 42, y: 483, w: 110, h: 22 };
    const remote: Point = { x: Rc - 84, y: 497 };
    const outlet = { x: Rc - 26, y: 770, w: 40, h: 58 };
    const jx = outlet.x + outlet.w / 2;
    const tvJ: Point = { x: jx, y: outlet.y + 17 };
    const dataJ: Point = { x: jx, y: outlet.y + 41 };
    const mcx = M.x + 54;
    const entry = measure([
      { x: env.w + 4, y: outlet.y + 29 },
      { x: outlet.x + outlet.w, y: outlet.y + 29 },
    ]);
    const tvLine = measure([
      { x: tvJ.x, y: tvJ.y - 8 },
      { x: tvJ.x, y: box.y + box.h },
    ]);
    const dataLine = measure([
      { x: dataJ.x, y: dataJ.y + 8 },
      { x: dataJ.x, y: floorY },
      { x: mcx, y: floorY },
      { x: mcx, y: M.y + M.h },
    ]);
    const titles = [
      "Ana Haber",
      "Dizi",
      "Canlı Maç",
      "Belgesel",
      "Sinema",
      "Çocuk",
      "Müzik",
      "Yarışma",
      "Spor Özeti",
      "Söyleşi",
      "Hava Durumu",
      "Tarih",
    ];
    const epg: EpgBlock[][] = [0, 1, 2].map(() => {
      const blocks: EpgBlock[] = [];
      let m = -20 - Math.floor(r() * 30);
      while (m < 200) {
        // Safe: `Math.floor(r() * n)` for `r() ∈ [0, 1)` always lands in
        // `[0, n - 1]`, within both arrays below.
        const d = [30, 45, 60, 60, 90, 120][Math.floor(r() * 6)]!;
        blocks.push({
          m0: m,
          m1: m + d,
          title: titles[Math.floor(r() * titles.length)]!,
        });
        m += d;
      }
      return blocks;
    });
    return {
      M,
      phone,
      gauge,
      tv,
      con,
      box,
      remote,
      outlet,
      tvJ,
      dataJ,
      mcx,
      entry,
      tvLine,
      dataLine,
      floorY,
      epg,
      ex0: 70,
      ex1: env.w - 84,
    };
  },

  static(ctx, env, st) {
    const { dark } = env;
    const p = paletteFor("kablo", env.dark);
    const ink = (a: number) => hexA(p.ink, a);
    const g = ctx.createLinearGradient(0, 0, env.w * 0.4, H);
    g.addColorStop(0, p.bg1);
    g.addColorStop(1, p.bg0);
    ctx.fillStyle = g;
    ctx.fillRect(0, env.top, env.w, env.h);

    // KabloTV broadcast schedule (EPG), pinned to the frame's top edge.
    ctx.save();
    ctx.translate(0, env.top);
    ctx.lineWidth = 1;
    for (let m = 0; m <= 180; m += 30) {
      const x = epgX(st, m);
      text(
        ctx,
        `${20 + Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`,
        x + 3,
        17,
        ink(0.55),
        8.5,
        "left",
        500
      );
      ctx.strokeStyle = ink(0.18);
      ctx.beginPath();
      ctx.moveTo(x, 9);
      ctx.lineTo(x, 74);
      ctx.stroke();
    }
    st.epg.forEach((row, i) => {
      const y = 24 + i * 17;
      text(ctx, String(101 + i), 32, y + 10, ink(0.75), 9, "left", 600);
      for (const b of row) {
        if (b.m1 <= 0 || b.m0 >= 180) continue;
        const x0 = epgX(st, b.m0) + 1;
        const x1 = epgX(st, b.m1) - 1;
        ctx.fillStyle = ink(dark ? 0.08 : 0.06);
        ctx.strokeStyle = ink(0.24);
        rrect(ctx, x0, y, x1 - x0, 13, 3);
        ctx.fill();
        ctx.stroke();
        if (x1 - x0 > 58) {
          ctx.save();
          ctx.beginPath();
          ctx.rect(x0, y, x1 - x0 - 4, 13);
          ctx.clip();
          text(ctx, b.title, x0 + 6, y + 9.5, ink(0.62), 8.5, "left", 500);
          ctx.restore();
        }
      }
    });

    ctx.restore();

    // Speed gauge.
    const G = st.gauge;
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.strokeStyle = ink(dark ? 0.14 : 0.12);
    ctx.beginPath();
    ctx.arc(G.x, G.y, G.r, 135 * DEG, 405 * DEG);
    ctx.stroke();
    ctx.lineCap = "butt";
    ctx.lineWidth = 1;
    GAUGE_MARKS.forEach((m, i) => {
      const a = 135 * DEG + (270 * DEG * i) / 5;
      const c = Math.cos(a);
      const s = Math.sin(a);
      ctx.strokeStyle = ink(0.4);
      ctx.beginPath();
      ctx.moveTo(G.x + (G.r - 12) * c, G.y + (G.r - 12) * s);
      ctx.lineTo(G.x + (G.r - 7) * c, G.y + (G.r - 7) * s);
      ctx.stroke();
      ctx.font = `500 8.5px ${MONO}`;
      ctx.fillStyle = ink(0.55);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(m), G.x + (G.r + 15) * c, G.y + (G.r + 15) * s);
    });
    text(
      ctx,
      "KABLONET · FİBER İNTERNET",
      G.x,
      G.y - G.r - 28,
      ink(0.75),
      9,
      "center",
      600,
      0.8
    );

    // Cable modem.
    const M = st.M;
    ctx.fillStyle = p.device;
    ctx.strokeStyle = ink(0.55);
    rrect(ctx, M.x, M.y, M.w, M.h, 10);
    ctx.fill();
    ctx.stroke();
    ctx.strokeStyle = ink(0.25);
    for (let i = 0; i < 5; i++) {
      ctx.beginPath();
      ctx.moveTo(M.x + 16, M.y + 12 + i * 3.5);
      ctx.lineTo(M.x + M.w - 16, M.y + 12 + i * 3.5);
      ctx.stroke();
    }
    LEDS.forEach((s, i) => {
      const y = M.y + 42 + i * 22;
      ctx.fillStyle = ink(0.15);
      circle(ctx, M.x + 15, y, 3);
      ctx.fill();
      text(ctx, s, M.x + 24, y + 3, ink(0.7), 8, "left", 600);
    });
    ctx.fillStyle = ink(0.35);
    ctx.fillRect(M.x + M.w - 1, M.y + 170, 5, 10);
    ctx.fillRect(M.x + M.w / 2 - 12, M.y + M.h - 1, 24, 4);
    // KabloSes phone and its coiled cable.
    const Ph = st.phone;
    ctx.strokeStyle = ink(0.5);
    ctx.lineWidth = 1;
    ctx.beginPath();
    const c0: Point = { x: M.x + M.w + 4, y: M.y + 175 };
    const c1: Point = { x: Ph.x - 30, y: Ph.y + 16 };
    for (let i = 0; i <= 80; i++) {
      const s = i / 80;
      const x = c0.x + (c1.x - c0.x) * s;
      const y =
        c0.y +
        (c1.y - c0.y) * s +
        10 * Math.sin(s * Math.PI) +
        3 * Math.sin(s * Math.PI * 22);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
    ctx.fillStyle = p.device;
    ctx.strokeStyle = ink(0.55);
    poly(ctx, [
      { x: Ph.x - 34, y: Ph.y + 28 },
      { x: Ph.x + 34, y: Ph.y + 28 },
      { x: Ph.x + 27, y: Ph.y - 2 },
      { x: Ph.x - 27, y: Ph.y - 2 },
    ]);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = ink(0.45);
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 4; j++) {
        ctx.fillRect(Ph.x - 11 + i * 9, Ph.y + 5 + j * 5.2, 4, 2.6);
      }
    }
    // Shelf.
    ctx.strokeStyle = ink(0.3);
    ctx.beginPath();
    ctx.moveTo(M.x - 14, M.y + M.h + 1);
    ctx.lineTo(Ph.x + 50, M.y + M.h + 1);
    ctx.stroke();

    // TV, console, 4K set-top box, remote.
    const T = st.tv;
    const C = st.con;
    const B = st.box;
    const Rm = st.remote;
    ctx.fillStyle = "#0E1416";
    ctx.strokeStyle = ink(0.5);
    rrect(ctx, T.x, T.y, T.w, T.h, 4);
    ctx.fill();
    ctx.stroke();
    ctx.strokeStyle = ink(0.5);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(B.x + B.w / 2, B.y);
    ctx.lineTo(B.x + B.w / 2, T.y + T.h);
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.fillStyle = ink(dark ? 0.12 : 0.1);
    ctx.strokeStyle = ink(0.4);
    ctx.fillRect(C.x, C.y, C.w, 10);
    ctx.strokeRect(C.x, C.y, C.w, 10);
    ctx.fillStyle = "#101819";
    ctx.strokeStyle = ink(0.55);
    rrect(ctx, B.x, B.y, B.w, B.h, 4);
    ctx.fill();
    ctx.stroke();
    text(
      ctx,
      "4K",
      B.x + B.w - 30,
      B.y + 15,
      "rgba(230,240,238,.7)",
      8,
      "left",
      600
    );
    ctx.save();
    ctx.translate(Rm.x + 17, Rm.y);
    ctx.rotate(-0.08);
    ctx.fillStyle = "#101819";
    ctx.strokeStyle = ink(0.55);
    rrect(ctx, -17, -5, 34, 11, 4);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "rgba(230,240,238,.55)";
    for (let i = 0; i < 4; i++) ctx.fillRect(-10 + i * 6, -1, 2.4, 2.4);
    ctx.restore();

    // Outlet, building entry, and the cable runs between them.
    const O = st.outlet;
    ctx.strokeStyle = hexA(p.fiber, dark ? 0.75 : 0.8);
    ctx.lineWidth = 1.8;
    poly(ctx, st.entry.pts, false);
    ctx.stroke();
    ctx.strokeStyle = hexA(p.copper, dark ? 0.65 : 0.7);
    ctx.lineWidth = 1.6;
    poly(ctx, st.tvLine.pts, false);
    ctx.stroke();
    poly(ctx, st.dataLine.pts, false);
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.fillStyle = p.device;
    ctx.strokeStyle = ink(0.55);
    rrect(ctx, O.x, O.y, O.w, O.h, 5);
    ctx.fill();
    ctx.stroke();
    [st.tvJ, st.dataJ].forEach((j) => {
      ctx.strokeStyle = ink(0.6);
      circle(ctx, j.x, j.y, 7);
      ctx.stroke();
      ctx.fillStyle = hexA(p.copper, 0.9);
      circle(ctx, j.x, j.y, 2.4);
      ctx.fill();
    });
    text(ctx, "TV", O.x - 6, st.tvJ.y + 3, ink(0.65), 8, "right", 600);
    text(ctx, "DATA", O.x - 6, st.dataJ.y + 3, ink(0.65), 8, "right", 600);
    ctx.strokeStyle = ink(0.18);
    ctx.beginPath();
    ctx.moveTo(0, st.floorY + 7);
    ctx.lineTo(env.w, st.floorY + 7);
    ctx.stroke();

    // Service labels.
    text(ctx, "KABLONET", M.x, M.y + M.h + 20, ink(0.8), 9, "left", 600, 1);
    text(ctx, "modem · Wi-Fi", M.x, M.y + M.h + 33, ink(0.5), 8.5, "left", 400);
    text(
      ctx,
      "KABLOSES",
      Ph.x - 34,
      M.y + M.h + 20,
      ink(0.8),
      9,
      "left",
      600,
      1
    );
    text(
      ctx,
      "ev telefonu",
      Ph.x - 34,
      M.y + M.h + 33,
      ink(0.5),
      8.5,
      "left",
      400
    );
    text(ctx, "KABLOTV · 4K KUTU", C.x, C.y + 28, ink(0.8), 9, "left", 600, 1);
    text(ctx, "akıllı kumanda", C.x, C.y + 41, ink(0.5), 8.5, "left", 400);
    text(
      ctx,
      "BİNA GİRİŞİ",
      env.w - 18,
      st.entry.pts[0]!.y - 8,
      hexA(p.fiber, 0.9),
      8.5,
      "right",
      600,
      0.8
    );
    text(
      ctx,
      "PRİZ",
      O.x + O.w / 2,
      O.y + O.h + 16,
      ink(0.7),
      9,
      "center",
      600,
      1
    );
  },

  frame(ctx, env, t, st) {
    const { dark } = env;
    const p = paletteFor("kablo", env.dark);
    const ink = (a: number) => hexA(p.ink, a);
    const nowM = 40 + ((t / 6) % 100);

    // What's live right now on the schedule (pinned to the top edge).
    ctx.save();
    ctx.translate(0, env.top);
    st.epg.forEach((row, i) => {
      const b = row.find((b) => b.m0 <= nowM && nowM < b.m1);
      if (!b) return;
      const y = 24 + i * 17;
      const x0 = epgX(st, b.m0) + 1;
      const x1 = epgX(st, b.m1) - 1;
      ctx.fillStyle = hexA(p.fiber, dark ? 0.2 : 0.16);
      ctx.strokeStyle = hexA(p.fiber, 0.6);
      rrect(ctx, x0, y, x1 - x0, 13, 3);
      ctx.fill();
      ctx.stroke();
    });
    const nx = epgX(st, nowM);
    ctx.strokeStyle = p.red;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(nx, 21);
    ctx.lineTo(nx, 76);
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.fillStyle = p.red;
    poly(ctx, [
      { x: nx - 4, y: 19 },
      { x: nx + 4, y: 19 },
      { x: nx, y: 24 },
    ]);
    ctx.fill();
    text(ctx, "ŞİMDİ", nx, 86, p.red, 8, "center", 600, 1);
    ctx.restore();

    // Speed gauge.
    const G = st.gauge;
    const v = 942 + 22 * Math.sin(t * 0.6) + 10 * Math.sin(t * 1.9 + 1);
    const a = gaugeAngle(v);
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.strokeStyle = hexA(p.fiber, 0.85);
    ctx.beginPath();
    ctx.arc(G.x, G.y, G.r, 135 * DEG, a);
    ctx.stroke();
    ctx.lineCap = "butt";
    ctx.strokeStyle = p.fiber;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(G.x, G.y);
    ctx.lineTo(G.x + (G.r - 16) * Math.cos(a), G.y + (G.r - 16) * Math.sin(a));
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.fillStyle = p.fiber;
    circle(ctx, G.x, G.y, 4);
    ctx.fill();
    text(
      ctx,
      String(Math.round(v)),
      G.x,
      G.y + 34,
      ink(0.92),
      20,
      "center",
      600
    );
    text(ctx, "Mbps · indirme", G.x, G.y + 50, ink(0.55), 9, "center", 400);

    // Wi-Fi.
    const M = st.M;
    const wx = M.x + M.w / 2;
    const wy = M.y - 8;
    for (let i = 0; i < 3; i++) {
      const f = (t * 0.32 + i / 3) % 1;
      ctx.strokeStyle = hexA(p.fiber, 0.6 * (1 - f));
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(wx, wy, 14 + f * 150, -150 * DEG, -30 * DEG);
      ctx.stroke();
    }
    ctx.lineWidth = 1;

    // Modem LEDs and the phone.
    const ring = t % 14 > 9 && t % 14 < 12.2;
    const on = [
      true,
      (t * 9.3) % 1 < 0.7,
      (t * 5.1 + 0.3) % 1 < 0.5,
      true,
      Math.sin(t * 13) > -0.3,
      (t * 7.7 + 0.5) % 1 < 0.6,
      ring ? (t * 4) % 1 < 0.5 : true,
    ];
    on.forEach((o, i) => {
      const y = M.y + 42 + i * 22;
      if (o) {
        ctx.fillStyle = hexA(p.led, 0.25);
        circle(ctx, M.x + 15, y, 5.5);
        ctx.fill();
      }
      ctx.fillStyle = hexA(p.led, o ? 0.95 : 0.15);
      circle(ctx, M.x + 15, y, 2.8);
      ctx.fill();
    });
    const Ph = st.phone;
    const jig = ring ? Math.sin(t * 55) * 1.3 : 0;
    ctx.fillStyle = ink(dark ? 0.75 : 0.7);
    ctx.beginPath();
    ctx.moveTo(Ph.x - 34 + jig, Ph.y - 4);
    ctx.quadraticCurveTo(Ph.x + jig, Ph.y - 20, Ph.x + 34 + jig, Ph.y - 4);
    ctx.lineTo(Ph.x + 29 + jig, Ph.y + 1);
    ctx.quadraticCurveTo(Ph.x + jig, Ph.y - 11, Ph.x - 29 + jig, Ph.y + 1);
    ctx.closePath();
    ctx.fill();
    if (ring) {
      const f = (t * 2.5) % 1;
      ctx.strokeStyle = hexA(p.copper, 0.8 * (1 - f));
      ctx.lineWidth = 1.3;
      ([-1, 1] as const).forEach((sx) => {
        ctx.beginPath();
        ctx.arc(
          Ph.x + sx * 40,
          Ph.y - 14,
          5 + f * 8,
          sx > 0 ? -60 * DEG : 120 * DEG,
          sx > 0 ? 20 * DEG : 200 * DEG
        );
        ctx.stroke();
      });
      ctx.lineWidth = 1;
    }

    // TV screen.
    const T = st.tv;
    const B = st.box;
    const per = 9;
    const ch = 101 + (Math.floor(t / per) % 8);
    const since = t % per;
    // Safe: the modulo always lands within `SCREENS`.
    const pal = SCREENS[(ch - 101) % SCREENS.length]!;
    ctx.save();
    ctx.beginPath();
    ctx.rect(T.x + 5, T.y + 5, T.w - 10, T.h - 10);
    ctx.clip();
    let g = ctx.createLinearGradient(T.x, T.y, T.x + T.w, T.y + T.h);
    g.addColorStop(0, pal[0]);
    g.addColorStop(1, pal[1]);
    ctx.fillStyle = g;
    ctx.fillRect(T.x, T.y, T.w, T.h);
    for (let k = 0; k < 3; k++) {
      const bx = T.x + T.w * (0.3 + 0.35 * Math.sin(t * 0.23 + k * 2.1));
      const by = T.y + T.h * (0.5 + 0.3 * Math.cos(t * 0.31 + k * 1.3));
      g = ctx.createRadialGradient(bx, by, 0, bx, by, 64);
      g.addColorStop(0, hexA(pal[2], 0.55));
      g.addColorStop(1, hexA(pal[2], 0));
      ctx.fillStyle = g;
      ctx.fillRect(T.x, T.y, T.w, T.h);
    }
    if (since < 0.35) {
      ctx.fillStyle = `rgba(255,255,255,${0.5 * (1 - since / 0.35)})`;
      ctx.fillRect(T.x, T.y, T.w, T.h);
    }
    const oa = since < 3 ? 1 : Math.max(0, 1 - (since - 3) / 0.6);
    if (oa > 0) {
      // Safe: `(ch - 101) % 3` always lands within the 3-row `epg`, and
      // each row is built (in `init`) with at least one block.
      const row = st.epg[(ch - 101) % 3]!;
      const prog = row.find((b) => b.m0 <= nowM && nowM < b.m1) || row[0]!;
      const frac = Math.max(
        0,
        Math.min(1, (nowM - prog.m0) / (prog.m1 - prog.m0))
      );
      ctx.fillStyle = `rgba(6,10,12,${0.6 * oa})`;
      ctx.fillRect(T.x + 5, T.y + T.h - 36, T.w - 10, 31);
      text(
        ctx,
        String(ch),
        T.x + 14,
        T.y + T.h - 15,
        `rgba(255,255,255,${oa})`,
        15,
        "left",
        600
      );
      text(
        ctx,
        prog.title,
        T.x + 52,
        T.y + T.h - 21,
        `rgba(255,255,255,${0.9 * oa})`,
        8.5,
        "left",
        500
      );
      ctx.fillStyle = `rgba(255,255,255,${0.25 * oa})`;
      ctx.fillRect(T.x + 52, T.y + T.h - 14, T.w - 68, 2.5);
      ctx.fillStyle = `rgba(255,255,255,${0.85 * oa})`;
      ctx.fillRect(T.x + 52, T.y + T.h - 14, (T.w - 68) * frac, 2.5);
    }
    text(
      ctx,
      "4K",
      T.x + T.w - 12,
      T.y + 19,
      "rgba(255,255,255,.8)",
      9,
      "right",
      600
    );
    ctx.restore();
    text(ctx, String(ch), B.x + 12, B.y + 15, p.fiber, 10, "left", 600);
    ctx.fillStyle = hexA(p.led, 0.9);
    circle(ctx, B.x + B.w - 8, B.y + B.h / 2, 2);
    ctx.fill();
    if (since > per - 0.7) {
      const f = (since - (per - 0.7)) / 0.7;
      const Rm = st.remote;
      ctx.strokeStyle = hexA(p.red, 0.8 * (1 - f));
      ctx.lineWidth = 1.2;
      for (let k = 0; k < 3; k++) {
        ctx.beginPath();
        ctx.arc(Rm.x + 36, Rm.y - 2, 3 + k * 4 + f * 4, -45 * DEG, 45 * DEG);
        ctx.stroke();
      }
      ctx.lineWidth = 1;
    }

    // Flow along the lines: fiber outside, copper inside.
    const dot = (q: Point, col: string, rr: number) => {
      const k = calmAt(env, q.x);
      ctx.fillStyle = hexA(col, 0.2 * k);
      circle(ctx, q.x, q.y, rr * 2.6);
      ctx.fill();
      ctx.fillStyle = hexA(col, 0.95 * k);
      circle(ctx, q.x, q.y, rr);
      ctx.fill();
    };
    for (let k = 0; k < 3; k++)
      dot(along(st.entry, (t * 0.55 + k / 3) % 1), p.fiber, 2.3);
    for (let k = 0; k < 2; k++)
      dot(along(st.tvLine, (t * 0.45 + k / 2) % 1), p.copper, 2);
    for (let k = 0; k < 4; k++)
      dot(along(st.dataLine, (t * 0.16 + k / 4) % 1), p.copper, 2);
    const uq = along(st.dataLine, 1 - ((t * 0.11) % 1));
    ctx.strokeStyle = hexA(p.fiber, 0.85 * calmAt(env, uq.x));
    ctx.lineWidth = 1.2;
    circle(ctx, uq.x, uq.y, 3);
    ctx.stroke();
    ctx.lineWidth = 1;
  },
};
