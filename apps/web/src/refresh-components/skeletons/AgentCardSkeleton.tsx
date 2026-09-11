import React from "react";
import { cn } from "@/lib/utils";

export function AgentCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-08 border border-border-01 bg-background-neutral-00 overflow-hidden flex flex-col justify-between shadow-00",
        className
      )}
      role="status"
      aria-label="Loading agent..."
    >
      {/* Top section: Avatar + Title + Description */}
      <div className="flex items-start gap-3 p-4 h-[6rem]">
        <div className="h-10 w-10 shrink-0 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
        <div className="flex flex-col gap-2 flex-1 min-w-0">
          <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          <div className="h-3 w-56 max-w-full rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-75" />
        </div>
      </div>

      {/* Footer section: matches bg-background-tint-01 of real AgentCard */}
      <div className="bg-background-tint-01 p-2 flex flex-row items-end justify-between border-t border-border-01/40">
        <div className="flex flex-col gap-1.5 py-1 px-2">
          {/* Availability badge */}
          <div className="h-4 w-20 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          {/* Creator / actions info lines */}
          <div className="flex items-center gap-1.5">
            <div className="h-3 w-3 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3 w-28 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-3 w-3 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3 w-20 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
        </div>

        {/* Start Chat Button Skeleton */}
        <div className="p-0.5">
          <div className="h-8 w-28 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
        </div>
      </div>
    </div>
  );
}

export function AgentsGridSkeleton({
  count = 4,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      className={cn("grid grid-cols-1 md:grid-cols-2 gap-2 w-full", className)}
    >
      {Array.from({ length: count }).map((_, i) => (
        <AgentCardSkeleton key={i} />
      ))}
    </div>
  );
}

export default AgentCardSkeleton;
