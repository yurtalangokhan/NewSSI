"use client";

import { DocumentPreviewPlaceholder } from "@/sections/document-panel/DocumentPreviewPlaceholder";
import { cn } from "@/lib/utils";

/** Placeholder widths for the tab strip (Preview · Changes · Compare · History). */
const TAB_WIDTHS = ["w-16", "w-24", "w-20", "w-14"];

/**
 * Placeholder for the document panel while its metadata loads: the panel would
 * otherwise open as an empty pulsing rectangle. Header, tab strip and paper
 * keep the layout the loaded panel snaps into.
 */
export function DocumentPanelSkeleton() {
  return (
    <div
      className="flex flex-col h-full min-h-0"
      data-testid="document-panel-skeleton"
      role="status"
      aria-label="Loading document panel..."
    >
      {/* Header: file icon + title/meta + window controls, then the draft
          switcher and the action group. */}
      <div className="flex flex-col gap-2 px-3 py-2 border-b border-border-01">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 shrink-0 rounded-08 bg-background-tint-02 animate-pulse" />
          <div className="flex flex-col gap-1.5 flex-1 min-w-0">
            <div className="h-3.5 w-2/5 rounded bg-background-tint-02 animate-pulse" />
            <div className="h-3 w-3/5 rounded bg-background-tint-02 animate-pulse opacity-70" />
          </div>
          <div className="h-7 w-7 shrink-0 rounded-08 bg-background-tint-02 animate-pulse" />
          <div className="h-7 w-7 shrink-0 rounded-08 bg-background-tint-02 animate-pulse" />
        </div>
        <div className="flex items-center gap-2">
          <div className="h-7 w-20 rounded-08 bg-background-tint-02 animate-pulse" />
          <div className="ml-auto h-7 w-24 rounded-08 bg-background-tint-02 animate-pulse" />
          <div className="h-7 w-20 rounded-08 bg-background-tint-02 animate-pulse" />
        </div>
      </div>

      {/* Underline tab strip */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-border-01">
        {TAB_WIDTHS.map((width) => (
          <div
            key={width}
            className={cn(
              "h-3.5 rounded bg-background-tint-02 animate-pulse",
              width
            )}
          />
        ))}
      </div>

      {/* The reading area under the tabs follows the white-page mode, so the
          skeleton shows up on the same surface as the loaded document. */}
      <DocumentPreviewPlaceholder className="flex-1 min-h-0 overflow-hidden p-4" />
    </div>
  );
}
