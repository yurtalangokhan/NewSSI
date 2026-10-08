import { renderHook } from "@testing-library/react";
import useTurksatSidebarTheme from "@/hooks/useTurksatSidebarTheme";
import { AppFocus } from "@/hooks/useAppFocus";
import type { AppFocusValue } from "@/hooks/appNavigation";

let mockCanvas: { company: string; mode: string; animate: boolean } | null;
let mockFocus: AppFocusValue;

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({ appBackgroundCanvas: mockCanvas }),
}));
jest.mock("@/hooks/useAppFocus", () => ({
  __esModule: true,
  AppFocus: jest.requireActual("@/hooks/useAppFocus").AppFocus,
  default: () => new AppFocus(mockFocus),
}));

describe("useTurksatSidebarTheme", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockCanvas = { company: "uydu", mode: "dark", animate: true };
    mockFocus = "new-session";
  });

  it("is on for a TÜRKSAT background on a chat surface", () => {
    const { result } = renderHook(() => useTurksatSidebarTheme());

    expect(result.current).toBe(true);
  });

  it("is off without a canvas background", () => {
    mockCanvas = null;

    const { result } = renderHook(() => useTurksatSidebarTheme());

    expect(result.current).toBe(false);
  });

  it("is off where the background is not painted", () => {
    mockFocus = { type: "project", id: "1" };

    const { result } = renderHook(() => useTurksatSidebarTheme());

    expect(result.current).toBe(false);
  });

  it("is off when the user switched it off", () => {
    window.localStorage.setItem("agentic_sidebar_background_theme", "off");

    const { result } = renderHook(() => useTurksatSidebarTheme());

    expect(result.current).toBe(false);
  });
});
