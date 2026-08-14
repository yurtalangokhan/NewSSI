import { NextRequest } from "next/server";
import { getLanguageHeaders, proxyToBackend } from "@/lib/api/proxy";

function responseWithHeaders(headers: Record<string, string>) {
  const response = new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers,
  });
  (
    response.headers as Headers & { getSetCookie?: () => string[] }
  ).getSetCookie = () => [];
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

    const request = new NextRequest(
      "http://localhost/api/auth/external/login",
      {
        method: "POST",
        body: new URLSearchParams([["username", "external@example.com"]]),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
        },
      }
    );

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

  it("forwards set-cookie when the runtime exposes only the standard header accessor", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "set-cookie":
            "access_token=sp-access-token; Path=/; HttpOnly; SameSite=lax",
        },
      })
    );

    const request = new NextRequest(
      "http://localhost/api/auth/external/login",
      {
        method: "POST",
        body: new URLSearchParams([["username", "external@example.com"]]),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
        },
      }
    );

    const response = await proxyToBackend(request, "/api/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain(
      "access_token=sp-access-token"
    );
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
      "http://user-service/api/v1/auth/external/login?existing=1&redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Foidc%2Fcallback",
      expect.any(Object)
    );
  });

  it("adds service scope when proxying through Kong", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/chat/get-user-chat-sessions"
    );

    await proxyToBackend(request, "/api/chat/get-user-chat-sessions", {
      backendUrl: "http://kong:8000",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/agent-service/api/v1/chat/get-user-chat-sessions",
      expect.any(Object)
    );
  });

  it("forwards idempotency keys for mutating requests", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        method: "POST",
        body: JSON.stringify({ message: "retryable" }),
        headers: {
          "content-type": "application/json",
          "idempotency-key": "idem-web-123",
        },
      }
    );

    await proxyToBackend(request, "/api/chat/send-chat-message", {
      method: "POST",
      backendUrl: "http://kong:8000",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/agent-service/api/v1/chat/send-chat-message",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "idem-web-123",
        }),
      })
    );
  });

  it("does not forward idempotency keys for read-only requests", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/chat/get-user-chat-sessions",
      {
        headers: {
          "idempotency-key": "idem-web-123",
        },
      }
    );

    await proxyToBackend(request, "/api/chat/get-user-chat-sessions", {
      backendUrl: "http://kong:8000",
    });

    expect(fetchSpy.mock.calls[0][1].headers).toEqual(
      expect.not.objectContaining({
        "Idempotency-Key": expect.any(String),
      })
    );
  });

  it.each([
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/oidc/callback",
    "/api/auth/external/login",
  ])("does not forward idempotency keys to auth route %s", async (pathname) => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(`http://localhost${pathname}`, {
      method: "POST",
      body: new URLSearchParams([["username", "auth@example.com"]]),
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "idempotency-key": "auth-key",
      },
    });

    await proxyToBackend(request, pathname, {
      method: "POST",
      backendUrl: "http://user-service",
    });

    expect(fetchSpy.mock.calls[0][1].headers).toEqual(
      expect.not.objectContaining({
        "Idempotency-Key": expect.any(String),
      })
    );
  });

  it("does not refresh before proxying when only a refresh token remains", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "missing access token" }), {
        status: 401,
        headers: {
          "content-type": "application/json",
        },
      })
    );

    const request = new NextRequest("http://localhost/api/rag/collections", {
      headers: {
        cookie: "refresh_token=valid-refresh",
      },
    });

    const response = await proxyToBackend(request, "/collections", {
      backendUrl: "http://kong:8000/rag-service",
      backendService: "rag",
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/rag-service/api/v1/collections",
      expect.objectContaining({
        headers: expect.objectContaining({
          Cookie: "refresh_token=valid-refresh",
        }),
      })
    );
    expect(fetchSpy.mock.calls[0][1].headers).toEqual(
      expect.not.objectContaining({
        Authorization: expect.any(String),
      })
    );
  });

  it("does not refresh after a backend 401 when unauthorized refresh is disabled", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "expired token" }), {
        status: 401,
        headers: {
          "content-type": "application/json",
        },
      })
    );

    const request = new NextRequest("http://localhost/api/rag/collections", {
      headers: {
        cookie: "access_token=expired-access; refresh_token=valid-refresh",
      },
    });

    const response = await proxyToBackend(request, "/collections", {
      backendUrl: "http://kong:8000/rag-service",
      backendService: "rag",
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/rag-service/api/v1/collections",
      expect.any(Object)
    );
  });

  it("does not refresh after a backend 401 by default", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "expired token" }), {
        status: 401,
        headers: {
          "content-type": "application/json",
        },
      })
    );

    const request = new NextRequest("http://localhost/api/me", {
      headers: {
        cookie: "access_token=expired-access; refresh_token=valid-refresh",
      },
    });

    const response = await proxyToBackend(request, "/api/auth/me", {
      backendUrl: "http://kong:8000",
      backendService: "user",
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/user-service/api/v1/auth/me",
      expect.any(Object)
    );
  });

  it("does not send an expired access bearer while refreshing auth cookies", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest("http://localhost/api/auth/refresh", {
      method: "POST",
      headers: {
        cookie: "access_token=expired-access; refresh_token=valid-refresh",
      },
    });

    await proxyToBackend(request, "/api/auth/refresh", {
      method: "POST",
      backendUrl: "http://kong:8000",
      backendService: "user",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/user-service/api/v1/auth/refresh",
      expect.objectContaining({
        headers: expect.not.objectContaining({
          Authorization: expect.any(String),
        }),
      })
    );
  });

  it("forwards the incoming X-Language header to the backend", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/auth/external/login",
      {
        method: "POST",
        body: new URLSearchParams([["username", "external@example.com"]]),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
          "x-language": "tr",
        },
      }
    );

    await proxyToBackend(request, "/api/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Language": "tr" }),
      })
    );
  });

  it("falls back to the incoming Accept-Language header when X-Language is absent", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/auth/external/login",
      {
        method: "POST",
        body: new URLSearchParams([["username", "external@example.com"]]),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
          "accept-language": "tr-TR,tr;q=0.9",
        },
      }
    );

    await proxyToBackend(request, "/api/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          "Accept-Language": "tr-TR,tr;q=0.9",
        }),
      })
    );
  });
});

describe("getLanguageHeaders", () => {
  it("prefers the app's X-Language header over Accept-Language", () => {
    const request = new NextRequest("http://localhost/api/user/pats", {
      headers: {
        "x-language": "tr",
        "accept-language": "en-US,en;q=0.9",
      },
    });

    expect(getLanguageHeaders(request)).toEqual({ "X-Language": "tr" });
  });

  it("falls back to Accept-Language when X-Language is absent", () => {
    const request = new NextRequest("http://localhost/api/user/pats", {
      headers: { "accept-language": "tr-TR,tr;q=0.9" },
    });

    expect(getLanguageHeaders(request)).toEqual({
      "Accept-Language": "tr-TR,tr;q=0.9",
    });
  });

  it("returns no language headers when neither is present", () => {
    const request = new NextRequest("http://localhost/api/user/pats");

    expect(getLanguageHeaders(request)).toEqual({});
  });
});
