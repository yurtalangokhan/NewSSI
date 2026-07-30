/**
 * @jest-environment jsdom
 */

import {
  authenticatedFetch,
  getSessionExpiredRedirectUrl,
  clearAuthRefreshFailed,
  getLoginRedirectUrl,
  RedirectError,
} from "@/lib/fetcher";

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
});
