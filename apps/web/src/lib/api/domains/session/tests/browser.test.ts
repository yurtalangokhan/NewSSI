/**
 * @jest-environment jsdom
 */

import i18n from "@/i18n/config";
import { setClientLanguage } from "@/i18n/languageState";
import {
  basicLogin,
  externalKeycloakLogin,
  fetchCurrentUserOrNull as getCurrentUser,
} from "@/lib/api/domains/session/api";

function response(status: number) {
  return new Response(status === 204 ? null : "{}", {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchMock() {
  return global.fetch as jest.MockedFunction<typeof fetch>;
}

describe("getCurrentUser", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    window.history.replaceState({}, "", "/app");
    window.sessionStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("returns null on unauthorized responses without starting auth redirects", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(401));

    await expect(getCurrentUser()).resolves.toBeNull();

    expect(fetchMock()).toHaveBeenCalledTimes(2);
    expect(fetchMock()).toHaveBeenNthCalledWith(
      1,
      "/api/me",
      expect.objectContaining({ credentials: "include" })
    );
    expect(fetchMock()).toHaveBeenNthCalledWith(
      2,
      "/api/auth/refresh",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });
});

describe("login requests send the app's selected language", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
    Object.defineProperty(i18n, "language", {
      value: originalLanguage,
      configurable: true,
    });
    setClientLanguage(originalLanguage);
  });

  it("basicLogin sends X-Language matching the app's i18n language, not just relying on the browser's Accept-Language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    setClientLanguage("tr");
    fetchMock().mockResolvedValueOnce(response(200));

    await basicLogin("user", "pass");

    const [, init] = fetchMock().mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Language")).toBe("tr");
  });

  it("returns failed public login responses without refreshing the session", async () => {
    fetchMock().mockResolvedValueOnce(response(401));

    await expect(basicLogin("user", "wrong-pass")).resolves.toMatchObject({
      status: 401,
    });

    expect(fetchMock()).toHaveBeenCalledTimes(1);
  });

  it("externalKeycloakLogin sends X-Language matching the app's i18n language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    setClientLanguage("tr");
    fetchMock().mockResolvedValueOnce(response(200));

    await externalKeycloakLogin("user", "pass");

    const [, init] = fetchMock().mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Language")).toBe("tr");
  });
});
