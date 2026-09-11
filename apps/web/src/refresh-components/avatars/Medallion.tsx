"use client";

import { cn } from "@/lib/utils";
import {
  deriveMedallion,
  hashName,
} from "@/refresh-components/avatars/medallion";

/** One Türksat parallelogram arm, in the 48×48 box (16-box coords × 3). */
const ARM = "M19.48 4.42 L28.52 4.42 L27.62 13.51 L22.65 12.98 Z";
const SIMPLIFY_BELOW_PX = 22;

export interface MedallionProps {
  name: string;
  variant: "agent" | "flow";
  size: number;
}

const r2 = (n: number): number => Math.round(n * 100) / 100;

/**
 * The "Transponder" avatar frame: a layered Türksat medallion drawn behind the
 * centered letter/glyph. Hue, satellite count and satellite positions come from
 * `name` (see {@link deriveMedallion}). Below {@link SIMPLIFY_BELOW_PX} only the
 * disc, rim, lead satellite and letter are drawn and nothing animates.
 */
export default function Medallion({ name, variant, size }: MedallionProps) {
  const { accent, primaryIndex, points, pathPoints, arrowD } = deriveMedallion(
    name,
    variant
  );
  const simplified = size < SIMPLIFY_BELOW_PX;
  const isFlow = variant === "flow";
  const id = `tr-${hashName(name)}-${variant}`;

  const discPath = isFlow ? (
    <rect x={2} y={2} width={44} height={44} rx={13} />
  ) : (
    <circle cx={24} cy={24} r={22} />
  );

  const rim = isFlow ? (
    <rect
      x={2}
      y={2}
      width={44}
      height={44}
      rx={13}
      fill="none"
      stroke={accent}
      strokeOpacity={0.55}
      strokeWidth={1.3}
    />
  ) : (
    <circle
      cx={24}
      cy={24}
      r={22}
      fill="none"
      stroke={accent}
      strokeOpacity={0.55}
      strokeWidth={1.3}
    />
  );

  const ticks = Array.from({ length: 12 }, (_, k) => {
    const a = (k * 30 * Math.PI) / 180;
    return (
      <line
        key={k}
        x1={r2(24 + 17 * Math.cos(a))}
        y1={r2(24 + 17 * Math.sin(a))}
        x2={r2(24 + 19 * Math.cos(a))}
        y2={r2(24 + 19 * Math.sin(a))}
      />
    );
  });

  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      width={size}
      height={size}
      aria-hidden="true"
      className="absolute inset-0"
    >
      <defs>
        <radialGradient id={`${id}-g`} cx="34%" cy="28%" r="80%">
          <stop offset="0" stopColor={accent} stopOpacity={0.22} />
          <stop offset="1" stopColor={accent} stopOpacity={0.05} />
        </radialGradient>
        <clipPath id={`${id}-c`}>{discPath}</clipPath>
      </defs>

      {/* 1 — depth disc */}
      <g clipPath={`url(#${id}-c)`}>
        {isFlow ? (
          <rect
            x={2}
            y={2}
            width={44}
            height={44}
            rx={13}
            fill={`url(#${id}-g)`}
          />
        ) : (
          <circle cx={24} cy={24} r={22} fill={`url(#${id}-g)`} />
        )}
        <path
          d="M3.33 16.48 A22 22 0 0 1 31.52 3.33"
          stroke="#ffffff"
          strokeOpacity={0.32}
          strokeWidth={1.4}
          strokeLinecap="round"
        />
        <path
          d="M44.67 31.52 A22 22 0 0 1 16.48 44.67"
          stroke="#04121d"
          strokeOpacity={0.18}
          strokeWidth={1.6}
          strokeLinecap="round"
        />
      </g>

      {/* 2 — rim */}
      {rim}

      {!simplified && (
        <>
          {/* 3 — bezel + degree ticks */}
          <circle
            data-part="bezel"
            cx={24}
            cy={24}
            r={18}
            fill="none"
            stroke={accent}
            strokeOpacity={0.3}
            strokeWidth={1}
          />
          <g
            stroke={accent}
            strokeOpacity={0.3}
            strokeWidth={1}
            strokeLinecap="round"
          >
            {ticks}
          </g>

          {/* 5 — Türksat arm mark, behind the letter */}
          <g
            data-part="arm"
            transform="translate(24 24) scale(0.46) translate(-24 -24)"
            fill={accent}
            fillOpacity={0.1}
          >
            <path d={ARM} />
            <path d={ARM} transform="rotate(120 24 24)" />
            <path d={ARM} transform="rotate(240 24 24)" />
          </g>
        </>
      )}

      {/* 4 — constellation */}
      <g
        data-part="constellation"
        className={cn(
          // rotate about the medallion centre (viewBox units), not the
          // constellation's own eccentric bounding box
          "[transform-box:view-box] [transform-origin:24px_24px]",
          !simplified && "motion-safe:animate-transponder-orbit"
        )}
      >
        {!simplified && !isFlow && (
          <polygon
            points={points.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke={accent}
            strokeOpacity={0.28}
            strokeWidth={1}
          />
        )}

        {!simplified && isFlow && (
          <>
            <path
              data-part="flowpath"
              d={`M${pathPoints.map((p) => `${p.x} ${p.y}`).join(" L")}`}
              fill="none"
              stroke={accent}
              strokeOpacity={0.6}
              strokeWidth={1.2}
              strokeLinecap="round"
              style={{ strokeDasharray: "3 3.4" }}
              className="motion-safe:animate-transponder-flow"
            />
            <path
              d={arrowD}
              stroke={accent}
              strokeWidth={1.2}
              strokeLinecap="round"
            />
          </>
        )}

        {points.map((p, i) => {
          if (
            simplified &&
            i !== primaryIndex &&
            i !== (primaryIndex + 1) % points.length
          ) {
            return null;
          }
          return i === primaryIndex ? (
            <circle
              key={i}
              data-part="primary"
              cx={p.x}
              cy={p.y}
              r={2.7}
              fill={accent}
              className={cn(
                "[transform-box:fill-box] [transform-origin:50%_50%]",
                !simplified && "motion-safe:animate-transponder-pulse"
              )}
            />
          ) : (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={1.6}
              fill={accent}
              fillOpacity={0.85}
            />
          );
        })}
      </g>
    </svg>
  );
}
