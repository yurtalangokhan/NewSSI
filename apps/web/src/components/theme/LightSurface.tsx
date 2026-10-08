"use client";

import {
  createContext,
  useContext,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

/**
 * The DOM node that carries a forced-light token scope, or `null` outside one.
 */
const LightSurfaceContext = createContext<HTMLElement | null>(null);

interface LightSurfaceProps extends HTMLAttributes<HTMLDivElement> {
  /** False renders a plain div, so call sites stay one tree in both states. */
  enabled: boolean;
  children: ReactNode;
}

/**
 * A surface whose subtree uses the light colour tokens even when the app is in
 * dark mode (`colors.css` re-applies the light set on `.theme-light`).
 *
 * The mounted node is shared through context so JavaScript-driven colours that
 * cannot read CSS variables themselves — the Mermaid theme — follow the same
 * scope instead of `<html>`.
 */
export function LightSurface({
  enabled,
  className,
  children,
  ...rest
}: LightSurfaceProps) {
  const [element, setElement] = useState<HTMLDivElement | null>(null);

  return (
    <LightSurfaceContext.Provider value={enabled ? element : null}>
      <div
        // A callback ref (not `useRef`): the node is state so consumers
        // re-render once it exists, and it never remounts the surface.
        ref={enabled ? setElement : undefined}
        className={cn(enabled && "theme-light", className)}
        {...rest}
      >
        {children}
      </div>
    </LightSurfaceContext.Provider>
  );
}

/** The enclosing light-scope node, or `null` when the subtree is not scoped. */
export function useLightSurfaceElement(): HTMLElement | null {
  return useContext(LightSurfaceContext);
}
