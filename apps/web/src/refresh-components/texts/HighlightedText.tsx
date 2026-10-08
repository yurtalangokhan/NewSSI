import { useMemo } from "react";
import { highlightSegments } from "@/lib/text/highlight";

interface HighlightedTextProps {
  text: string;
  query: string;
}

/** ``text`` with the query's words marked. */
export function HighlightedText({ text, query }: HighlightedTextProps) {
  const segments = useMemo(() => highlightSegments(text, query), [text, query]);
  return (
    <>
      {segments.map((segment, index) =>
        segment.match ? (
          <mark
            key={index}
            className="rounded-04 bg-theme-amber-01 px-0.5 text-text-05"
          >
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        )
      )}
    </>
  );
}
