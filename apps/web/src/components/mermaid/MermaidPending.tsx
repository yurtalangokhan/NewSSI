"use client";

import { useTranslation } from "react-i18next";
import Skeleton from "@/refresh-components/skeletons/Skeleton";
import Text from "@/refresh-components/texts/Text";
import { summarizePending } from "@/components/mermaid/mermaidSource";

interface MermaidPendingProps {
  source: string;
  /** False while the fence is still streaming; true while it is being drawn. */
  isComplete: boolean;
}

export function MermaidPending({ source, isComplete }: MermaidPendingProps) {
  const { t } = useTranslation();
  const { lineCount, lastLine } = summarizePending(source);
  const status = isComplete
    ? t("mermaid.rendering")
    : t("mermaid.writing", { count: lineCount });

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={status}
      data-testid="mermaid-pending"
      className="flex flex-col"
    >
      <div className="px-3 pt-2">
        <Text secondaryMono text03>
          {status}
        </Text>
      </div>
      <div
        aria-hidden
        className="flex h-32 items-center justify-center gap-3 px-3"
      >
        <Skeleton className="h-7 w-16" />
        <Skeleton className="h-0.5 w-6" variant="rectangular" />
        <Skeleton className="h-7 w-16" />
        <Skeleton className="h-0.5 w-6" variant="rectangular" />
        <Skeleton className="h-7 w-16" />
      </div>
      {!isComplete && lastLine !== "" && (
        <div
          data-testid="mermaid-pending-tail"
          className="flex items-center overflow-hidden border-t border-border-01 px-3 py-2"
        >
          <Text secondaryMono text03 nowrap className="truncate whitespace-pre">
            {lastLine}
          </Text>
          <span
            aria-hidden
            className="ml-0.5 inline-block h-3 w-1.5 shrink-0 animate-pulse bg-action-link-05 motion-reduce:animate-none"
          />
        </div>
      )}
    </div>
  );
}
