import { useState } from "react";

/** Fades in what replaces a loading skeleton, and only that. */
export const SKELETON_REVEAL_CLASS =
  "animate-in fade-in slide-in-from-bottom-2 duration-300 motion-reduce:animate-none";

/**
 * The ids of the items that replaced a skeleton, so the list can fade exactly
 * those in. Later arrivals (a message being sent) are not part of the reveal.
 * `null` while a skeleton is showing or when the list never sat behind one.
 *
 * The set is decided during the render that swaps the skeleton out, not in an
 * effect: the fade class has to be on the first painted frame of the items or
 * the animation never plays.
 */
export function useSkeletonReveal(
  showingSkeleton: boolean,
  items: readonly { nodeId: number }[]
): ReadonlySet<number> | null {
  const [wasSkeleton, setWasSkeleton] = useState(showingSkeleton);
  const [revealed, setRevealed] = useState<ReadonlySet<number> | null>(null);

  if (wasSkeleton !== showingSkeleton) {
    setWasSkeleton(showingSkeleton);
    setRevealed(
      showingSkeleton ? null : new Set(items.map((item) => item.nodeId))
    );
  }
  return revealed;
}
