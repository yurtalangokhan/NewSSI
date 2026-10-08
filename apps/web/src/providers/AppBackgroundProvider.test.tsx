import React from "react";
import { renderHook } from "@testing-library/react";
import {
  AppBackgroundProvider,
  useAppBackground,
} from "./AppBackgroundProvider";
import * as chatBackgroundClient from "@/lib/chatBackgroundClient";

// Mock UserProvider
const mockUseUser = jest.fn();
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => mockUseUser(),
}));

// Mock next-themes: the resolved color mode drives canvas-kind backgrounds
let mockResolvedTheme: string | undefined = "light";
jest.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: mockResolvedTheme }),
}));

// Mock chatBackgroundClient
jest.mock("@/lib/chatBackgroundClient", () => ({
  getChatBackgroundCookie: jest.fn(),
  setChatBackgroundCookie: jest.fn(),
  clearChatBackgroundCookie: jest.fn(),
  preloadChatBackgroundImage: jest.fn(),
}));

describe("AppBackgroundProvider", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockResolvedTheme = "light";
    window.localStorage.clear();
    mockUseUser.mockReturnValue({ user: null });
    (chatBackgroundClient.getChatBackgroundCookie as jest.Mock).mockReturnValue(
      null
    );
  });

  it("defaults to no background when user has no preference and no initialBackgroundId", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AppBackgroundProvider>{children}</AppBackgroundProvider>
    );

    const { result } = renderHook(() => useAppBackground(), { wrapper });

    expect(result.current.hasBackground).toBe(false);
    expect(result.current.appBackgroundUrl).toBeNull();
  });

  it("immediately uses initialBackgroundId before user finishes loading (zero hydration flash)", () => {
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AppBackgroundProvider initialBackgroundId="mountains">
        {children}
      </AppBackgroundProvider>
    );

    const { result } = renderHook(() => useAppBackground(), { wrapper });

    expect(result.current.hasBackground).toBe(true);
    expect(result.current.appBackgroundUrl).toBe(
      "/chat-backgrounds/mountains.jpg"
    );
    expect(result.current.appBackground?.id).toBe("mountains");
    expect(result.current.foregroundTextClass).toBe("text-text-light-05");
    expect(
      chatBackgroundClient.preloadChatBackgroundImage
    ).toHaveBeenCalledWith("/chat-backgrounds/mountains.jpg");
  });

  it("reads from client cookie if user is null and no initialBackgroundId was provided", () => {
    (chatBackgroundClient.getChatBackgroundCookie as jest.Mock).mockReturnValue(
      "clouds"
    );

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <AppBackgroundProvider>{children}</AppBackgroundProvider>
    );

    const { result } = renderHook(() => useAppBackground(), { wrapper });

    expect(result.current.hasBackground).toBe(true);
    expect(result.current.appBackgroundUrl).toBe(
      "/chat-backgrounds/clouds.jpg"
    );
    expect(result.current.foregroundTextClass).toBe("text-text-dark-05");
  });

  it("updates background and sets cookie when user preferences change", () => {
    let currentUser: any = {
      preferences: { chat_background: null },
    };
    mockUseUser.mockImplementation(() => ({ user: currentUser }));

    const { result, rerender } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.hasBackground).toBe(false);

    // User selects a new background
    currentUser = {
      preferences: { chat_background: "night" },
    };
    rerender();

    expect(result.current.hasBackground).toBe(true);
    expect(result.current.appBackgroundUrl).toBe("/chat-backgrounds/night.jpg");
    expect(chatBackgroundClient.setChatBackgroundCookie).toHaveBeenCalledWith(
      "night"
    );
  });

  it("resolves a canvas-kind background without a URL, and does not preload an image", () => {
    mockResolvedTheme = "dark";
    mockUseUser.mockImplementation(() => ({
      user: { preferences: { chat_background: "turksat-uydu" } },
    }));

    const { result } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.hasBackground).toBe(true);
    expect(result.current.appBackgroundUrl).toBeNull();
    expect(result.current.appBackgroundCanvas).toEqual({
      company: "uydu",
      mode: "dark",
      animate: true,
    });
    expect(result.current.appBackground?.isDarkBackground).toBe(true);
    expect(result.current.foregroundTextClass).toBe("text-text-light-05");
    expect(
      chatBackgroundClient.preloadChatBackgroundImage
    ).not.toHaveBeenCalled();
  });

  it("renders a canvas-kind background in light mode when the resolved theme is light", () => {
    mockUseUser.mockImplementation(() => ({
      user: { preferences: { chat_background: "turksat-kablo" } },
    }));

    const { result } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.appBackgroundCanvas).toEqual({
      company: "kablo",
      mode: "light",
      animate: true,
    });
    expect(result.current.appBackground?.isDarkBackground).toBe(false);
    expect(result.current.foregroundTextClass).toBe("text-text-dark-05");
  });

  it("switches a canvas-kind background's mode when the color mode changes", () => {
    mockUseUser.mockImplementation(() => ({
      user: { preferences: { chat_background: "turksat-bilisim" } },
    }));

    const { result, rerender } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });
    expect(result.current.appBackgroundCanvas?.mode).toBe("light");

    mockResolvedTheme = "dark";
    rerender();

    expect(result.current.appBackgroundCanvas?.mode).toBe("dark");
  });

  it("keeps a photo background's own darkness regardless of the color mode", () => {
    mockResolvedTheme = "light";
    mockUseUser.mockImplementation(() => ({
      user: { preferences: { chat_background: "mountains" } },
    }));

    const { result } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.appBackgroundCanvas).toBeNull();
    expect(result.current.foregroundTextClass).toBe("text-text-light-05");
  });

  it("clears appBackgroundCanvas when switching from a canvas to an image background", () => {
    let currentUser: any = {
      preferences: { chat_background: "turksat-bilisim" },
    };
    mockUseUser.mockImplementation(() => ({ user: currentUser }));

    const { result, rerender } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.appBackgroundCanvas).toEqual({
      company: "bilisim",
      mode: "light",
      animate: true,
    });

    currentUser = { preferences: { chat_background: "mountains" } };
    rerender();

    expect(result.current.appBackgroundCanvas).toBeNull();
    expect(result.current.appBackgroundUrl).toBe(
      "/chat-backgrounds/mountains.jpg"
    );
  });

  it("clears cookie when user selects none", () => {
    let currentUser: any = {
      preferences: { chat_background: "mountains" },
    };
    mockUseUser.mockImplementation(() => ({ user: currentUser }));

    const { result, rerender } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.hasBackground).toBe(true);

    // User selects "none"
    currentUser = {
      preferences: { chat_background: "none" },
    };
    rerender();

    expect(result.current.hasBackground).toBe(false);
    expect(chatBackgroundClient.clearChatBackgroundCookie).toHaveBeenCalled();
  });

  it("stops the canvas scene animating when the user turned background animation off", () => {
    window.localStorage.setItem("agentic_background_animation", "off");
    mockUseUser.mockImplementation(() => ({
      user: { preferences: { chat_background: "turksat-bilisim" } },
    }));

    const { result } = renderHook(() => useAppBackground(), {
      wrapper: ({ children }) => (
        <AppBackgroundProvider>{children}</AppBackgroundProvider>
      ),
    });

    expect(result.current.appBackgroundCanvas).toMatchObject({
      company: "bilisim",
      animate: false,
    });
  });
});
