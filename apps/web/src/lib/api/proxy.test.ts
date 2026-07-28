import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";

function responseWithHeaders(headers: Record<string, string>) {
  const response = new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers,
  });
  (response.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie =
    () => [];
  return response;
}

describe("proxyToBackend", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("does not forward hop-by-hop or body framing headers from upstream", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithHeaders({
        connection: "keep-alive",
        "keep-alive": "timeout=5",
        "transfer-encoding": "chunked",
        "content-length": "9999",
        "content-encoding": "gzip",
        "content-type": "application/json",
      })
    );

    const request = new NextRequest("http://localhost/api/auth/external/login", {
      method: "POST",
      body: new URLSearchParams([["username", "external@example.com"]]),
      headers: {
        "content-type": "application/x-www-form-urlencoded",
      },
    });

    const response = await proxyToBackend(request, "/api/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
    });

    expect(response.headers.get("connection")).toBeNull();
    expect(response.headers.get("keep-alive")).toBeNull();
    expect(response.headers.get("transfer-encoding")).toBeNull();
    expect(response.headers.get("content-length")).toBeNull();
    expect(response.headers.get("content-encoding")).toBeNull();
    expect(response.headers.get("content-type")).toBe("application/json");
  });

  it("merges explicit query params into the upstream request URL", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/auth/external/login?existing=1",
      {
        method: "POST",
        body: new URLSearchParams([["username", "external@example.com"]]),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
        },
      }
    );

    await proxyToBackend(request, "/api/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
      queryParams: {
        redirect_uri: "http://localhost:3000/auth/oidc/callback",
      },
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://user-service/api/auth/external/login?existing=1&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Foidc%2Fcallback",
      expect.any(Object)
    );
  });
});
