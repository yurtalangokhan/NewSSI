/**
 * @jest-environment jsdom
 */

import {
  authenticatedFetch,
  errorHandlingFetcher,
  getSessionExpiredRedirectUrl,
  clearAuthRefreshFailed,
  getLoginRedirectUrl,
  RedirectError,
} from "@/lib/fetcher";
import i18n from "@/i18n/config";

function response(status: number) {
  return new Response(status === 204 ? null : "{}", {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchMock() {
  return global.fetch as jest.MockedFunction<typeof fetch>;
}

describe("authenticatedFetch", () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleErrorSpy = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    jest.spyOn(console, "log").mockImplementation(() => undefined);
    global.fetch = jest.fn();
    window.history.replaceState({}, "", "/app?view=chat");
    window.sessionStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("refreshes the access token and retries the original request", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200));

    const result = await authenticatedFetch("/api/me");

    expect(result.status).toBe(200);
    expect(fetchMock()).toHaveBeenNthCalledWith(1, "/api/me", {
      credentials: "include",
    });
    expect(fetchMock()).toHaveBeenNthCalledWith(2, "/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    expect(fetchMock()).toHaveBeenNthCalledWith(3, "/api/me", {
      credentials: "include",
    });
  });

  it("notifies the browser after refreshing the access token", async () => {
    const refreshListener = jest.fn();
    window.addEventListener("auth:session-refreshed", refreshListener);
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200));

    await authenticatedFetch("/api/me");

    expect(refreshListener).toHaveBeenCalledTimes(1);
    window.removeEventListener("auth:session-refreshed", refreshListener);
  });

  it("redirects to login when refresh token is expired or invalid", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(401))
      // /api/auth/type
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    fetchMock().mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));
    await expect(getLoginRedirectUrl()).resolves.toBe(
      `/auth/ee/login?next=${encodeURIComponent("/app?view=chat")}`
    );
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[Auth] Session expired, redirecting to login"
    );
  });

  it("routes expired sessions through logout before returning to login", async () => {
    fetchMock().mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(getSessionExpiredRedirectUrl()).resolves.toBe(
      `/auth/logout?next=${encodeURIComponent(
        `/auth/ee/login?next=${encodeURIComponent("/app?view=chat")}`
      )}`
    );
  });

  it("does not reload when already on the resolved login page", async () => {
    window.history.replaceState({}, "", "/auth/ee/login?next=%2Fapp");
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(400))
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    expect(window.location.pathname).toBe("/auth/ee/login");
    expect(window.location.search).toBe("?next=%2Fapp");
  });

  it("redirects to login when no refresh token is available", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(400))
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[Auth] Session expired, redirecting to login"
    );
  });

  it("does not retry refresh after a refresh failure in the same browser session", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(400))
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    expect(fetchMock()).toHaveBeenCalledTimes(5);
    expect(fetchMock()).toHaveBeenNthCalledWith(1, "/api/me", {
      credentials: "include",
    });
    expect(fetchMock()).toHaveBeenNthCalledWith(2, "/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    expect(fetchMock()).toHaveBeenNthCalledWith(4, "/api/me", {
      credentials: "include",
    });
    expect(fetchMock()).toHaveBeenNthCalledWith(5, "/api/auth/type", {
      credentials: "include",
      cache: "no-store",
    });
  });

  it("retries refresh again after a successful login clears the refresh failure marker", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(400))
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    clearAuthRefreshFailed();

    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200));

    const result = await authenticatedFetch("/api/me");

    expect(result.status).toBe(200);
    expect(fetchMock()).toHaveBeenNthCalledWith(5, "/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
  });

  it("returns auth errors without redirecting when redirectOnAuthError is disabled", async () => {
    fetchMock().mockResolvedValueOnce(response(401));

    const result = await authenticatedFetch("/api/me", {
      redirectOnAuthError: false,
    });

    expect(result.status).toBe(401);
    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(fetchMock()).toHaveBeenCalledWith("/api/me", {
      credentials: "include",
    });
  });

  it("redirects to login when the retried request is still unauthorized", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(jsonResponse({ externalKeycloak: true }));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[Auth] Unauthorized after token refresh"
    );
  });

  it("attaches an Idempotency-Key to mutating requests", async () => {
    fetchMock().mockResolvedValueOnce(response(200));

    await authenticatedFetch("/api/chat/send", { method: "POST" });

    const init = fetchMock().mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    const key = headers.get("Idempotency-Key");
    expect(key).toBeTruthy();
    expect(key!.length).toBeGreaterThanOrEqual(8);
  });

  it("does not attach an Idempotency-Key to GET requests", async () => {
    fetchMock().mockResolvedValueOnce(response(200));

    await authenticatedFetch("/api/me");

    const init = fetchMock().mock.calls[0]?.[1];
    expect(new Headers(init?.headers).has("Idempotency-Key")).toBe(false);
  });

  it("preserves a caller-provided Idempotency-Key", async () => {
    fetchMock().mockResolvedValueOnce(response(200));

    await authenticatedFetch("/api/chat/send", {
      method: "POST",
      headers: { "Idempotency-Key": "client-key-123" },
    });

    const init = fetchMock().mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe(
      "client-key-123"
    );
  });

  it("does not attach an Idempotency-Key to auth endpoints", async () => {
    fetchMock().mockResolvedValueOnce(response(200));

    await authenticatedFetch("/api/auth/login", { method: "POST" });

    const init = fetchMock().mock.calls[0]?.[1];
    expect(new Headers(init?.headers).has("Idempotency-Key")).toBe(false);
  });

  it("reuses the same Idempotency-Key when retrying after token refresh", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200));

    await authenticatedFetch("/api/chat/send", { method: "POST" });

    const firstKey = new Headers(fetchMock().mock.calls[0]?.[1]?.headers).get(
      "Idempotency-Key"
    );
    const retriedKey = new Headers(fetchMock().mock.calls[2]?.[1]?.headers).get(
      "Idempotency-Key"
    );
    expect(firstKey).toBeTruthy();
    expect(retriedKey).toBe(firstKey);
  });
});

describe("errorHandlingFetcher", () => {
  const originalLanguage = i18n.language;

  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue(jsonResponse({ ok: true }));
  });

  afterEach(async () => {
    jest.restoreAllMocks();
    await i18n.changeLanguage(originalLanguage);
  });

  it("sends the app's currently selected language, not just the browser's", async () => {
    await i18n.changeLanguage("tr");

    await errorHandlingFetcher("/api/agents/catalog");

    expect(fetchMock()).toHaveBeenCalledWith(
      "/api/agents/catalog",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Language": "tr" }),
      })
    );
  });

  it("updates the header when the selected language changes", async () => {
    await i18n.changeLanguage("en");
    await errorHandlingFetcher("/api/agents/catalog");
    expect(fetchMock()).toHaveBeenLastCalledWith(
      "/api/agents/catalog",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Language": "en" }),
      })
    );

    await i18n.changeLanguage("tr");
    await errorHandlingFetcher("/api/agents/catalog");
    expect(fetchMock()).toHaveBeenLastCalledWith(
      "/api/agents/catalog",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Language": "tr" }),
      })
    );
  });
});
