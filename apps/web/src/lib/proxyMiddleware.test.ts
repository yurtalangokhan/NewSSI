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
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("does not refresh or clear auth cookies for page requests", async () => {
    const fetchSpy = jest.spyOn(global, "fetch");

    const response = await proxy(
      requestWithCookie("refresh_token=stale; access_token=expired")
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(setCookieHeaders(response)).toEqual([]);
  });

  it("does not set refreshed cookies for page requests", async () => {
    const fetchSpy = jest.spyOn(global, "fetch");

    const response = await proxy(
      requestWithCookie("refresh_token=valid; access_token=expired")
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(setCookieHeaders(response)).toEqual([]);
  });
});
