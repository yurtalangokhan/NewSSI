import React from "react";
import { cn } from "@/lib/utils";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "rectangular" | "circular" | "rounded" | "pill";
}

export default function Skeleton({
  className,
  variant = "rounded",
  ...props
}: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse bg-background-tint-03 dark:bg-background-tint-04",
        variant === "circular" && "rounded-full",
        variant === "rounded" && "rounded-08",
        variant === "rectangular" && "rounded-none",
        variant === "pill" && "rounded-full",
        className
      )}
      role="status"
      aria-label="Loading..."
      {...props}
    />
  );
}
