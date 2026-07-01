/**
 * @jest-environment jsdom
 */

import {
  authenticatedFetch,
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

  it("redirects to the 401 error page when no refresh token is available", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(400));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[Auth] No refresh token available, redirecting to error page"
    );
  });

  it("redirects to the 401 error page when the retried request is still unauthorized", async () => {
    fetchMock()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(401));

    await expect(authenticatedFetch("/api/me")).rejects.toBeInstanceOf(
      RedirectError
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[Auth] Unauthorized after token refresh"
    );
  });
});
