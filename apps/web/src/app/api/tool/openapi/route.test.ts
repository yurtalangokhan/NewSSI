/**
 * Same bug as /api/tool and /api/mcp/servers (fixed in 02065b43c and
 * 7a2db9445): this route forwards the incoming Cookie header verbatim but
 * never derives an Authorization header from it before calling
 * agent-service server-side. agent-service is bearer-token only and never
 * reads cookies, so this internal self-call always got a bare 401 -- and
 * because it's a server-side call, it never shows up in the browser's own
 * Network tab, only in agent-service's access log, which is what made this
 * one hard to pin down: useOpenApiTools() is fetched on the same agent
 * editor page as the already-fixed /api/tool and /api/mcp/servers calls,
 * so a failure here reads as "one more mystery 401 on this page" even
 * after those two were fixed.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { GET } from "./route";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("GET /api/tool/openapi", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ tools: [{ name: "search" }] })
    );

    const request = new NextRequest("http://localhost/api/tool/openapi", {
      headers: { cookie: "access_token=real-session-token" },
    });

    const response = await GET(request);
    const body = await response.json();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
    expect(body).toEqual([{ name: "search" }]);
  });

  it("still prefers an explicit incoming Authorization header when present", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ tools: [] }));

    const request = new NextRequest("http://localhost/api/tool/openapi", {
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
});
