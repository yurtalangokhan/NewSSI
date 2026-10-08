"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { BackgroundRunner } from "@/lib/turksatBackgrounds/runner";
import type {
  TurksatCompany,
  TurksatMode,
} from "@/lib/turksatBackgrounds/types";

export interface TurksatBackgroundCanvasProps {
  company: TurksatCompany;
  mode: TurksatMode;
  /** `false` renders one static frame instead of animating — used for the
   * settings picker's thumbnails, where a live loop per tile would be
   * wasted work. Defaults to `true`. */
  animate?: boolean;
  className?: string;
}

/**
 * Renders one TÜRKSAT animated background scene into a `<canvas>` that fills
 * its parent. Pure rendering: it takes no interaction and reports no state
 * back up — callers own layout and any readability overlay drawn on top of
 * it (see `layouts/app-layouts.tsx` and `app/nrf/NRFPage.tsx`).
 *
 * Animation, resize, and lifecycle handling (the rAF loop, reduced motion,
 * pausing when hidden or off-screen, canvas-context loss) live in
 * `BackgroundRunner`, so both mounting surfaces and the settings thumbnail
 * picker share one implementation and one set of guarantees.
 */
export function TurksatBackgroundCanvas({
  company,
  mode,
  animate = true,
  className,
}: TurksatBackgroundCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const runner = new BackgroundRunner(canvas, {
      company,
      dark: mode === "dark",
      animate,
    });
    runner.start();
    return () => runner.dispose();
  }, [company, mode, animate]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn("block h-full w-full object-cover", className)}
    />
  );
}
