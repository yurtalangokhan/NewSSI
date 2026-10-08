/**
 * This route forwarded the incoming Cookie header verbatim but never
 * derived an Authorization header from it. agent-service is bearer-token
 * only (it deliberately never reads cookies), so the internal call to
 * /admin/mcp/servers always got a bare 401 "Missing bearer token" --
 * every single time, for every user, not just intermittently. The route's
 * own designed fallback (return built-in tools only, so the editor still
 * renders) then silently swallowed that failure, so the agent editor's
 * MCP tool picker never showed a user's external servers, no error ever
 * surfaced, and there was nothing to debug from the outside.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
    TOOLS_SERVICE_URL: "http://localhost:8000/tools-service/mcp",
  },
}));

import { GET } from "./route";

describe("GET /api/mcp/servers", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          statusCode: 200,
          message: null,
          data: { mcp_servers: [{ id: 1001, name: "DeepWiki" }] },
          error: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        }
      )
    );

    const request = new NextRequest("http://localhost/api/mcp/servers", {
      headers: { cookie: "access_token=real-session-token" },
    });

    const response = await GET(request);
    const body = await response.json();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
    // The client unwraps the ResponseModel envelope, so it must be passed on.
    expect(body.statusCode).toBe(200);
    expect(body.data.mcp_servers).toEqual([{ id: 1001, name: "DeepWiki" }]);
  });

  it("still prefers an explicit incoming Authorization header when present", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          statusCode: 200,
          message: null,
          data: { mcp_servers: [] },
          error: null,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        }
      )
    );

    const request = new NextRequest("http://localhost/api/mcp/servers", {
      headers: {
        cookie: "access_token=cookie-token",
        authorization: "Bearer header-token",
      },
    });

    await GET(request);

    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer header-token"
    );
  });

  it("falls back to the built-in server inside the same envelope", async () => {
    fetchSpy.mockResolvedValueOnce(new Response("{}", { status: 403 }));

    const response = await GET(
      new NextRequest("http://localhost/api/mcp/servers", {
        headers: { authorization: "Bearer t" },
      })
    );
    const body = await response.json();

    expect(body.statusCode).toBe(200);
    expect(body.data.mcp_servers).toEqual([
      expect.objectContaining({ id: 1, name: "tools-service" }),
    ]);
  });
});
