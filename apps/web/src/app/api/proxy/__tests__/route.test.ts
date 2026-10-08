/**
 * /api/proxy/mcp/tools-builtin and /api/proxy/mcp/execute had no
 * corresponding Next.js route, so calls to them fell through to
 * next.config.js's generic `/api/:path*` rewrite -- a raw byte-level
 * proxy that forwards the browser's original headers as-is. The browser
 * only ever sends the access_token as an httpOnly cookie
 * (authenticatedFetch never sets an Authorization header itself), and
 * agent-service deliberately never reads cookies, so every request through
 * that path got a 401 no matter how valid the session was. authenticatedFetch
 * then retried after a refresh, got 401 again, and forced a logout.
 *
 * Every other backend surface avoids this by having a dedicated route.ts
 * that calls proxyToBackend, which reads the access_token cookie
 * server-side and attaches it as an Authorization header. This catch-all
 * gives /api/proxy/* the same treatment.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/api/proxy", () => ({
  proxyToBackend: jest.fn(async () => new Response(null, { status: 200 })),
}));

import { proxyToBackend } from "@/lib/api/proxy";
import { GET, POST } from "../[...path]/route";

const mockProxyToBackend = proxyToBackend as jest.Mock;

function request(
  url: string,
  init?: ConstructorParameters<typeof NextRequest>[1]
) {
  return new NextRequest(url, init);
}

beforeEach(() => {
  mockProxyToBackend.mockClear();
});

describe("proxy catch-all", () => {
  it("forwards GET /mcp/tools-builtin to the backend proxy path", async () => {
    await GET(request("http://x/api/proxy/mcp/tools-builtin"), {
      params: Promise.resolve({ path: ["mcp", "tools-builtin"] }),
    });

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/proxy/mcp/tools-builtin" }
    );
  });

  it("forwards POST /mcp/execute to the backend proxy path", async () => {
    await POST(
      request("http://x/api/proxy/mcp/execute", {
        method: "POST",
        body: JSON.stringify({ tool_name: "x" }),
      }),
      { params: Promise.resolve({ path: ["mcp", "execute"] }) }
    );

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/proxy/mcp/execute" },
      { method: "POST" }
    );
  });
});
