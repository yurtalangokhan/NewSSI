"use client";

import { cn } from "@/lib/utils";

interface MermaidSourceProps {
  source: string;
  /** 1-based line to mark as failing. */
  highlightLine?: number | null;
}

export function MermaidSource({
  source,
  highlightLine = null,
}: MermaidSourceProps) {
  const lines = source.split("\n");
  return (
    <pre
      data-testid="mermaid-source"
      className="m-0 overflow-x-auto bg-background-tint-00 py-2 font-mono text-xs leading-relaxed"
    >
      <code>
        {lines.map((line, index) => {
          const isBad = highlightLine === index + 1;
          return (
            <span
              key={index}
              data-line={index + 1}
              data-error-line={isBad ? "true" : undefined}
              className={cn(
                "block whitespace-pre px-3",
                isBad
                  ? "bg-status-error-01 text-status-error-05"
                  : "text-text-04"
              )}
            >
              {line === "" ? " " : line}
            </span>
          );
        })}
      </code>
    </pre>
  );
}
