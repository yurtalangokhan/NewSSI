import React, { useState } from "react";
import { cn } from "@/lib/utils";

// Pools to draw random shapes from — every mount gets a slightly different
// arrangement so a real, un-loaded conversation never all looks the same.
const REPLY_LINE_WIDTH_POOL = [
  "w-full",
  "w-[92%]",
  "w-[85%]",
  "w-[74%]",
  "w-[60%]",
  "w-[45%]",
];
const USER_BUBBLE_WIDTH_POOL = ["w-1/4", "w-[30%]", "w-2/5", "w-1/2"];
const HUMAN_INPUT_BUTTON_WIDTH_POOL = ["w-20", "w-24", "w-28", "w-32"];

// Occasional chance a reply looks like a human-in-the-loop card (an approval
// or clarification request) instead of plain prose — real agent
// conversations mix both, so an all-prose skeleton reads as less alive.
const HUMAN_INPUT_CHANCE = 0.3;

function randomInt(min: number, max: number): number {
  return min + Math.floor(Math.random() * (max - min + 1));
}

function pick<T>(pool: T[]): T {
  // Pools are always non-empty constants defined above, so the index is
  // always in range.
  return pool[randomInt(0, pool.length - 1)]!;
}

interface ReplyExchange {
  kind: "reply";
  bubbleWidthClass: string;
  lineWidths: string[];
}

interface HumanInputExchange {
  kind: "humanInput";
  bubbleWidthClass: string;
  promptWidthClass: string;
  buttonWidths: string[];
}

type Exchange = ReplyExchange | HumanInputExchange;

function buildExchange(): Exchange {
  const bubbleWidthClass = pick(USER_BUBBLE_WIDTH_POOL);

  if (Math.random() < HUMAN_INPUT_CHANCE) {
    return {
      kind: "humanInput",
      bubbleWidthClass,
      promptWidthClass: pick(REPLY_LINE_WIDTH_POOL),
      buttonWidths: Array.from({ length: randomInt(2, 3) }, () =>
        pick(HUMAN_INPUT_BUTTON_WIDTH_POOL)
      ),
    };
  }

  const lineCount = randomInt(2, 4);
  const lineWidths = Array.from({ length: lineCount }, (_, i) =>
    // Last line in a paragraph is always shorter — keep that even when
    // randomized, so it still reads as trailing off rather than cut short.
    i === lineCount - 1
      ? pick(["w-[35%]", "w-[45%]", "w-[55%]"])
      : pick(REPLY_LINE_WIDTH_POOL)
  );

  return { kind: "reply", bubbleWidthClass, lineWidths };
}

function buildExchanges(pairCount: number): Exchange[] {
  return Array.from({ length: pairCount }, buildExchange);
}

const pulseShape =
  "border border-border-02 bg-background-tint-03 animate-pulse";

export interface ChatMessagesSkeletonProps {
  /**
   * Number of user-question / assistant-reply exchanges to render. Omit to
   * pick a random count (2–4) so the skeleton doesn't look identical on
   * every load.
   */
  pairCount?: number;
  className?: string;
}

/**
 * Placeholder shown in the message list while an existing chat session's
 * history is still being fetched (see `isFetchingChatMessages`). Mimics the
 * shape of a real exchange — a right-aligned user bubble followed by either
 * plain assistant prose or a human-in-the-loop card (mirroring
 * HumanInputRenderer / UserClarificationRenderer) — using the calm
 * `animate-pulse` treatment every other skeleton in this app uses for shapes.
 * Bubble widths, line counts and the reply/human-input mix are randomized
 * once per mount so it reads as a real, varied conversation rather than a
 * repeating template.
 */
export default function ChatMessagesSkeleton({
  pairCount,
  className,
}: ChatMessagesSkeletonProps) {
  const [resolvedPairCount] = useState(() => pairCount ?? randomInt(2, 4));
  const [exchanges] = useState(() => buildExchanges(resolvedPairCount));

  return (
    <div
      className={cn("flex flex-col w-full gap-8 md:gap-10", className)}
      role="status"
      aria-label="Loading messages..."
    >
      {exchanges.map((exchange, pairIndex) => (
        <div key={pairIndex} className="flex flex-col w-full gap-4">
          {/* User bubble */}
          <div className="flex justify-end">
            <div
              className={cn(
                "h-9 max-w-[22rem] rounded-t-16 rounded-bl-16",
                pulseShape,
                exchange.bubbleWidthClass
              )}
              style={{ animationDelay: `${pairIndex * 300}ms` }}
            />
          </div>

          {exchange.kind === "reply" ? (
            <div className="flex flex-col gap-2.5" aria-hidden="true">
              {exchange.lineWidths.map((width, lineIndex) => (
                <div
                  key={lineIndex}
                  className={cn("h-3 rounded-04", pulseShape, width)}
                  style={{
                    animationDelay: `${pairIndex * 300 + lineIndex * 100}ms`,
                  }}
                />
              ))}
            </div>
          ) : (
            // Human-in-the-loop card placeholder (approval / clarification)
            <div
              aria-hidden="true"
              className="flex w-full flex-col gap-3 rounded-lg border border-border-02 bg-background-tint-01 p-4"
            >
              <div className="flex items-center gap-2">
                <div
                  className={cn("h-4 w-4 rounded-full", pulseShape)}
                  style={{ animationDelay: `${pairIndex * 300}ms` }}
                />
                <div
                  className={cn("h-3 w-40 rounded-04", pulseShape)}
                  style={{ animationDelay: `${pairIndex * 300 + 100}ms` }}
                />
              </div>
              <div
                className={cn(
                  "h-3 rounded-04",
                  pulseShape,
                  exchange.promptWidthClass
                )}
                style={{ animationDelay: `${pairIndex * 300 + 200}ms` }}
              />
              <div className="flex flex-wrap gap-2">
                {exchange.buttonWidths.map((width, buttonIndex) => (
                  <div
                    key={buttonIndex}
                    className={cn("h-8 rounded-full", pulseShape, width)}
                    style={{
                      animationDelay: `${
                        pairIndex * 300 + 300 + buttonIndex * 100
                      }ms`,
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
