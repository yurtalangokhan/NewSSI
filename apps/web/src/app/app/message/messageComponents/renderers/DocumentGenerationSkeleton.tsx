"use client";

import React from "react";
import { useTranslation } from "react-i18next";
import { FileIcon } from "@/components/icons/icons";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { DocumentGenerationPhase } from "@/app/app/services/streamingModels";

// Relative widths of the placeholder text lines — uneven on purpose, so the
// block reads as a page of prose being written rather than a loading bar.
const LINE_WIDTHS = ["w-[92%]", "w-[78%]", "w-[85%]", "w-[60%]"];

export interface DocumentGenerationSkeletonProps {
  /** "writing" while the model dictates the body, "rendering" while the file is built. */
  phase: DocumentGenerationPhase;
  /** Known once the model has streamed the filename argument. */
  filename?: string | null;
  /** File extension, e.g. "pdf" — shown next to the filename when known. */
  format?: string | null;
  /** Characters of body written so far; hidden until there is something to show. */
  chars?: number;
}

/**
 * Placeholder shown while a document tool is producing a file.
 *
 * Writing the body can take a long time and emits no chat tokens at all, so
 * without this the message area sits empty and the stream looks stuck. The
 * skeleton occupies the same slot the finished file card will appear in.
 */
export function DocumentGenerationSkeleton({
  phase,
  filename,
  format,
  chars = 0,
}: DocumentGenerationSkeletonProps) {
  const { t } = useTranslation();

  const label =
    phase === "rendering"
      ? t("documentGeneration.rendering", "Preparing file...")
      : t("documentGeneration.writing", "Writing document...");

  const title = filename
    ? format && !filename.toLowerCase().endsWith(`.${format.toLowerCase()}`)
      ? `${filename}.${format}`
      : filename
    : t("documentGeneration.untitled", "Document");

  return (
    <div
      className="flex flex-col border bg-background-tint-00 rounded-12 p-1 gap-2 my-1 w-full max-w-[22rem] animate-fade-in-scale"
      role="status"
      aria-live="polite"
      aria-label={label}
      data-testid="document-generation-skeleton"
    >
      <div className="flex items-center gap-1">
        <div className="p-2 bg-background-tint-01 rounded-08 animate-subtle-pulse">
          <FileIcon size={20} />
        </div>
        <div className="flex flex-col px-2 min-w-0">
          <Text as="p" secondaryAction className="truncate">
            {title}
          </Text>
          <Text
            as="p"
            secondaryBody
            text03
            className="animate-shimmer bg-[length:200%_100%] bg-[linear-gradient(90deg,var(--shimmer-base)_10%,var(--shimmer-highlight)_40%,var(--shimmer-base)_70%)] bg-clip-text text-transparent"
          >
            {chars > 0
              ? t("documentGeneration.progress", {
                  label,
                  chars: chars.toLocaleString(),
                  defaultValue: "{{label}} ({{chars}} characters)",
                })
              : label}
          </Text>
        </div>
      </div>

      {/* Placeholder body lines — purely decorative, hidden from screen readers
          which already get the live label above. */}
      <div className="flex flex-col gap-2 px-3 pb-2 pt-1" aria-hidden="true">
        {LINE_WIDTHS.map((width, index) => (
          <div
            key={width}
            className={cn(
              "h-2 rounded-04 bg-background-tint-02 animate-shimmer bg-[length:200%_100%]",
              "bg-[linear-gradient(90deg,var(--shimmer-base)_10%,var(--shimmer-highlight)_40%,var(--shimmer-base)_70%)]",
              width
            )}
            style={{ animationDelay: `${index * 120}ms`, opacity: 0.35 }}
          />
        ))}
      </div>
    </div>
  );
}

export default DocumentGenerationSkeleton;
