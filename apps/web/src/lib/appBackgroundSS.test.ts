import { fetchAppBackgroundMetadata } from "./appBackgroundSS";
import { cookies } from "next/headers";
import { CHAT_BACKGROUND_COOKIE_NAME } from "./constants/chatBackgrounds";

jest.mock("next/headers", () => ({
  cookies: jest.fn(),
}));

describe("appBackgroundSS", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("prioritizes user.preferences.chat_background", async () => {
    const mockUser: any = {
      preferences: {
        chat_background: "mountains",
      },
    };

    const result = await fetchAppBackgroundMetadata(mockUser);
    expect(result.backgroundId).toBe("mountains");
    expect(result.backgroundOption?.id).toBe("mountains");
    expect(result.backgroundOption).toMatchObject({
      src: "/chat-backgrounds/mountains.jpg",
    });
    expect(cookies).not.toHaveBeenCalled();
  });

  it("falls back to cookie when user is null", async () => {
    (cookies as jest.Mock).mockResolvedValue({
      get: (name: string) =>
        name === CHAT_BACKGROUND_COOKIE_NAME ? { value: "night" } : undefined,
    });

    const result = await fetchAppBackgroundMetadata(null);
    expect(result.backgroundId).toBe("night");
    expect(result.backgroundOption?.id).toBe("night");
    expect(result.backgroundOption).toMatchObject({
      src: "/chat-backgrounds/night.jpg",
    });
  });

  it("resolves a canvas-kind background from the cookie", async () => {
    (cookies as jest.Mock).mockResolvedValue({
      get: (name: string) =>
        name === CHAT_BACKGROUND_COOKIE_NAME
          ? { value: "turksat-kablo" }
          : undefined,
    });

    const result = await fetchAppBackgroundMetadata(null);
    expect(result.backgroundId).toBe("turksat-kablo");
    expect(result.backgroundOption).toMatchObject({
      kind: "canvas",
      canvas: { company: "kablo" },
    });
  });

  it("returns null backgroundId when preference is none or cookie is none", async () => {
    const mockUser: any = {
      preferences: {
        chat_background: "none",
      },
    };
    (cookies as jest.Mock).mockResolvedValue({
      get: () => ({ value: "none" }),
    });

    const result = await fetchAppBackgroundMetadata(mockUser);
    expect(result.backgroundId).toBeNull();
    expect(result.backgroundOption).toMatchObject({ src: "none" });
  });

  it("handles cookies() throwing an exception safely", async () => {
    (cookies as jest.Mock).mockRejectedValue(new Error("No cookie context"));

    const result = await fetchAppBackgroundMetadata(null);
    expect(result.backgroundId).toBeNull();
    expect(result.backgroundOption).toMatchObject({ src: "none" });
  });
});
