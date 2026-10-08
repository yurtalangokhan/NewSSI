import React from "react";
import { cn } from "@/lib/utils";

export interface AppSidebarContentSkeletonProps {
  folded?: boolean;
  includeActionButtons?: boolean;
}

export function AppSidebarActionButtonsSkeleton() {
  return (
    <div
      className="flex flex-col gap-0.5 w-full"
      role="status"
      aria-label="Loading action buttons..."
    >
      {/* Yeni Oturum */}
      <div className="flex items-center gap-2.5 px-3 py-2 w-full rounded-08">
        <div className="h-4 w-4 rounded bg-background-tint-03 animate-pulse shrink-0" />
        <div className="h-3.5 w-24 rounded bg-background-tint-03 animate-pulse" />
      </div>
      {/* Sohbet Ara */}
      <div className="flex items-center gap-2.5 px-3 py-2 w-full rounded-08">
        <div className="h-4 w-4 rounded bg-background-tint-03 animate-pulse shrink-0" />
        <div className="h-3.5 w-20 rounded bg-background-tint-03 animate-pulse" />
      </div>
    </div>
  );
}

export default function AppSidebarContentSkeleton({
  folded = false,
  includeActionButtons = false,
}: AppSidebarContentSkeletonProps) {
  if (folded) {
    return (
      <div
        className="flex flex-col w-full gap-2 items-center py-2"
        role="status"
        aria-label="Loading sidebar content..."
      >
        {Array.from({ length: 8 }).map((_, index) => (
          <div
            key={index}
            className="h-8 w-8 rounded-08 bg-background-tint-03 animate-pulse flex items-center justify-center"
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className="flex flex-col w-full gap-5 py-2"
      role="status"
      aria-label="Loading sidebar content..."
    >
      {includeActionButtons && <AppSidebarActionButtonsSkeleton />}

      {/* Agents Section */}
      <div className="flex flex-col gap-1 w-full">
        <div className="px-3 mb-1">
          <div className="h-3 w-20 rounded bg-background-tint-04 animate-pulse" />
        </div>
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-2.5 px-3 py-2 w-full rounded-08"
          >
            <div className="h-4 w-4 rounded-full bg-background-tint-03 animate-pulse shrink-0" />
            <div
              className={cn(
                "h-3.5 rounded bg-background-tint-03 animate-pulse",
                index === 0 ? "w-28" : index === 1 ? "w-24" : "w-32"
              )}
            />
          </div>
        ))}
      </div>

      {/* Projects Section */}
      <div className="flex flex-col gap-1 w-full">
        <div className="px-3 mb-1">
          <div className="h-3 w-20 rounded bg-background-tint-04 animate-pulse" />
        </div>
        {Array.from({ length: 2 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-2.5 px-3 py-2 w-full rounded-08"
          >
            <div className="h-4 w-4 rounded bg-background-tint-03 animate-pulse shrink-0" />
            <div
              className={cn(
                "h-3.5 rounded bg-background-tint-03 animate-pulse",
                index === 0 ? "w-32" : "w-24"
              )}
            />
          </div>
        ))}
      </div>

      {/* Recents Section - chats have no leading icon */}
      <div className="flex flex-col gap-1 w-full">
        <div className="px-3 mb-1">
          <div className="h-3 w-24 rounded bg-background-tint-04 animate-pulse" />
        </div>
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center px-3 py-2 w-full rounded-08"
          >
            <div
              className={cn(
                "h-3.5 rounded bg-background-tint-03 animate-pulse",
                index % 4 === 0
                  ? "w-44"
                  : index % 4 === 1
                    ? "w-36"
                    : index % 4 === 2
                      ? "w-40"
                      : "w-28"
              )}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
