"use client";

import type { HTMLAttributes } from "react";
import { LightSurface } from "@/components/theme/LightSurface";
import { useWhitePage } from "@/sections/document-panel/useWhitePage";
import { cn } from "@/lib/utils";

type PaperProps = HTMLAttributes<HTMLDivElement>;

/**
 * The sheet a document is rendered on. `paper` and `page` modes both turn the
 * sheet light, so the text area never flips colour between "loading" and
 * "loaded".
 */
export function DocumentPaper({ className, children, ...rest }: PaperProps) {
  const [mode] = useWhitePage();

  return (
    <LightSurface
      enabled={mode !== "off"}
      className={cn(
        "mx-auto w-full max-w-[48rem] rounded-12 bg-background-tint-00 border border-border-01 px-8 py-6",
        className
      )}
      {...rest}
    >
      {children}
    </LightSurface>
  );
}

/**
 * The reading viewport itself. In `page` mode it paints the page colour edge to
 * edge, so whatever a document renders — the sheet, its skeleton, or content
 * that overflows the sheet — sits on one colour and scrolling cannot shift the
 * background between black and white. `paper` mode keeps the app surface here
 * (the sheet alone goes light).
 *
 * `enabled={false}` keeps the viewport on the app surface for tabs that are not
 * documents (the diff and history tools).
 */
export function DocumentReadingSurface({
  enabled = true,
  className,
  children,
  ...rest
}: PaperProps & { enabled?: boolean }) {
  const [mode] = useWhitePage();

  return (
    <LightSurface
      enabled={enabled && mode === "page"}
      className={cn("bg-background-tint-00", className)}
      {...rest}
    >
      {children}
    </LightSurface>
  );
}
