import React from "react";
import { cn } from "@/lib/utils";

export interface McpProviderListSkeletonProps {
  rowCount?: number;
  className?: string;
}

/** Placeholder for the MCP provider rows on /admin/configuration/mcp. */
export default function McpProviderListSkeleton({
  rowCount = 3,
  className,
}: McpProviderListSkeletonProps) {
  return (
    <div
      className={cn("flex flex-col divide-y divide-border-01", className)}
      role="status"
      aria-label="Loading providers..."
      data-testid="mcp-provider-list-skeleton"
    >
      {Array.from({ length: rowCount }).map((_, index) => (
        <div
          key={index}
          data-testid="mcp-provider-skeleton-row"
          className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex min-w-0 items-start gap-3">
            <div className="h-10 w-10 shrink-0 rounded-08 bg-background-tint-02 animate-pulse" />
            <div className="flex min-w-0 flex-col gap-1.5">
              <div className="h-4 w-40 rounded bg-background-tint-02 animate-pulse" />
              <div className="h-3 w-64 max-w-full rounded bg-background-tint-02 animate-pulse opacity-70" />
              <div className="h-3 w-48 max-w-full rounded bg-background-tint-02 animate-pulse opacity-50" />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="h-9 w-20 rounded-08 bg-background-tint-02 animate-pulse" />
            <div className="h-9 w-20 rounded-08 bg-background-tint-02 animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}
