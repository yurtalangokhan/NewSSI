import React from "react";
import { cn } from "@/lib/utils";

export interface FormSkeletonProps {
  fieldCount?: number;
  hasSubmitButton?: boolean;
  className?: string;
}

export default function FormSkeleton({
  fieldCount = 4,
  hasSubmitButton = true,
  className,
}: FormSkeletonProps) {
  return (
    <div
      className={cn("flex flex-col gap-6 w-full max-w-3xl", className)}
      role="status"
      aria-label="Loading form..."
    >
      {Array.from({ length: fieldCount }).map((_, index) => (
        <div key={index} className="flex flex-col gap-2">
          {/* Label */}
          <div className="h-4 w-32 rounded bg-background-tint-02 animate-pulse" />

          {/* Input Box */}
          <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-01 animate-pulse" />

          {/* Description helper text */}
          <div className="h-3 w-64 rounded bg-background-tint-02 animate-pulse opacity-70" />
        </div>
      ))}

      {hasSubmitButton && (
        <div className="flex items-center gap-3 pt-2">
          <div className="h-9 w-28 rounded-08 bg-background-tint-02 animate-pulse" />
          <div className="h-9 w-20 rounded-08 bg-background-tint-02 animate-pulse opacity-60" />
        </div>
      )}
    </div>
  );
}
