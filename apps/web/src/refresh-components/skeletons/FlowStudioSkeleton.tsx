import React from "react";
import { cn } from "@/lib/utils";

export interface FlowStudioSkeletonProps {
  className?: string;
  isInline?: boolean;
}

export function FlowStudioSkeleton({
  className,
  isInline = false,
}: FlowStudioSkeletonProps) {
  return (
    <div
      className={cn(
        "langflow-canvas flex flex-col overflow-hidden bg-canvas-panel text-canvas-fg select-none",
        isInline
          ? "h-[36rem] w-full rounded-12 border border-border-01"
          : "h-screen w-screen",
        className
      )}
      role="status"
      aria-label="Loading flow canvas..."
    >
      {/* ── Top Bar (VersionBar) ── */}
      <div className="flex h-12 w-full shrink-0 items-center justify-between border-b border-canvas-border bg-canvas-panel px-4">
        <div className="flex items-center gap-3">
          {/* Back/Exit button */}
          <div className="h-8 w-8 rounded-08 bg-muted animate-pulse shrink-0" />
          {/* Agent Avatar & Name */}
          <div className="flex items-center gap-2 px-1.5 py-1">
            <div className="h-6 w-6 rounded-full bg-muted animate-pulse shrink-0" />
            <div className="h-4 w-28 rounded bg-muted animate-pulse" />
          </div>
          {/* Status Chip */}
          <div className="h-4 w-16 rounded-full bg-muted animate-pulse" />
        </div>

        {/* Right action buttons */}
        <div className="flex items-center gap-2">
          {/* History */}
          <div className="h-8 w-8 rounded-08 bg-muted animate-pulse" />
          {/* Playground */}
          <div className="h-8 w-24 rounded-08 bg-muted animate-pulse hidden sm:block" />
          {/* Import */}
          <div className="h-8 w-8 rounded-08 bg-muted animate-pulse" />
          {/* Publish */}
          <div className="h-8 w-20 rounded-08 bg-muted animate-pulse" />
        </div>
      </div>

      {/* ── Workspace Body: Sidebar + Canvas ── */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {/* Component Palette / Sidebar */}
        <div className="hidden md:flex w-64 shrink-0 flex-col gap-3 border-r border-canvas-border bg-canvas-panel p-2">
          {/* Search bar */}
          <div className="h-8 w-full rounded-lg bg-muted animate-pulse" />
          {/* Components Header */}
          <div className="flex items-center justify-between px-2 pt-1">
            <div className="h-4 w-24 rounded bg-muted animate-pulse" />
            <div className="h-5 w-5 rounded bg-muted animate-pulse" />
          </div>
          {/* Category Sections */}
          <div className="flex flex-col gap-2.5 pt-1">
            {[
              { labelW: "w-20", items: ["w-28", "w-32"] },
              { labelW: "w-24", items: ["w-36", "w-28"] },
              { labelW: "w-16", items: ["w-24"] },
              { labelW: "w-28", items: ["w-32", "w-28"] },
              { labelW: "w-20", items: ["w-30"] },
            ].map((cat, idx) => (
              <div key={idx} className="flex flex-col gap-1.5 px-1">
                <div className="flex items-center gap-2 py-1">
                  <div className="h-4 w-4 rounded bg-muted animate-pulse shrink-0" />
                  <div
                    className={`h-3.5 ${cat.labelW} rounded bg-muted animate-pulse`}
                  />
                  <div className="flex-1" />
                  <div className="h-3 w-3 rounded bg-muted animate-pulse" />
                </div>
                <div className="flex flex-col gap-1 pl-6">
                  {cat.items.map((itemW, iIdx) => (
                    <div
                      key={iIdx}
                      className={`h-6 ${itemW} rounded border border-canvas-border/40 bg-muted/40 animate-pulse`}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Canvas Surface with Grid and Sample Nodes */}
        <div className="relative flex-1 bg-background-neutral-01 overflow-hidden">
          {/* Dot grid simulation */}
          <div
            className="absolute inset-0 opacity-20 pointer-events-none"
            style={{
              backgroundImage:
                "radial-gradient(circle, currentColor 1px, transparent 1px)",
              backgroundSize: "20px 20px",
            }}
          />

          {/* Simulated Flow Nodes on Canvas */}
          <div className="absolute inset-0 p-8 flex items-center justify-around pointer-events-none opacity-80">
            {/* Node 1: Chat Input */}
            <div className="w-64 rounded-12 border border-canvas-border bg-canvas-panel shadow-md flex flex-col overflow-hidden animate-pulse">
              <div className="h-9 bg-muted px-3 flex items-center justify-between border-b border-canvas-border">
                <div className="flex items-center gap-2">
                  <div className="h-4 w-4 rounded bg-background-tint-03" />
                  <div className="h-3.5 w-24 rounded bg-background-tint-03" />
                </div>
                <div className="h-2.5 w-2.5 rounded-full bg-status-success-02" />
              </div>
              <div className="p-3 flex flex-col gap-2">
                <div className="h-3 w-20 rounded bg-muted" />
                <div className="h-8 w-full rounded bg-muted/60" />
              </div>
            </div>

            {/* Connecting Edge */}
            <div className="hidden lg:flex items-center">
              <div className="h-0.5 w-16 bg-muted animate-pulse" />
            </div>

            {/* Node 2: Agent / LLM */}
            <div className="w-72 rounded-12 border border-canvas-border bg-canvas-panel shadow-md flex flex-col overflow-hidden animate-pulse">
              <div className="h-9 bg-muted px-3 flex items-center justify-between border-b border-canvas-border">
                <div className="flex items-center gap-2">
                  <div className="h-4 w-4 rounded bg-background-tint-03" />
                  <div className="h-3.5 w-28 rounded bg-background-tint-03" />
                </div>
                <div className="h-2.5 w-2.5 rounded-full bg-status-success-02" />
              </div>
              <div className="p-3 flex flex-col gap-2.5">
                <div className="h-3 w-24 rounded bg-muted" />
                <div className="h-7 w-full rounded bg-muted/60" />
                <div className="h-3 w-20 rounded bg-muted" />
                <div className="h-7 w-full rounded bg-muted/60" />
              </div>
            </div>

            {/* Connecting Edge */}
            <div className="hidden lg:flex items-center">
              <div className="h-0.5 w-16 bg-muted animate-pulse" />
            </div>

            {/* Node 3: Chat Output */}
            <div className="w-64 rounded-12 border border-canvas-border bg-canvas-panel shadow-md flex flex-col overflow-hidden animate-pulse">
              <div className="h-9 bg-muted px-3 flex items-center justify-between border-b border-canvas-border">
                <div className="flex items-center gap-2">
                  <div className="h-4 w-4 rounded bg-background-tint-03" />
                  <div className="h-3.5 w-24 rounded bg-background-tint-03" />
                </div>
                <div className="h-2.5 w-2.5 rounded-full bg-status-success-02" />
              </div>
              <div className="p-3 flex flex-col gap-2">
                <div className="h-3 w-20 rounded bg-muted" />
                <div className="h-8 w-full rounded bg-muted/60" />
              </div>
            </div>
          </div>

          {/* Bottom Canvas Controls Skeleton */}
          <div className="absolute bottom-4 left-4 z-10 flex items-center gap-1.5 rounded-lg border border-canvas-border bg-canvas-panel p-1 shadow-sm">
            <div className="h-7 w-7 rounded bg-muted animate-pulse" />
            <div className="h-7 w-7 rounded bg-muted animate-pulse" />
            <div className="h-7 w-7 rounded bg-muted animate-pulse" />
            <div className="h-7 w-7 rounded bg-muted animate-pulse" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function InlineFlowDesignerSkeleton({
  className,
}: {
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2 w-full", className)}>
      {/* Notice Banner Skeleton */}
      <div className="flex w-full items-center justify-between rounded-12 border border-border-01 bg-background-neutral-01 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
          <div className="flex flex-col gap-1">
            <div className="h-3.5 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3 w-72 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
          </div>
        </div>
      </div>
      {/* Canvas Skeleton */}
      <FlowStudioSkeleton isInline />
    </div>
  );
}

export default FlowStudioSkeleton;
