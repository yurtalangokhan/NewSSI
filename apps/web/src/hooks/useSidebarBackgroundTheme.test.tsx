import { act, renderHook } from "@testing-library/react";
import useSidebarBackgroundTheme from "@/hooks/useSidebarBackgroundTheme";
import useBackgroundAnimation from "@/hooks/useBackgroundAnimation";

describe("useSidebarBackgroundTheme", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("is on by default", () => {
    const { result } = renderHook(() => useSidebarBackgroundTheme());

    expect(result.current[0]).toBe(true);
  });

  it("remembers being switched off under its own key", () => {
    const { result } = renderHook(() => useSidebarBackgroundTheme());

    act(() => result.current[1](false));

    expect(result.current[0]).toBe(false);
    expect(
      window.localStorage.getItem("agentic_sidebar_background_theme")
    ).toBe("off");
  });

  it("does not affect the background animation flag", () => {
    const theme = renderHook(() => useSidebarBackgroundTheme());
    const animation = renderHook(() => useBackgroundAnimation());

    act(() => theme.result.current[1](false));

    expect(animation.result.current[0]).toBe(true);
  });
});
