import React from "react";
import { cn } from "@/lib/utils";

export interface DocumentPreviewSkeletonProps {
  /** Body paragraphs drawn between the title and the block. */
  paragraphCount?: number;
  /** Draw a wide block after the first paragraphs, like a diagram or a table. */
  showBlock?: boolean;
  /** Render the wrapping "paper" sheet (border, padding, centred width). */
  paper?: boolean;
  className?: string;
}

/** Cycling widths so the paragraph lines do not look like a grid. */
const LINE_WIDTHS = ["w-full", "w-11/12", "w-10/12", "w-full", "w-3/4"];

/**
 * Placeholder for a document preview: a page-shaped title, paragraph lines and
 * a wide block. Used while a revision, a chat attachment or a legacy file is
 * still loading, so the preview keeps its shape instead of flashing empty.
 */
export default function DocumentPreviewSkeleton({
  paragraphCount = 3,
  showBlock = true,
  paper = true,
  className,
}: DocumentPreviewSkeletonProps) {
  const paragraph = (keyPrefix: string) =>
    Array.from({ length: paragraphCount }).map((_, index) => (
      <div
        key={`${keyPrefix}-${index}`}
        className={cn(
          "h-3.5 rounded bg-background-tint-03 animate-pulse",
          LINE_WIDTHS[index % LINE_WIDTHS.length]
        )}
      />
    ));

  return (
    <div
      data-testid="document-preview-skeleton"
      role="status"
      aria-label="Loading document..."
      className={cn(
        paper &&
          "mx-auto w-full max-w-[48rem] rounded-12 border border-border-01 bg-background-tint-00 px-8 py-6",
        className
      )}
    >
      {/* Title and the revision/author meta line */}
      <div className="h-7 w-1/2 rounded bg-background-tint-03 animate-pulse" />
      <div className="mt-3 h-3 w-1/4 rounded bg-background-tint-03 animate-pulse opacity-60" />

      <div className="mt-6 flex flex-col gap-3">{paragraph("head")}</div>

      {showBlock && (
        <div className="mt-6 h-40 w-full rounded-12 border border-border-01 bg-background-tint-02 animate-pulse" />
      )}

      <div className="mt-6 flex flex-col gap-3">{paragraph("tail")}</div>
    </div>
  );
}
