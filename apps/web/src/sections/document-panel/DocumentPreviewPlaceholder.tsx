"use client";

import type { HTMLAttributes } from "react";
import { DocumentPreviewSkeleton } from "@/refresh-components/skeletons";
import {
  DocumentPaper,
  DocumentReadingSurface,
} from "@/sections/document-panel/DocumentPaper";
import { useWhitePage } from "@/sections/document-panel/useWhitePage";

/**
 * The loading placeholder of a document preview. It follows the same three white
 * page modes as the loaded document, so the surface never changes colour when
 * the text arrives:
 *
 * - `off`   — the text column on the app surface
 * - `paper` — a light sheet inside the app surface
 * - `page`  — the text column directly on the light reading area
 */
export function DocumentPreviewPlaceholder({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  const [mode] = useWhitePage();

  return (
    <DocumentReadingSurface className={className} {...rest}>
      {mode === "paper" ? (
        <DocumentPaper>
          <DocumentPreviewSkeleton paper={false} />
        </DocumentPaper>
      ) : (
        <DocumentPreviewSkeleton
          paper={false}
          className="mx-auto w-full max-w-[48rem] px-8 py-6"
        />
      )}
    </DocumentReadingSurface>
  );
}
