import React from "react";

export default function ChatSessionSkeleton() {
  return (
    <div className="w-full rounded-08 py-2 p-1.5">
      <div className="flex gap-3 min-w-0 w-full">
        <div className="flex h-full w-fit pt-1 pl-1">
          <div className="h-4 w-4 rounded bg-background-tint-03 animate-pulse shrink-0" />
        </div>
        <div className="flex flex-col w-full gap-1.5">
          <div className="h-3.5 w-2/3 rounded bg-background-tint-03 animate-pulse" />
          <div className="h-3 w-1/3 rounded bg-background-tint-02 animate-pulse" />
        </div>
      </div>
    </div>
  );
}
