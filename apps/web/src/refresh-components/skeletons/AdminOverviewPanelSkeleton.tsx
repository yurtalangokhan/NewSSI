import React from "react";
import { cn } from "@/lib/utils";

export interface AdminOverviewPanelSkeletonProps {
  metricsCount?: number;
  className?: string;
}

export default function AdminOverviewPanelSkeleton({
  metricsCount = 3,
  className,
}: AdminOverviewPanelSkeletonProps) {
  return (
    <section
      className={cn(
        "rounded-08 border border-border-01 bg-background-neutral-00 p-4 shadow-01",
        className
      )}
      role="status"
      aria-label="Loading overview..."
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-3 items-start">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-01">
            <div className="h-5 w-5 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <div className="h-5 w-44 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3.5 w-64 sm:w-96 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
        </div>
      </div>

      {metricsCount > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {Array.from({ length: metricsCount }).map((_, index) => (
            <div
              key={index}
              className="min-w-[160px] flex-1 rounded-08 border border-border-01 bg-background-neutral-01 px-3 py-2.5 flex flex-col justify-center min-h-[4.25rem]"
            >
              <div className="h-3 w-20 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
              <div className="mt-2 h-6 w-16 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
