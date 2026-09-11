import React from "react";
import { cn } from "@/lib/utils";

export interface ChartSkeletonProps {
  className?: string;
  height?: string;
  barCount?: number;
}

const BAR_HEIGHTS = [
  "45%",
  "75%",
  "35%",
  "90%",
  "60%",
  "40%",
  "85%",
  "55%",
  "70%",
  "50%",
];

export default function ChartSkeleton({
  className,
  height = "h-72",
  barCount = 8,
}: ChartSkeletonProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4 rounded-08 border border-border-01 bg-background-neutral-00 p-5 shadow-01 w-full",
        className
      )}
      role="status"
      aria-label="Loading chart..."
    >
      {/* Chart Title and Legend */}
      <div className="flex items-center justify-between pb-2 border-b border-border-01/60">
        <div className="flex flex-col gap-1.5">
          <div className="h-4 w-36 rounded bg-background-tint-02 animate-pulse" />
          <div className="h-3 w-56 rounded bg-background-tint-02 animate-pulse opacity-70" />
        </div>
        <div className="flex items-center gap-3">
          <div className="h-3.5 w-16 rounded bg-background-tint-02 animate-pulse" />
          <div className="h-3.5 w-16 rounded bg-background-tint-02 animate-pulse" />
        </div>
      </div>

      {/* Chart Canvas Simulation */}
      <div
        className={cn(
          "relative flex items-end justify-between gap-3 pt-6 pb-4 px-2 w-full",
          height
        )}
      >
        {/* Horizontal grid lines */}
        <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20">
          <div className="border-b border-border-01 w-full" />
          <div className="border-b border-border-01 w-full" />
          <div className="border-b border-border-01 w-full" />
          <div className="border-b border-border-01 w-full" />
        </div>

        {/* Pulse Bars */}
        {Array.from({ length: barCount }).map((_, index) => {
          const h = BAR_HEIGHTS[index % BAR_HEIGHTS.length];
          return (
            <div
              key={index}
              className="flex-1 flex flex-col items-center gap-2 h-full justify-end z-10"
            >
              <div
                className="w-full max-w-[40px] rounded-t-04 bg-background-tint-02 animate-pulse"
                style={{ height: h }}
              />
              <div className="h-2.5 w-6 rounded bg-background-tint-02 animate-pulse opacity-60 shrink-0" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
