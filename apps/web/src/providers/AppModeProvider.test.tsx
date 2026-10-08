import React from "react";
import { act, renderHook } from "@testing-library/react";

import {
  AppModeProvider,
  appModeFromPreference,
  useAppMode,
  useStartNewSessionOnEntry,
} from "@/providers/AppModeProvider";

const mockUseUser = jest.fn();
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => mockUseUser(),
}));

const mockUseSettings = jest.fn();
jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => mockUseSettings(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  return <AppModeProvider>{children}</AppModeProvider>;
}

function givenUser(defaultAppMode?: "AUTO" | "CHAT" | "SEARCH") {
  mockUseUser.mockReturnValue({
    user: defaultAppMode
      ? { preferences: { default_app_mode: defaultAppMode } }
      : null,
  });
}

describe("appModeFromPreference", () => {
  it.each([
    ["SEARCH", "search"],
    ["CHAT", "chat"],
    ["AUTO", "chat"],
    [undefined, "chat"],
  ] as const)("maps %s to %s", (preference, mode) => {
    expect(appModeFromPreference(preference)).toBe(mode);
  });
});

describe("AppModeProvider", () => {
  beforeEach(() => {
    mockUseSettings.mockReturnValue({ isSearchModeAvailable: true });
    givenUser();
  });

  it("starts in chat and switches to search", () => {
    const { result } = renderHook(() => useAppMode(), { wrapper });

    expect(result.current.appMode).toBe("chat");
    expect(result.current.isSearchAvailable).toBe(true);

    act(() => result.current.setAppMode("search"));

    expect(result.current.appMode).toBe("search");
  });

  it("opens in the user's persisted search preference", () => {
    givenUser("SEARCH");

    const { result } = renderHook(() => useAppMode(), { wrapper });

    expect(result.current.appMode).toBe("search");
  });

  it("stays in chat when search is unavailable", () => {
    mockUseSettings.mockReturnValue({ isSearchModeAvailable: false });
    givenUser("SEARCH");

    const { result } = renderHook(() => useAppMode(), { wrapper });
    act(() => result.current.setAppMode("search"));

    expect(result.current.appMode).toBe("chat");
    expect(result.current.isSearchAvailable).toBe(false);
  });

  it("falls back to chat when search becomes unavailable", () => {
    const { result, rerender } = renderHook(() => useAppMode(), { wrapper });
    act(() => result.current.setAppMode("search"));

    mockUseSettings.mockReturnValue({ isSearchModeAvailable: false });
    rerender();

    expect(result.current.appMode).toBe("chat");
  });

  it("renders the persisted preference on the very first render", () => {
    givenUser("SEARCH");
    const rendered: string[] = [];

    renderHook(
      () => {
        const { appMode } = useAppMode();
        rendered.push(appMode);
      },
      { wrapper }
    );

    // No chat frame that flips to search afterwards (that would fade twice).
    expect(rendered.every((mode) => mode === "search")).toBe(true);
  });

  it("follows a preference that loads after the first render", () => {
    const { result, rerender } = renderHook(() => useAppMode(), { wrapper });
    expect(result.current.appMode).toBe("chat");

    givenUser("SEARCH");
    rerender();

    expect(result.current.appMode).toBe("search");
  });

  it("keeps the user's explicit choice over the preference", () => {
    givenUser("SEARCH");
    const { result, rerender } = renderHook(() => useAppMode(), { wrapper });

    act(() => result.current.setAppMode("chat"));
    rerender();

    expect(result.current.appMode).toBe("chat");
  });

  it("starts a new session in the preferred mode with a fresh search view", () => {
    givenUser("SEARCH");
    const { result } = renderHook(() => useAppMode(), { wrapper });
    act(() => result.current.setAppMode("chat"));
    const initialKey = result.current.searchSessionKey;

    act(() => result.current.startNewSession());

    expect(result.current.appMode).toBe("search");
    expect(result.current.searchSessionKey).toBe(initialKey + 1);
  });

  it("starts a new session in chat when the preference is chat", () => {
    givenUser("CHAT");
    const { result } = renderHook(() => useAppMode(), { wrapper });
    act(() => result.current.setAppMode("search"));

    act(() => result.current.startNewSession());

    expect(result.current.appMode).toBe("chat");
  });

  it("defaults to chat outside the provider", () => {
    const { result } = renderHook(() => useAppMode());

    expect(result.current.appMode).toBe("chat");
    expect(result.current.isSearchAvailable).toBe(false);
  });
});

describe("useStartNewSessionOnEntry", () => {
  beforeEach(() => {
    mockUseSettings.mockReturnValue({ isSearchModeAvailable: true });
    givenUser("SEARCH");
  });

  function renderEntry(isNewSession: boolean) {
    return renderHook(
      ({ isNew }: { isNew: boolean }) => {
        useStartNewSessionOnEntry(isNew);
        return useAppMode();
      },
      { wrapper, initialProps: { isNew: isNewSession } }
    );
  }

  it("resets the mode to the preference when a new session is entered", () => {
    const { result, rerender } = renderEntry(false);
    act(() => result.current.setAppMode("chat"));

    rerender({ isNew: true });

    expect(result.current.appMode).toBe("search");
  });

  it("does not restart the search page when a new session is entered", () => {
    const { result, rerender } = renderEntry(false);
    const keyBefore = result.current.searchSessionKey;
    act(() => result.current.setAppMode("chat"));

    rerender({ isNew: true });

    expect(result.current.searchSessionKey).toBe(keyBefore);
  });

  it("leaves the user's choice alone outside a new session", () => {
    const { result, rerender } = renderEntry(false);
    act(() => result.current.setAppMode("chat"));

    rerender({ isNew: false });

    expect(result.current.appMode).toBe("chat");
  });
});
