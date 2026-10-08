import { act, renderHook } from "@testing-library/react";
import useBackgroundAnimation from "@/hooks/useBackgroundAnimation";

describe("useBackgroundAnimation", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("animates by default", () => {
    const { result } = renderHook(() => useBackgroundAnimation());

    expect(result.current[0]).toBe(true);
  });

  it("remembers a disabled animation across mounts", () => {
    const first = renderHook(() => useBackgroundAnimation());
    act(() => first.result.current[1](false));
    first.unmount();

    const second = renderHook(() => useBackgroundAnimation());

    expect(second.result.current[0]).toBe(false);
  });

  it("updates every mounted consumer in the same tab", () => {
    const a = renderHook(() => useBackgroundAnimation());
    const b = renderHook(() => useBackgroundAnimation());

    act(() => a.result.current[1](false));

    expect(b.result.current[0]).toBe(false);
  });

  it("follows a change made in another tab", () => {
    const { result } = renderHook(() => useBackgroundAnimation());

    act(() => {
      window.localStorage.setItem("agentic_background_animation", "off");
      window.dispatchEvent(new StorageEvent("storage"));
    });

    expect(result.current[0]).toBe(false);
  });

  it("re-enables animation", () => {
    const { result } = renderHook(() => useBackgroundAnimation());
    act(() => result.current[1](false));

    act(() => result.current[1](true));

    expect(result.current[0]).toBe(true);
  });

  it("falls back to animating, without throwing, when storage is blocked", () => {
    jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    const { result } = renderHook(() => useBackgroundAnimation());

    expect(result.current[0]).toBe(true);
    expect(() => act(() => result.current[1](false))).not.toThrow();
  });
});
