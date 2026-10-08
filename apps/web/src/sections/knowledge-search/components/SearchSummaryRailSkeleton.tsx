"use client";

import Skeleton from "@/refresh-components/skeletons/Skeleton";

const PLACEHOLDER_ROWS = [0, 1, 2, 3];

/**
 * Placeholder for the summary rail while the first search runs. It mirrors the
 * rail's blocks so the right column keeps its shape instead of opening up as
 * empty space. Purely decorative: `ResultListSkeleton` owns the "searching"
 * announcement, so this stays out of the accessibility tree.
 */
export default function SearchSummaryRailSkeleton() {
  return (
    <div
      aria-hidden
      data-testid="knowledge-search-rail-skeleton"
      className="flex min-w-0 flex-col gap-6"
    >
      <div className="flex flex-col gap-2.5 border-b border-border-01 pb-5">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton variant="pill" className="h-1.5 w-full" />
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {[0, 1].map((legend) => (
            <span key={legend} className="flex items-center gap-1.5">
              <Skeleton variant="circular" className="h-2 w-2" />
              <Skeleton className="h-3.5 w-24" />
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Skeleton className="h-3.5 w-28" />
        {PLACEHOLDER_ROWS.map((row) => (
          <div
            key={row}
            className="flex items-center gap-2.5 rounded-12 border border-border-01 bg-background-neutral-01 px-2.5 py-2"
          >
            <Skeleton className="h-7 w-7 shrink-0" />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <Skeleton className="h-3.5 w-1/2" />
              <Skeleton className="h-3 w-2/3" />
            </div>
            <Skeleton className="h-3.5 w-6 shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}
