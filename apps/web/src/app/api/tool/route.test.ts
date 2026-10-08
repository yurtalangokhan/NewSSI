/**
 * This route forwarded the incoming Cookie header verbatim but never
 * derived an Authorization header from it, for both the built-in-tools
 * call and every call inside fetchExternalMcpTools() (the server list,
 * and each server's tool snapshots). agent-service is bearer-token only
 * and never reads cookies, so every one of those internal calls got a
 * bare 401 -- fetchExternalMcpTools() swallows that silently (`if
 * (!serversRes.ok) return []`), so external MCP tools never appeared in
 * the agent editor's tool picker for any user, deterministically, not
 * intermittently.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { GET } from "./route";

// agent-service answers with the ResponseModel envelope, not the bare payload.
function envelope(data: unknown, status = 200) {
  return jsonResponse({ statusCode: status, message: null, data, error: null });
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("GET /api/tool", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("derives an Authorization header from the access_token cookie for every outbound call", async () => {
    fetchSpy.mockImplementation((url: string) => {
      if (url.includes("/mcp/tools-builtin")) {
        return Promise.resolve(jsonResponse({ tools: [] }));
      }
      if (url.includes("/servers/1001/tools")) {
        return Promise.resolve(
          envelope([{ id: 5, name: "search", mcp_server_id: 1001 }])
        );
      }
      if (url.includes("/admin/mcp/servers")) {
        return Promise.resolve(
          envelope({ mcp_servers: [{ id: 1001, status: "CONNECTED" }] })
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const request = new NextRequest("http://localhost/api/tool", {
      headers: { cookie: "access_token=real-session-token" },
    });

    const response = await GET(request);
    const body = await response.json();

    expect(fetchSpy).toHaveBeenCalledTimes(3);
    for (const call of fetchSpy.mock.calls) {
      const init = call[1] as RequestInit;
      expect(new Headers(init.headers).get("Authorization")).toBe(
        "Bearer real-session-token"
      );
    }
    expect(body).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 5, name: "search", mcp_server_id: 1001 }),
      ])
    );
  });

  it("skips servers that are only registered, not connected", async () => {
    fetchSpy.mockImplementation((url: string) => {
      if (url.includes("/mcp/tools-builtin")) {
        return Promise.resolve(jsonResponse({ tools: [] }));
      }
      return Promise.resolve(
        envelope({
          mcp_servers: [
            { id: 1001, status: "CONNECTED" },
            { id: 1002, status: "CREATED" },
          ],
        })
      );
    });

    await GET(
      new NextRequest("http://localhost/api/tool", {
        headers: { authorization: "Bearer t" },
      })
    );

    const toolCalls = fetchSpy.mock.calls
      .map((call) => String(call[0]))
      .filter((url) => url.includes("/tools"));
    // One per connected server, from the cached-tools endpoint (read access),
    // not the live-discovery one that needs the sync permission.
    expect(toolCalls).toHaveLength(2);
    expect(toolCalls.some((url) => url.includes("/tools-builtin"))).toBe(true);
    expect(toolCalls.some((url) => url.includes("/servers/1001/tools"))).toBe(
      true
    );
    expect(toolCalls.some((url) => url.includes("/tools/snapshots"))).toBe(
      false
    );
  });

  it("logs a server whose tools cannot be read instead of dropping it silently", async () => {
    const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
    fetchSpy.mockImplementation((url: string) => {
      if (url.includes("/mcp/tools-builtin")) {
        return Promise.resolve(jsonResponse({ tools: [] }));
      }
      if (url.includes("/servers/1001/tools")) {
        return Promise.resolve(jsonResponse({}, 403));
      }
      return Promise.resolve(
        envelope({ mcp_servers: [{ id: 1001, status: "CONNECTED" }] })
      );
    });

    const response = await GET(
      new NextRequest("http://localhost/api/tool", {
        headers: { authorization: "Bearer t" },
      })
    );

    expect(response.status).toBe(200);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("1001"));
    warn.mockRestore();
  });

  it("still prefers an explicit incoming Authorization header when present", async () => {
    fetchSpy.mockImplementation((url: string) => {
      if (url.includes("/mcp/tools-builtin")) {
        return Promise.resolve(jsonResponse({ tools: [] }));
      }
      return Promise.resolve(envelope({ mcp_servers: [] }));
    });

    const request = new NextRequest("http://localhost/api/tool", {
      headers: {
        cookie: "access_token=cookie-token",
        authorization: "Bearer header-token",
      },
    });

    await GET(request);

    for (const call of fetchSpy.mock.calls) {
      const init = call[1] as RequestInit;
      expect(new Headers(init.headers).get("Authorization")).toBe(
        "Bearer header-token"
      );
    }
  });
});
