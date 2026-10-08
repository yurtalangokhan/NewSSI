import { NextRequest } from "next/server";
import { GET } from "@/app/mcp/[[...path]]/route";
import { appSettings } from "@/lib/settings";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    OVERRIDE_API_PRODUCTION: true,
    NODE_ENV: "test",
    TOOLS_SERVICE_URL: "https://gateway.example/tools-service",
  },
}));

const mockAppSettings = appSettings as unknown as {
  OVERRIDE_API_PRODUCTION: boolean;
  NODE_ENV: string;
};

describe("MCP proxy uses the public tools service", () => {
  beforeEach(() => {
    mockAppSettings.OVERRIDE_API_PRODUCTION = true;
    mockAppSettings.NODE_ENV = "test";
    global.fetch = jest
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("joins the domain endpoint, encodes segments and forwards auth and query", async () => {
    const request = new NextRequest("https://web.example/mcp/sse?tag=x&tag=y", {
      headers: {
        authorization: "Bearer incoming-token",
        "mcp-session-id": "session-1",
      },
    });
    const response = await GET(request, {
      params: Promise.resolve({ path: ["a/b", "sse"] }),
    });
    expect(response.status).toBe(204);
    expect(global.fetch).toHaveBeenCalledWith(
      "https://gateway.example/tools-service/mcp/a%2Fb/sse?tag=x&tag=y",
      expect.any(Object)
    );
    const init = (global.fetch as jest.Mock).mock.calls[0][1];
    expect(new Headers(init.headers).get("authorization")).toBe(
      "Bearer incoming-token"
    );
    expect(new Headers(init.headers).get("mcp-session-id")).toBe("session-1");
    expect(init.signal).toBe(request.signal);
  });

  it("retains the production proxy guard", async () => {
    mockAppSettings.NODE_ENV = "production";
    mockAppSettings.OVERRIDE_API_PRODUCTION = false;
    expect(
      (await GET(new NextRequest("https://web.example/mcp"), {})).status
    ).toBe(404);
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
