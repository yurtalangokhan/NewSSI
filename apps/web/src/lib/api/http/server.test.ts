import { backendRequest, resolveBackendUrl } from "@/lib/api/http/server";
import { appSettings } from "@/lib/settings";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    AGENT_SERVICE_URL: "http://apisix:8000/agent-service",
    USER_SERVICE_URL: "http://apisix:8000/user-service",
    RAG_SERVICE_URL: "http://apisix:8000/rag-service",
    TOOLS_SERVICE_URL: "http://apisix:8000/tools-service/mcp",
    DEBUG_AUTH_COOKIE: undefined,
    NODE_ENV: "test",
  },
}));

const mockAppSettings = appSettings as unknown as {
  AGENT_SERVICE_URL: string;
  USER_SERVICE_URL: string;
  RAG_SERVICE_URL: string;
  TOOLS_SERVICE_URL: string;
};

describe("backendRequest service routing", () => {
  beforeEach(() => {
    mockAppSettings.AGENT_SERVICE_URL = "http://apisix:8000/agent-service";
    mockAppSettings.USER_SERVICE_URL = "http://apisix:8000/user-service";
    mockAppSettings.RAG_SERVICE_URL = "http://apisix:8000/rag-service";
    mockAppSettings.TOOLS_SERVICE_URL = "http://apisix:8000/tools-service/mcp";
    global.fetch = jest
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("uses the selected service base rather than the agent base", async () => {
    await backendRequest({ service: "user", path: "/api/v1/users/me" });

    expect(global.fetch).toHaveBeenCalledWith(
      "http://apisix:8000/user-service/api/v1/users/me",
      expect.any(Object)
    );
  });

  it.each(["agent", "rag", "user", "tools"] as const)(
    "selects only the explicit %s service base",
    async (service) => {
      await backendRequest({ service, path: "/custom/resource" });
      const suffix = service === "tools" ? "/mcp" : "/api/v1/custom/resource";
      expect(global.fetch).toHaveBeenCalledWith(
        `http://apisix:8000/${service}-service${suffix}`,
        expect.any(Object)
      );
    }
  );

  it.each([
    [
      "http://apisix:8000",
      "/api/items",
      "http://apisix:8000/agent-service/api/v1/items",
    ],
    [
      "https://edge.example:9443/mount/",
      "/api/v7/items/",
      "https://edge.example:9443/mount/api/v1/v7/items/",
    ],
  ])(
    "canonicalizes service paths against an explicit base (%s)",
    (baseUrl, path, expected) => {
      expect(
        resolveBackendUrl({ service: "agent", baseUrl, path }).toString()
      ).toBe(expected);
    }
  );

  it("preserves encoded segments and repeated query values", () => {
    expect(
      resolveBackendUrl(
        { service: "user", path: "/items/a%2Fb/" },
        new URLSearchParams("tag=y&tag=z")
      ).toString()
    ).toBe("http://apisix:8000/user-service/api/v1/items/a%2Fb/?tag=y&tag=z");
  });

  describe("language forwarding", () => {
    const sentHeaders = () =>
      new Headers((global.fetch as jest.Mock).mock.calls[0]?.[1]?.headers);

    it("forwards the caller's selected language", async () => {
      const request = new Request("http://web/api/users/me", {
        headers: { "x-language": "tr", "accept-language": "en-US" },
      });
      await backendRequest({ service: "user", path: "/users/me", request });

      expect(sentHeaders().get("x-language")).toBe("tr");
      expect(sentHeaders().get("accept-language")).toBeNull();
    });

    it("falls back to Accept-Language when no language was selected", async () => {
      const request = new Request("http://web/api/users/me", {
        headers: { "accept-language": "en-US" },
      });
      await backendRequest({ service: "user", path: "/users/me", request });

      expect(sentHeaders().get("x-language")).toBeNull();
      expect(sentHeaders().get("accept-language")).toBe("en-US");
    });

    it("keeps an explicit language header over the forwarded one", async () => {
      const request = new Request("http://web/api/users/me", {
        headers: { "x-language": "tr" },
      });
      await backendRequest({
        service: "user",
        path: "/users/me",
        request,
        headers: { "X-Language": "en" },
      });

      expect(sentHeaders().get("x-language")).toBe("en");
    });
  });
});
