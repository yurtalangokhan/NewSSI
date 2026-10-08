import { NextRequest } from "next/server";

// The route resolves the backend through getAgentServiceUrl() at import time.
jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://internal.test",
  },
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { GET } = require("./route") as typeof import("./route");

describe("GET /api/chat/mcp/oauth/callback", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }));
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  const baseUrl =
    "http://localhost:3000/api/chat/mcp/oauth/callback?code=abc&server_id=srv-1";

  it("ignores an external redirect_to and falls back to the chat app", async () => {
    const request = new NextRequest(
      `${baseUrl}&redirect_to=https://evil.example/`
    );

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location.startsWith("https://evil.example")).toBe(false);
    expect(location).toBe("http://localhost:3000/app");
  });

  it("ignores a protocol-relative redirect_to", async () => {
    const request = new NextRequest(`${baseUrl}&redirect_to=//evil.example/`);

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location).not.toContain("evil.example");
  });

  it("accepts a well-formed internal redirect_to", async () => {
    const request = new NextRequest(`${baseUrl}&redirect_to=/app/chat?id=1`);

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location).toBe("http://localhost:3000/app/chat?id=1");
  });

  it("falls back to the admin edit page for an invalid redirect_to in an admin flow", async () => {
    const request = new NextRequest(
      `${baseUrl}&admin=true&redirect_to=https://evil.example/`
    );

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location).toBe(
      "http://localhost:3000/admin/actions/edit-mcp?server_id=srv-1"
    );
  });
});
