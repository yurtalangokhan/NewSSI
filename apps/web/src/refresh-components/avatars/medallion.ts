/**
 * Pure geometry for the "Transponder" avatar medallion. A name maps
 * deterministically to a hue, a satellite count and their positions, so every
 * agent reads as the same family but distinct. No React here.
 */

export const TRANSPONDER_PALETTE = [
  "#009BDA", // Türksat cyan — the default
  "#3B6FE0",
  "#0FA5A5",
  "#5A54D6",
  "#8A49C9",
  "#4C7A96",
] as const;

/** FNV-1a over UTF-16 code units. Deterministic, unsigned 32-bit. */
export function hashName(name: string): number {
  const seed = name.trim() || "Agent";
  let h = 2166136261 >>> 0;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

export interface MedallionPoint {
  x: number;
  y: number;
}

export interface MedallionGeometry {
  accent: string;
  /** satellites, 3–5 */
  count: number;
  /** index into `points` of the lead satellite */
  primaryIndex: number;
  /** satellite centres in the 48×48 viewBox, orbit order */
  points: MedallionPoint[];
  /** flow only: `points` sorted by angle for the open path; [] for agents */
  pathPoints: MedallionPoint[];
  /** flow only: 2-segment arrowhead `d` at the last path point; "" for agents */
  arrowD: string;
}

const VIEW = 48;
const CENTER = VIEW / 2;
const ORBIT_R = 14;
const ARROW_BARB = 3.2;

const round2 = (n: number): number => Math.round(n * 100) / 100;

export function deriveMedallion(
  name: string,
  variant: "agent" | "flow"
): MedallionGeometry {
  const h = hashName(name);
  const accent = TRANSPONDER_PALETTE[h % TRANSPONDER_PALETTE.length]!;
  const count = 3 + (Math.floor(h / 8) % 3);
  const baseAngle = Math.floor(h / 64) % 360;
  const primaryIndex = h % count;

  const points: MedallionPoint[] = Array.from({ length: count }, (_, i) => {
    const jitter = ((h >>> (i * 3)) % 15) - 7;
    const rad = ((baseAngle + i * (360 / count) + jitter) * Math.PI) / 180;
    return {
      x: round2(CENTER + ORBIT_R * Math.cos(rad)),
      y: round2(CENTER + ORBIT_R * Math.sin(rad)),
    };
  });

  if (variant !== "flow") {
    return { accent, count, primaryIndex, points, pathPoints: [], arrowD: "" };
  }

  const pathPoints = [...points].sort(
    (a, b) =>
      Math.atan2(a.y - CENTER, a.x - CENTER) -
      Math.atan2(b.y - CENTER, b.x - CENTER)
  );
  const last = pathPoints[pathPoints.length - 1]!;
  const prev = pathPoints[pathPoints.length - 2] ?? last;
  const ang = Math.atan2(last.y - prev.y, last.x - prev.x);
  const arrowD =
    `M${last.x} ${last.y} ` +
    `l${round2(-ARROW_BARB * Math.cos(ang - 0.5))} ${round2(
      -ARROW_BARB * Math.sin(ang - 0.5)
    )} ` +
    `M${last.x} ${last.y} ` +
    `l${round2(-ARROW_BARB * Math.cos(ang + 0.5))} ${round2(
      -ARROW_BARB * Math.sin(ang + 0.5)
    )}`;

  return { accent, count, primaryIndex, points, pathPoints, arrowD };
}
