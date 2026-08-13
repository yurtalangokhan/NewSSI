/**
 * @jest-environment jsdom
 */

import i18n from "@/i18n/config";
import {
  basicLogin,
  externalKeycloakLogin,
  getCurrentUser,
  ldapLogin,
} from "@/lib/user";

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
    fetchMock().mockResolvedValueOnce(response(401));

    await expect(getCurrentUser()).resolves.toBeNull();

    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(fetchMock()).toHaveBeenCalledWith("/api/me", {
      credentials: "include",
    });
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
  });

  it("basicLogin sends X-Language matching the app's i18n language, not just relying on the browser's Accept-Language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    fetchMock().mockResolvedValueOnce(response(200));

    await basicLogin("user", "pass");

    const [, init] = fetchMock().mock.calls[0]!;
    expect((init?.headers as Record<string, string>)["X-Language"]).toBe(
      "tr"
    );
  });

  it("externalKeycloakLogin sends X-Language matching the app's i18n language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    fetchMock().mockResolvedValueOnce(response(200));

    await externalKeycloakLogin("user", "pass");

    const [, init] = fetchMock().mock.calls[0]!;
    expect((init?.headers as Record<string, string>)["X-Language"]).toBe(
      "tr"
    );
  });

  it("ldapLogin sends X-Language matching the app's i18n language", async () => {
    Object.defineProperty(i18n, "language", {
      value: "tr",
      configurable: true,
    });
    fetchMock().mockResolvedValueOnce(response(200));

    await ldapLogin("user", "pass");

    const [, init] = fetchMock().mock.calls[0]!;
    expect((init?.headers as Record<string, string>)["X-Language"]).toBe(
      "tr"
    );
  });
});
