import { NextRequest } from "next/server";
import {
  deriveBackendAuthHeaders,
  getLanguageHeaders,
  proxyToBackend,
} from "@/lib/api/proxy";
import { appSettings } from "@/lib/settings";

jest.mock("@/lib/settings", () => {
  const actual = jest.requireActual("@/lib/settings");
  return {
    appSettings: {
      ...actual.appSettings,
      GATEWAY_URL: "http://apisix:8000",
      USER_SERVICE_URL: "http://apisix:8000/user-service",
      AGENT_SERVICE_URL: "http://apisix:8000/agent-service",
      RAG_SERVICE_URL: "http://apisix:8000/rag-service",
      TOOLS_SERVICE_URL: "http://apisix:8000/tools-service/mcp",
    },
  };
});
const mockAppSettings = appSettings as unknown as {
  GATEWAY_URL: string;
  USER_SERVICE_URL: string;
  AGENT_SERVICE_URL: string;
  RAG_SERVICE_URL: string;
  TOOLS_SERVICE_URL: string;
};

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
    mockAppSettings.USER_SERVICE_URL = "http://apisix:8000/user-service";
    mockAppSettings.AGENT_SERVICE_URL = "http://apisix:8000/agent-service";
    mockAppSettings.RAG_SERVICE_URL = "http://apisix:8000/rag-service";
    mockAppSettings.TOOLS_SERVICE_URL = "http://apisix:8000/tools-service/mcp";
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("routes canonical auth requests directly through the Gateway auth API", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));
    const request = new NextRequest("http://localhost/api/auth/refresh", {
      method: "POST",
      headers: {
        cookie: "refresh_token=refresh; access_token=expired",
        authorization: "Bearer expired",
      },
    });

    await proxyToBackend(request, "/auth/api/v1/refresh", {
      method: "POST",
      backendUrl: "http://apisix:8000",
    });

    expect(fetchSpy.mock.calls[0]![0]).toBe(
      "http://apisix:8000/user-service/api/v1/auth/refresh"
    );
    expect(
      new Headers(fetchSpy.mock.calls[0]![1]?.headers).has("Authorization")
    ).toBe(false);
  });

  it.each([undefined, "http://localhost:8090"])(
    "does not read service URL settings for Gateway login (%s)",
    async (userServiceUrl) => {
      const settings = appSettings as {
        GATEWAY_URL: string;
        USER_SERVICE_URL: string;
      };
      settings.GATEWAY_URL = "http://apisix:8000";
      settings.USER_SERVICE_URL = userServiceUrl || "http://must-not-be-used";
      fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));
      const response = await proxyToBackend(
        new NextRequest("http://localhost/api/auth/login", { method: "POST" }),
        "/auth/api/v1/login"
      );
      expect(response.status).toBe(200);
      expect(fetchSpy).toHaveBeenCalledWith(
        "http://apisix:8000/user-service/api/v1/auth/login",
        expect.objectContaining({ method: "POST" })
      );
    }
  );
  it("uses a domain target descriptor without changing the query or method", async () => {
    fetchSpy.mockResolvedValueOnce(
      responseWithHeaders({ "content-type": "application/json" })
    );
    const request = new NextRequest("http://localhost/api/me?include=roles");
    const response = await proxyToBackend(request, {
      service: "user",
      path: "/api/v1/auth/me",
    });
    expect(response.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://apisix:8000/user-service/api/v1/auth/me?include=roles",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("preserves browser Origin for Gateway CSRF checks", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));
    const request = new NextRequest("http://localhost/api/auth/login", {
      method: "POST",
      headers: { origin: "https://untrusted.example" },
    });

    await proxyToBackend(request, "/auth/api/v1/login", {
      backendUrl: "http://apisix:8000",
    });

    expect(fetchSpy.mock.calls[0]![0]).toBe(
      "http://apisix:8000/user-service/api/v1/auth/login"
    );
    expect(new Headers(fetchSpy.mock.calls[0]![1]?.headers).get("Origin")).toBe(
      "https://untrusted.example"
    );
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

    const response = await proxyToBackend(
      request,
      "/api/v1/auth/external/login",
      {
        method: "POST",
        backendUrl: "http://user-service",
      }
    );

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

    const response = await proxyToBackend(
      request,
      "/api/v1/auth/external/login",
      {
        method: "POST",
        backendUrl: "http://user-service",
      }
    );

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

    await proxyToBackend(request, "/api/v1/auth/external/login", {
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

  it("uses the service scope explicitly configured in the base", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest(
      "http://localhost/api/chat/get-user-chat-sessions"
    );

    await proxyToBackend(request, "/api/v1/chat/get-user-chat-sessions", {
      backendUrl: "http://apisix:8000/agent-service",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://apisix:8000/agent-service/api/v1/chat/get-user-chat-sessions",
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

    await proxyToBackend(request, "/api/v1/chat/send-chat-message", {
      method: "POST",
      backendUrl: "http://apisix:8000/agent-service",
    });

    expect(fetchSpy.mock.calls[0][0]).toBe(
      "http://apisix:8000/agent-service/api/v1/chat/send-chat-message"
    );
    expect(
      new Headers(fetchSpy.mock.calls[0][1]?.headers).get("Idempotency-Key")
    ).toBe("idem-web-123");
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

    await proxyToBackend(request, "/api/v1/chat/get-user-chat-sessions", {
      backendUrl: "http://apisix:8000/agent-service",
    });

    expect(
      new Headers(fetchSpy.mock.calls[0][1]?.headers).has("Idempotency-Key")
    ).toBe(false);
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

    expect(
      new Headers(fetchSpy.mock.calls[0][1]?.headers).has("Idempotency-Key")
    ).toBe(false);
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

    const response = await proxyToBackend(request, "/api/v1/collections", {
      backendUrl: "http://apisix:8000/rag-service",
      backendService: "rag",
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][0]).toBe(
      "http://apisix:8000/rag-service/api/v1/collections"
    );
    const headers = new Headers(fetchSpy.mock.calls[0][1]?.headers);
    expect(headers.get("Cookie")).toBe("refresh_token=valid-refresh");
    expect(headers.has("Authorization")).toBe(false);
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

    const response = await proxyToBackend(request, "/api/v1/collections", {
      backendUrl: "http://apisix:8000/rag-service",
      backendService: "rag",
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://apisix:8000/rag-service/api/v1/collections",
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

    const response = await proxyToBackend(request, "/api/v1/auth/me", {
      backendUrl: "http://apisix:8000/user-service",
      backendService: "user",
    });

    expect(response.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://apisix:8000/user-service/api/v1/auth/me",
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

    await proxyToBackend(request, "/api/v1/auth/refresh", {
      method: "POST",
      backendUrl: "http://apisix:8000/user-service",
      backendService: "user",
    });

    expect(fetchSpy.mock.calls[0][0]).toBe(
      "http://apisix:8000/user-service/api/v1/auth/refresh"
    );
    expect(
      new Headers(fetchSpy.mock.calls[0][1]?.headers).has("Authorization")
    ).toBe(false);
  });

  it("does not clear rotated cookies when a stale refresh request fails", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "invalid refresh token" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      })
    );

    const request = new NextRequest("http://localhost/api/auth/refresh", {
      method: "POST",
      headers: {
        cookie: "access_token=fresh-access; refresh_token=fresh-refresh",
      },
    });

    const response = await proxyToBackend(request, "/api/v1/auth/refresh", {
      method: "POST",
      backendUrl: "http://apisix:8000/user-service",
      backendService: "user",
    });

    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toBeNull();
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

    await proxyToBackend(request, "/api/v1/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
    });

    const [, init] = fetchSpy.mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Language")).toBe("tr");
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

    await proxyToBackend(request, "/api/v1/auth/external/login", {
      method: "POST",
      backendUrl: "http://user-service",
    });

    const [, init] = fetchSpy.mock.calls[0]!;
    expect(new Headers(init?.headers).get("Accept-Language")).toBe(
      "tr-TR,tr;q=0.9"
    );
  });

  it("forwards the request body as a stream instead of buffering it first", async () => {
    fetchSpy.mockResolvedValueOnce(responseWithHeaders({}));

    const request = new NextRequest("http://localhost/api/collections", {
      method: "POST",
      body: "a".repeat(1024),
      headers: { "content-type": "application/octet-stream" },
    });
    const arrayBufferSpy = jest.spyOn(request, "arrayBuffer");

    await proxyToBackend(request, "/api/collections", {
      method: "POST",
      backendUrl: "http://apisix:8000/agent-service",
    });

    expect(arrayBufferSpy).not.toHaveBeenCalled();
    const [, init] = fetchSpy.mock.calls[0];
    expect(init.body).toBe(request.body);
    expect(init.duplex).toBe("half");
  });

  it("rejects a request whose declared Content-Length exceeds the proxy limit", async () => {
    const request = new NextRequest("http://localhost/api/collections", {
      method: "POST",
      headers: { "content-length": String(300 * 1024 * 1024) },
    });

    const response = await proxyToBackend(request, "/api/collections", {
      method: "POST",
    });

    expect(response.status).toBe(413);
    expect(fetchSpy).not.toHaveBeenCalled();
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

describe("deriveBackendAuthHeaders", () => {
  it("derives Authorization from the access_token cookie", () => {
    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        headers: { cookie: "access_token=real-session-token; other=1" },
      }
    );

    expect(deriveBackendAuthHeaders(request)).toEqual({
      Cookie: "access_token=real-session-token; other=1",
      Authorization: "Bearer real-session-token",
    });
  });

  it("prefers an explicit incoming Authorization header over the cookie", () => {
    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        headers: {
          cookie: "access_token=cookie-token",
          authorization: "Bearer header-token",
        },
      }
    );

    expect(deriveBackendAuthHeaders(request)).toEqual({
      Cookie: "access_token=cookie-token",
      Authorization: "Bearer header-token",
    });
  });

  it("returns no Authorization when there is no cookie and no header", () => {
    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message"
    );

    expect(deriveBackendAuthHeaders(request)).toEqual({});
  });

  it("returns no Authorization when the cookie jar has no access_token", () => {
    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        headers: { cookie: "refresh_token=only-this" },
      }
    );

    expect(deriveBackendAuthHeaders(request)).toEqual({
      Cookie: "refresh_token=only-this",
    });
  });
});
