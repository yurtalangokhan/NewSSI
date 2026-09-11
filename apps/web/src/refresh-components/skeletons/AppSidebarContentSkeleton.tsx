import React from "react";
import ChatSessionSkeleton from "@/refresh-components/skeletons/ChatSessionSkeleton";

export default function AppSidebarContentSkeleton() {
  return (
    <div
      className="flex flex-col w-full gap-5 py-2"
      role="status"
      aria-label="Loading sidebar content..."
    >
      {/* Agents Section */}
      <div className="flex flex-col gap-1 w-full">
        <div className="px-3 mb-1">
          <div className="h-3 w-16 rounded bg-background-tint-04 animate-pulse" />
        </div>
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-2.5 px-3 py-1.5 w-full rounded-08"
          >
            <div className="h-5 w-5 rounded-full bg-background-tint-02 animate-pulse shrink-0" />
            <div
              className={`h-3.5 rounded bg-background-tint-02 animate-pulse ${
                index === 0 ? "w-28" : index === 1 ? "w-24" : "w-32"
              }`}
            />
          </div>
        ))}
      </div>

      {/* Projects Section */}
      <div className="flex flex-col gap-1 w-full">
        <div className="px-3 mb-1">
          <div className="h-3 w-16 rounded bg-background-tint-04 animate-pulse" />
        </div>
        {Array.from({ length: 2 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-2.5 px-3 py-1.5 w-full rounded-08"
          >
            <div className="h-4 w-4 rounded bg-background-tint-02 animate-pulse shrink-0" />
            <div
              className={`h-3.5 rounded bg-background-tint-02 animate-pulse ${
                index === 0 ? "w-32" : "w-24"
              }`}
            />
          </div>
        ))}
      </div>

      {/* Recents Section */}
      <div className="flex flex-col gap-1 w-full">
        <div className="px-3 mb-1">
          <div className="h-3 w-16 rounded bg-background-tint-04 animate-pulse" />
        </div>
        {Array.from({ length: 4 }).map((_, index) => (
          <ChatSessionSkeleton key={index} />
        ))}
      </div>
    </div>
  );
}
