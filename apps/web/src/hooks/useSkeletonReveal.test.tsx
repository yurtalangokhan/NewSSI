import { renderHook } from "@testing-library/react";
import { SKELETON_REVEAL_CLASS, useSkeletonReveal } from "./useSkeletonReveal";

const items = (...ids: number[]) => ids.map((nodeId) => ({ nodeId }));

describe("useSkeletonReveal", () => {
  it("reveals nothing when the list was never behind a skeleton", () => {
    const { result } = renderHook(
      ({ skeleton, list }) => useSkeletonReveal(skeleton, list),
      { initialProps: { skeleton: false, list: items(1, 2) } }
    );
    expect(result.current).toBeNull();
  });

  it("reveals nothing while the skeleton is still up", () => {
    const { result } = renderHook(
      ({ skeleton, list }) => useSkeletonReveal(skeleton, list),
      { initialProps: { skeleton: true, list: items() } }
    );
    expect(result.current).toBeNull();
  });

  it("names the messages that replaced the skeleton", () => {
    const { result, rerender } = renderHook(
      ({ skeleton, list }) => useSkeletonReveal(skeleton, list),
      { initialProps: { skeleton: true, list: items() } }
    );
    rerender({ skeleton: false, list: items(1, 2, 3) });
    expect(Array.from(result.current ?? [])).toEqual([1, 2, 3]);
  });

  it("is already set in the very render that swaps the skeleton out", () => {
    // The class must be on the first painted frame, or nothing animates.
    const seen: (ReadonlySet<number> | null)[] = [];
    const { rerender } = renderHook(
      ({ skeleton, list }) => {
        const revealed = useSkeletonReveal(skeleton, list);
        seen.push(revealed);
        return revealed;
      },
      { initialProps: { skeleton: true, list: items() } }
    );
    rerender({ skeleton: false, list: items(1) });
    expect(seen.at(-1)?.has(1)).toBe(true);
  });

  it("leaves messages that arrive afterwards out of the reveal", () => {
    const { result, rerender } = renderHook(
      ({ skeleton, list }) => useSkeletonReveal(skeleton, list),
      { initialProps: { skeleton: true, list: items() } }
    );
    rerender({ skeleton: false, list: items(1, 2) });
    rerender({ skeleton: false, list: items(1, 2, 3, 4) });
    expect(Array.from(result.current ?? [])).toEqual([1, 2]);
  });

  it("starts over when a skeleton comes back", () => {
    const { result, rerender } = renderHook(
      ({ skeleton, list }) => useSkeletonReveal(skeleton, list),
      { initialProps: { skeleton: true, list: items() } }
    );
    rerender({ skeleton: false, list: items(1) });
    rerender({ skeleton: true, list: items() });
    expect(result.current).toBeNull();
    rerender({ skeleton: false, list: items(7) });
    expect(Array.from(result.current ?? [])).toEqual([7]);
  });

  it("honours reduced motion", () => {
    expect(SKELETON_REVEAL_CLASS).toContain("motion-reduce:animate-none");
    expect(SKELETON_REVEAL_CLASS).toContain("animate-in");
    expect(SKELETON_REVEAL_CLASS).toContain("fade-in");
  });
});
