import { cn } from "@/lib/utils";

interface EvidenceTextBlockProps {
  children: string;
  /** Bounds the block, e.g. ``max-h-56``. */
  className?: string;
}

/** Preformatted text as the model or a tool produced it, in a scrollable box. */
export function EvidenceTextBlock({
  children,
  className,
}: EvidenceTextBlockProps) {
  return (
    <pre
      className={cn(
        "overflow-auto whitespace-pre-wrap break-words rounded-08 border border-border-01 bg-background-tint-01 p-3 font-main-ui-mono text-text-04",
        className
      )}
    >
      {children}
    </pre>
  );
}
