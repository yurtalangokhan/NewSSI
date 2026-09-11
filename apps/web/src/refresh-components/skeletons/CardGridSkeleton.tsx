import React from "react";
import { cn } from "@/lib/utils";

export interface CardGridSkeletonProps {
  cardCount?: number;
  columnsClassName?: string;
  className?: string;
  hasFooter?: boolean;
}

export default function CardGridSkeleton({
  cardCount = 6,
  columnsClassName = "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  className,
  hasFooter = true,
}: CardGridSkeletonProps) {
  return (
    <div
      className={cn("grid gap-4 w-full", columnsClassName, className)}
      role="status"
      aria-label="Loading cards..."
    >
      {Array.from({ length: cardCount }).map((_, index) => (
        <div
          key={index}
          className="flex flex-col justify-between rounded-12 border border-border-01 bg-background-neutral-00 p-4 shadow-01"
        >
          <div className="flex flex-col gap-3">
            {/* Header: Icon + Title */}
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 shrink-0 rounded-08 bg-background-tint-02 animate-pulse" />
              <div className="flex flex-col gap-1.5 flex-1 min-w-0">
                <div className="h-4 w-2/3 rounded bg-background-tint-02 animate-pulse" />
                <div className="h-3 w-1/3 rounded bg-background-tint-02 animate-pulse opacity-75" />
              </div>
            </div>

            {/* Description lines */}
            <div className="flex flex-col gap-2 mt-1">
              <div className="h-3 w-full rounded bg-background-tint-02 animate-pulse" />
              <div className="h-3 w-4/5 rounded bg-background-tint-02 animate-pulse" />
            </div>
          </div>

          {/* Optional Footer */}
          {hasFooter && (
            <div className="flex items-center justify-between pt-4 mt-3 border-t border-border-01/60">
              <div className="h-5 w-20 rounded-full bg-background-tint-02 animate-pulse" />
              <div className="h-7 w-16 rounded-08 bg-background-tint-02 animate-pulse" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
