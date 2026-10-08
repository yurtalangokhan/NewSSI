"use client";

import * as React from "react";
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import { cn } from "@/lib/utils";
import { wrapperClasses } from "@/refresh-components/inputs/styles";

export interface InputAvatarProps
  extends React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Root> {
  variant?: "agent" | "flow";
}

const InputAvatar = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Root>,
  InputAvatarProps
>(({ className, variant = "agent", ...props }, ref) => (
  <AvatarPrimitive.Root
    ref={ref}
    data-variant={variant}
    className={cn(
      "relative flex h-10 w-10 shrink-0 overflow-hidden",
      variant === "flow" ? "rounded-[28%]" : "rounded-full",
      wrapperClasses.primary,
      className
    )}
    {...props}
  />
));
InputAvatar.displayName = AvatarPrimitive.Root.displayName;

export default InputAvatar;
