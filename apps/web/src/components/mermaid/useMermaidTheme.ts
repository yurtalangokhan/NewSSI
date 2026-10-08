"use client";

import { useMemo, useSyncExternalStore } from "react";
import {
  SERVER_MERMAID_THEME,
  readElementTheme,
  type MermaidThemeConfig,
} from "@/components/mermaid/mermaidTheme";
import { useLightSurfaceElement } from "@/components/theme/LightSurface";

/** next-themes toggles `class` on <html>; admin themes may set inline vars. */
function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "style", "data-theme"],
  });
  return () => observer.disconnect();
}

function getSnapshot(): string {
  const root = document.documentElement;
  return `${root.className}|${root.getAttribute("style") ?? ""}|${
    root.getAttribute("data-theme") ?? ""
  }`;
}

function getServerSnapshot(): string {
  return "";
}

export function useMermaidTheme(): MermaidThemeConfig {
  const snapshot = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot
  );
  // A diagram inside a forced-light surface (the document panel's white page)
  // follows that page's tokens instead of the page-level theme.
  const lightSurface = useLightSurfaceElement();
  return useMemo(
    () =>
      typeof document === "undefined"
        ? SERVER_MERMAID_THEME
        : readElementTheme(lightSurface),
    [snapshot, lightSurface]
  );
}
