/**
 * Wraps the editor surface — component palette, canvas, inspector — and
 * expands that whole group when `FlowStore.isFullscreen` is set.
 */

"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useStore, type StoreApi } from "zustand";
import { cn } from "@/lib/utils";
import type { FlowStore } from "../stores/flowStore";

export type FlowEditorShellProps = {
  store: StoreApi<FlowStore>;
  className?: string;
  children: ReactNode;
};

export function FlowEditorShell({
  store,
  className,
  children,
}: FlowEditorShellProps) {
  const isFullscreen = useStore(store, (s) => s.isFullscreen);
  const setFullscreen = useStore(store, (s) => s.setFullscreen);
  const [mounted, setMounted] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const parentDialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    setMounted(true);
    if (containerRef.current) {
      parentDialogRef.current = containerRef.current.closest('[role="dialog"]');
    }
  }, []);

  // Track parent dialog before going fullscreen
  useEffect(() => {
    if (!isFullscreen && containerRef.current) {
      parentDialogRef.current = containerRef.current.closest('[role="dialog"]');
    }
  }, [isFullscreen]);

  // When fullscreen is activated from inside a modal, hide the parent modal so it doesn't
  // float in the middle of the screen or capture clicks, and mark it as the canvas parent.
  useEffect(() => {
    if (!isFullscreen) return;

    const parentDialog = parentDialogRef.current;
    if (parentDialog) {
      parentDialog.setAttribute("data-canvas-parent", "true");
      const prevVisibility = parentDialog.style.visibility;
      const prevPointerEvents = parentDialog.style.pointerEvents;
      parentDialog.style.visibility = "hidden";
      parentDialog.style.pointerEvents = "none";

      return () => {
        parentDialog.removeAttribute("data-canvas-parent");
        parentDialog.style.visibility = prevVisibility;
        parentDialog.style.pointerEvents = prevPointerEvents;
      };
    }
  }, [isFullscreen]);

  // Escape exits — the affordance the native Fullscreen API would provide.
  useEffect(() => {
    if (!isFullscreen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // If a modal dialog was opened OVER the fullscreen canvas, let that modal handle Escape first!
        const openDialogs = Array.from(
          document.querySelectorAll('[role="dialog"]')
        ) as HTMLElement[];
        const dialogOverCanvas = openDialogs.find(
          (d) =>
            d !== parentDialogRef.current && d.style.visibility !== "hidden"
        );
        if (dialogOverCanvas) {
          return;
        }
        event.stopPropagation();
        event.preventDefault();
        setFullscreen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [isFullscreen, setFullscreen]);

  // Freeze the page behind the overlay, restoring whatever `overflow` the
  // document actually had rather than assuming "visible".
  useEffect(() => {
    if (!isFullscreen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isFullscreen]);

  if (!isFullscreen || !mounted) {
    return (
      <div
        ref={containerRef}
        className={className}
        data-testid="flow-editor-shell"
      >
        {children}
      </div>
    );
  }

  if (typeof document === "undefined") return null;

  const isNestedInModal = Boolean(parentDialogRef.current);

  return createPortal(
    <div
      ref={containerRef}
      // `langflow-canvas` has to be repeated here: the portal renders
      // outside the editor page's subtree, so the `--lf-*` tokens scoped
      // to that class would otherwise not resolve.
      className={cn(
        "langflow-canvas fixed inset-0 z-canvas-fullscreen flex h-screen w-screen bg-canvas",
        isNestedInModal && "z-canvas-fullscreen-modal",
        "animate-in fade-in zoom-in-95 duration-200"
      )}
      // Opened from inside a modal, Radix's Dialog sets
      // `document.body.style.pointerEvents = "none"` while it's open and
      // only re-enables `auto` on its own dialog content node — this
      // portal renders as a sibling of that node under `document.body`
      // (see below), so without setting this explicitly here too, every
      // click on the "fullscreen" canvas would silently do nothing.
      style={{ pointerEvents: "auto" }}
      data-testid="flow-editor-shell"
      data-fullscreen="true"
    >
      {children}
    </div>,
    // Always `document.body`, never nested inside a dialog's own content
    // node: that element is centered with a CSS `transform`, which per
    // spec becomes the containing block for `position: fixed`
    // descendants — nesting in it would silently clip "fullscreen" down
    // to the dialog's own (much smaller) box instead of the viewport.
    document.body
  );
}
