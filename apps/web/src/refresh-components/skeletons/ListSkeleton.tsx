import React from "react";
import { cn } from "@/lib/utils";

export interface ListSkeletonProps {
  itemCount?: number;
  className?: string;
  hasIcon?: boolean;
}

export default function ListSkeleton({
  itemCount = 5,
  className,
  hasIcon = true,
}: ListSkeletonProps) {
  return (
    <div
      className={cn("flex flex-col gap-2 w-full", className)}
      role="status"
      aria-label="Loading list..."
    >
      {Array.from({ length: itemCount }).map((_, index) => (
        <div
          key={index}
          className="flex items-center justify-between rounded-08 border border-border-01 bg-background-neutral-00 p-3.5"
        >
          <div className="flex items-center gap-3 min-w-0 flex-1">
            {hasIcon && (
              <div className="h-8 w-8 shrink-0 rounded-08 bg-background-tint-02 animate-pulse" />
            )}
            <div className="flex flex-col gap-1.5 flex-1 min-w-0">
              <div className="h-3.5 w-1/3 rounded bg-background-tint-02 animate-pulse" />
              <div className="h-3 w-2/3 rounded bg-background-tint-02 animate-pulse opacity-70" />
            </div>
          </div>
          <div className="h-6 w-16 rounded-full bg-background-tint-02 animate-pulse shrink-0 ml-4" />
        </div>
      ))}
    </div>
  );
}
