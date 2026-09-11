import { renderHook, act } from "@testing-library/react";
import { useIdempotencyKey } from "./useIdempotencyKey";

describe("useIdempotencyKey", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("returns a stable key across renders for the same operation", () => {
    const { result, rerender } = renderHook(({ id }) => useIdempotencyKey(id), {
      initialProps: { id: "create-assistant" },
    });

    const firstKey = result.current.key;
    rerender({ id: "create-assistant" });
    rerender({ id: "create-assistant" });

    expect(result.current.key).toBe(firstKey);
  });

  it("returns different keys for different operations", () => {
    const { result, rerender } = renderHook(({ id }) => useIdempotencyKey(id), {
      initialProps: { id: "op-a" },
    });

    const keyA = result.current.key;
    rerender({ id: "op-b" });

    expect(result.current.key).not.toBe(keyA);
  });

  it("persists the key in sessionStorage", () => {
    const { result } = renderHook(() => useIdempotencyKey("persist-op"));

    const stored = window.sessionStorage.getItem("idem-key:persist-op");
    expect(stored).toBe(result.current.key);
  });

  it("recovers the same key after a remount", () => {
    const { result, unmount } = renderHook(() =>
      useIdempotencyKey("remount-op")
    );
    const firstKey = result.current.key;
    unmount();

    const { result: remounted } = renderHook(() =>
      useIdempotencyKey("remount-op")
    );
    expect(remounted.current.key).toBe(firstKey);
  });

  it("clearKey removes the stored key", () => {
    const { result } = renderHook(() => useIdempotencyKey("clear-op"));

    act(() => {
      result.current.clearKey();
    });

    expect(window.sessionStorage.getItem("idem-key:clear-op")).toBeNull();
  });

  it("generates a new key after clearKey", () => {
    const { result } = renderHook(() => useIdempotencyKey("new-after-clear"));
    const firstKey = result.current.key;

    act(() => {
      result.current.clearKey();
    });

    const { result: fresh } = renderHook(() =>
      useIdempotencyKey("new-after-clear")
    );
    expect(fresh.current.key).not.toBe(firstKey);
  });
});
