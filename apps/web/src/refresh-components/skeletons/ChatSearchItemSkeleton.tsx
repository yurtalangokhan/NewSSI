import React from "react";

export default function ChatSearchItemSkeleton({
  count = 2,
}: {
  count?: number;
}) {
  return (
    <div
      className="flex flex-col gap-1 w-full px-2 py-1"
      role="status"
      aria-label="Searching chats..."
    >
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="flex items-center justify-between p-2 rounded-08 bg-background-neutral-01"
        >
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="h-4 w-4 rounded bg-background-tint-03 animate-pulse shrink-0" />
            <div
              className={`h-3.5 rounded bg-background-tint-03 animate-pulse ${
                index === 0 ? "w-3/4" : "w-1/2"
              }`}
            />
          </div>
          <div className="h-3 w-12 rounded bg-background-tint-03 animate-pulse shrink-0 ml-2" />
        </div>
      ))}
    </div>
  );
}
