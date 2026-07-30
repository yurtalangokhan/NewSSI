import { NextRequest } from "next/server";
import { proxy } from "@/proxy";

function requestWithCookie(cookie: string) {
  return new NextRequest("http://localhost/app", {
    headers: {
      cookie,
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

describe("proxy middleware auth refresh", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("clears auth cookies when refresh token is invalid", async () => {
    jest.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "invalid refresh token" }), {
        status: 400,
        headers: {
          "Content-Type": "application/json",
        },
      })
    );

    const response = await proxy(
      requestWithCookie("refresh_token=stale; access_token=expired")
    );

    const cookies = setCookieHeaders(response);
    expect(cookies).toEqual(
      expect.arrayContaining([
        expect.stringContaining("refresh_token=;"),
        expect.stringContaining("access_token=;"),
        expect.stringContaining("id_token=;"),
      ])
    );
  });

  it("forwards refreshed cookies when refresh succeeds", async () => {
    jest.mocked(fetch).mockResolvedValueOnce(
      new Response("{}", {
        status: 200,
        headers: {
          "Set-Cookie": "access_token=fresh; Path=/; HttpOnly",
        },
      })
    );

    const response = await proxy(
      requestWithCookie("refresh_token=valid; access_token=expired")
    );

    expect(setCookieHeaders(response)).toEqual(
      expect.arrayContaining([expect.stringContaining("access_token=fresh")])
    );
  });
});
