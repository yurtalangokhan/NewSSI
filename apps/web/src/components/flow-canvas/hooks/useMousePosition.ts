/**
 * Tracks the last known mouse position within a wrapper element, in screen
 * coordinates. Paste-at-cursor (Ctrl+V, duplicate) needs "where is the
 * mouse right now" outside of any specific event handler — Langflow keeps
 * this in a ref updated by a mousemove listener; ported the same way.
 *
 * Brief: .tmp/flow-canvas-task-24-brief.md
 */

import { useEffect, useRef } from "react";

export function useMousePosition(ref: React.RefObject<HTMLElement | null>) {
  const position = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onMouseMove = (e: MouseEvent) => {
      const bounds = el.getBoundingClientRect();
      position.current = {
        x: e.clientX - bounds.left,
        y: e.clientY - bounds.top,
      };
    };

    el.addEventListener("mousemove", onMouseMove);
    return () => el.removeEventListener("mousemove", onMouseMove);
  }, [ref]);

  return position;
}
