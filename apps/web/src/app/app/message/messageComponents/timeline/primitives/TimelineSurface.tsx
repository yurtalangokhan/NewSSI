import React from "react";
import { cn } from "@/lib/utils";
import { useAppBackground } from "@/providers/AppBackgroundProvider";

export type TimelineSurfaceBackground = "tint" | "transparent";

export interface TimelineSurfaceProps {
  children: React.ReactNode;
  className?: string;
  isHover?: boolean;
  roundedTop?: boolean;
  roundedBottom?: boolean;
  background?: TimelineSurfaceBackground;
  "data-testid"?: string;
}

/**
 * TimelineSurface provides the shared background + rounded corners for a row.
 * Use it to keep hover and tint behavior consistent across timeline items.
 */
export function TimelineSurface({
  children,
  className,
  isHover = false,
  roundedTop = false,
  roundedBottom = false,
  background = "tint",
  "data-testid": testId,
}: TimelineSurfaceProps) {
  const { hasBackground } = useAppBackground();

  if (React.Children.count(children) === 0) {
    return null;
  }

  const baseBackground =
    background === "tint"
      ? hasBackground
        ? "backdrop-blur-md bg-background-tint-00/60"
        : "bg-background-tint-00"
      : "";
  const hoverBackground =
    background === "tint" && isHover
      ? hasBackground
        ? "backdrop-blur-md bg-background-tint-02/60"
        : "bg-background-tint-02"
      : "";

  return (
    <div
      data-testid={testId}
      className={cn(
        "transition-colors duration-200",
        baseBackground,
        hoverBackground,
        roundedTop && "rounded-t-12",
        roundedBottom && "rounded-b-12",
        className
      )}
    >
      {children}
    </div>
  );
}

export default TimelineSurface;
