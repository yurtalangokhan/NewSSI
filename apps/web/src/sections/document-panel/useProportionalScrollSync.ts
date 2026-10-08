"use client";

import { useEffect } from "react";

/** Keep two scroll containers at the same relative position. */
export function useProportionalScrollSync(
  left: HTMLElement | null,
  right: HTMLElement | null,
  enabled: boolean
) {
  useEffect(() => {
    if (!enabled || !left || !right) return;

    // The programmatic scroll we cause fires a scroll event on the target;
    // swallow exactly that one so the two sides do not ping-pong.
    let echo: HTMLElement | null = null;
    const follow = (from: HTMLElement, to: HTMLElement) => () => {
      if (echo === from) {
        echo = null;
        return;
      }
      const range = from.scrollHeight - from.clientHeight;
      const ratio = range > 0 ? from.scrollTop / range : 0;
      const before = to.scrollTop;
      to.scrollTop = ratio * (to.scrollHeight - to.clientHeight);
      // Only a real move fires an echo event; arming it otherwise would
      // swallow the user's next scroll on the other side.
      echo = to.scrollTop !== before ? to : null;
    };

    const onLeft = follow(left, right);
    const onRight = follow(right, left);
    left.addEventListener("scroll", onLeft, { passive: true });
    right.addEventListener("scroll", onRight, { passive: true });
    return () => {
      left.removeEventListener("scroll", onLeft);
      right.removeEventListener("scroll", onRight);
    };
  }, [left, right, enabled]);
}
