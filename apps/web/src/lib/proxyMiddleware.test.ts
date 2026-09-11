import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

function makeJwt(expOffsetSeconds: number): string {
  const payload = Buffer.from(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expOffsetSeconds })
  )
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${payload}.signature`;
}

function requestWithCookie(
  cookie: string,
  init: { method?: string; headers?: Record<string, string>; url?: string } = {}
) {
  return new NextRequest(init.url ?? "http://localhost/app", {
    method: init.method ?? "GET",
    headers: {
      cookie,
      ...(init.headers ?? {}),
    },
  });
}

function setCookieHeaders(response: Response): string[] {
  const getSetCookie = (
    response.headers as Headers & {
      getSetCookie?: () => string[];
    }
  ).getSetCookie;
  return getSetCookie ? getSetCookie.call(response.headers) : [];
}

function refreshResponse(setCookies: string[]): Response {
  const headers = new Headers();
  setCookies.forEach((cookie) => headers.append("set-cookie", cookie));
  return new Response(JSON.stringify({ access_token: "new" }), {
    status: 200,
    headers,
  });
}

describe("proxy middleware auth refresh", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("does not refresh when the access token is still valid", async () => {
    const fetchSpy = jest.spyOn(global, "fetch");

    const response = await proxy(
      requestWithCookie(`refresh_token=valid; access_token=${makeJwt(600)}`)
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(setCookieHeaders(response)).toEqual([]);
  });

  it("does not refresh when there is no refresh token", async () => {
    const fetchSpy = jest.spyOn(global, "fetch");

    const response = await proxy(
      requestWithCookie(`access_token=${makeJwt(-60)}`)
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(setCookieHeaders(response)).toEqual([]);
  });

  it("refreshes and forwards the new cookies when the access token expired", async () => {
    const fetchSpy = jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        refreshResponse([
          "access_token=fresh-access; Path=/; HttpOnly",
          "refresh_token=fresh-refresh; Path=/; HttpOnly",
        ])
      );

    const response = await proxy(
      requestWithCookie(`refresh_token=valid; access_token=${makeJwt(-60)}`)
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain("/api/v1/auth/refresh");
    expect((init as RequestInit).method).toBe("POST");

    expect(setCookieHeaders(response)).toEqual([
      "access_token=fresh-access; Path=/; HttpOnly",
      "refresh_token=fresh-refresh; Path=/; HttpOnly",
    ]);
  });

  it("refreshes when the access token cookie is gone but the refresh token remains", async () => {
    const fetchSpy = jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        refreshResponse(["access_token=fresh-access; Path=/; HttpOnly"])
      );

    await proxy(requestWithCookie("refresh_token=valid"));

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("preserves auth cookies when a stale concurrent refresh is rejected", async () => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }));

    const response = await proxy(
      requestWithCookie(`refresh_token=stale; access_token=${makeJwt(-60)}`)
    );

    expect(setCookieHeaders(response)).toEqual([]);
  });

  it("leaves the session alone when the auth backend is unreachable", async () => {
    jest
      .spyOn(global, "fetch")
      .mockRejectedValueOnce(new Error("ECONNREFUSED"));
    jest.spyOn(console, "error").mockImplementation(() => {});

    const response = await proxy(
      requestWithCookie(`refresh_token=valid; access_token=${makeJwt(-60)}`)
    );

    expect(setCookieHeaders(response)).toEqual([]);
  });

  it("does not spend the refresh token on router prefetches", async () => {
    const fetchSpy = jest.spyOn(global, "fetch");

    await proxy(
      requestWithCookie(`refresh_token=valid; access_token=${makeJwt(-60)}`, {
        headers: { "next-router-prefetch": "1" },
      })
    );

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("does not refresh on the logout route", async () => {
    const fetchSpy = jest.spyOn(global, "fetch");

    await proxy(
      requestWithCookie(`refresh_token=valid; access_token=${makeJwt(-60)}`, {
        url: "http://localhost/auth/logout",
      })
    );

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
