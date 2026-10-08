/**
 * @jest-environment jsdom
 */
import Cookies from "js-cookie";
import {
  getChatBackgroundCookie,
  setChatBackgroundCookie,
  clearChatBackgroundCookie,
  preloadChatBackgroundImage,
} from "./chatBackgroundClient";
import { CHAT_BACKGROUND_COOKIE_NAME } from "./constants/chatBackgrounds";

jest.mock("js-cookie", () => ({
  get: jest.fn(),
  set: jest.fn(),
  remove: jest.fn(),
}));

describe("chatBackgroundClient", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("getChatBackgroundCookie", () => {
    it("returns null if cookie is not set or empty", () => {
      (Cookies.get as jest.Mock).mockReturnValue(undefined);
      expect(getChatBackgroundCookie()).toBeNull();
    });

    it("returns null if cookie value is 'none'", () => {
      (Cookies.get as jest.Mock).mockReturnValue("none");
      expect(getChatBackgroundCookie()).toBeNull();
    });

    it("returns the saved background ID", () => {
      (Cookies.get as jest.Mock).mockReturnValue("mountains");
      expect(getChatBackgroundCookie()).toBe("mountains");
    });
  });

  describe("setChatBackgroundCookie", () => {
    it("sets cookie with 365 days expiration and lax sameSite", () => {
      setChatBackgroundCookie("night");
      expect(Cookies.set).toHaveBeenCalledWith(
        CHAT_BACKGROUND_COOKIE_NAME,
        "night",
        {
          expires: 365,
          path: "/",
          sameSite: "lax",
        }
      );
    });

    it("clears cookie if backgroundId is 'none' or falsy", () => {
      setChatBackgroundCookie("none");
      expect(Cookies.remove).toHaveBeenCalledWith(CHAT_BACKGROUND_COOKIE_NAME, {
        path: "/",
      });
    });
  });

  describe("clearChatBackgroundCookie", () => {
    it("removes cookie with root path", () => {
      clearChatBackgroundCookie();
      expect(Cookies.remove).toHaveBeenCalledWith(CHAT_BACKGROUND_COOKIE_NAME, {
        path: "/",
      });
    });
  });

  describe("preloadChatBackgroundImage", () => {
    it("creates an Image and sets src for a valid background ID", () => {
      const originalImage = global.Image;
      const mockImageInstances: any[] = [];

      global.Image = class {
        src = "";
        constructor() {
          mockImageInstances.push(this);
        }
      } as any;

      try {
        preloadChatBackgroundImage("mountains");
        expect(mockImageInstances).toHaveLength(1);
        expect(mockImageInstances[0].src).toBe(
          "/chat-backgrounds/mountains.jpg"
        );

        // When "none" or null, it should not preload
        preloadChatBackgroundImage("none");
        preloadChatBackgroundImage(null);
        expect(mockImageInstances).toHaveLength(1);
      } finally {
        global.Image = originalImage;
      }
    });

    it("supports direct image url", () => {
      const originalImage = global.Image;
      const mockImageInstances: any[] = [];

      global.Image = class {
        src = "";
        constructor() {
          mockImageInstances.push(this);
        }
      } as any;

      try {
        preloadChatBackgroundImage("/chat-backgrounds/custom.jpg");
        expect(mockImageInstances).toHaveLength(1);
        expect(mockImageInstances[0].src).toBe("/chat-backgrounds/custom.jpg");
      } finally {
        global.Image = originalImage;
      }
    });

    it("does not construct an Image for a canvas-kind background", () => {
      const originalImage = global.Image;
      const mockImageInstances: any[] = [];

      global.Image = class {
        src = "";
        constructor() {
          mockImageInstances.push(this);
        }
      } as any;

      try {
        preloadChatBackgroundImage("turksat-uydu");
        expect(mockImageInstances).toHaveLength(0);
      } finally {
        global.Image = originalImage;
      }
    });
  });
});
