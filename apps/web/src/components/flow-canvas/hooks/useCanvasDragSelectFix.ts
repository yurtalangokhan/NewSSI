/**
 * Ported from Langflow (MIT) — src/frontend/src/pages/FlowPage/components/PageComponent/hooks/useCanvasDragSelectFix.ts
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 * Adapted for Onyx: verbatim — a real browser-bug workaround with no
 * Langflow-specific coupling.
 *
 * Brief: .tmp/flow-canvas-task-24-brief.md
 */

import { useEffect } from "react";

/**
 * Suppresses text selection during any canvas drag in WKWebView.
 *
 * WKWebView does not suppress selection on pointer-drag the way Chromium
 * does, so text/labels/inputs highlight as the pointer moves over them
 * during a shift-drag box-select, an edge drag, or a node drag. Sets
 * user-select:none on the root element for the lifetime of the drag and
 * restores it on mouseup, so normal text editing elsewhere is unaffected.
 */
export function useCanvasDragSelectFix(
  ref: React.RefObject<HTMLElement | null>
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onMouseDown = () => {
      document.documentElement.style.setProperty("-webkit-user-select", "none");
      document.documentElement.style.setProperty("user-select", "none");
      const restore = () => {
        document.documentElement.style.removeProperty("-webkit-user-select");
        document.documentElement.style.removeProperty("user-select");
        document.removeEventListener("mouseup", restore);
      };
      document.addEventListener("mouseup", restore);
    };

    el.addEventListener("mousedown", onMouseDown);
    return () => el.removeEventListener("mousedown", onMouseDown);
  }, [ref]);
}
