import React from "react";
import { cn } from "@/lib/utils";

export interface AdminSidebarSkeletonProps {
  folded?: boolean;
  sectionCount?: number;
}

export default function AdminSidebarSkeleton({
  folded = false,
  sectionCount = 4,
}: AdminSidebarSkeletonProps) {
  if (folded) {
    return (
      <div
        className="flex flex-col w-full gap-2 items-center py-2"
        role="status"
        aria-label="Loading navigation..."
      >
        {Array.from({ length: 8 }).map((_, index) => (
          <div
            key={index}
            className="h-8 w-8 rounded-08 bg-background-tint-02 animate-pulse flex items-center justify-center"
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className="flex flex-col w-full gap-5 py-2"
      role="status"
      aria-label="Loading navigation..."
    >
      {Array.from({ length: sectionCount }).map((_, sectionIndex) => (
        <div key={sectionIndex} className="flex flex-col gap-1 w-full">
          {/* Section title */}
          <div className="px-3 mb-1">
            <div className="h-3 w-24 rounded bg-background-tint-04 animate-pulse" />
          </div>

          {/* 2-3 tab items per section */}
          {Array.from({ length: sectionIndex % 2 === 0 ? 3 : 2 }).map(
            (_, itemIndex) => (
              <div
                key={itemIndex}
                className="flex items-center gap-2.5 px-3 py-2 w-full rounded-08"
              >
                <div className="h-4 w-4 rounded bg-background-tint-03 animate-pulse shrink-0" />
                <div
                  className={cn(
                    "h-3.5 rounded bg-background-tint-03 animate-pulse",
                    itemIndex === 0 ? "w-32" : itemIndex === 1 ? "w-24" : "w-28"
                  )}
                />
              </div>
            )
          )}
        </div>
      ))}
    </div>
  );
}
