/**
 * /api/admin/web-search/content-providers and .../search-providers had no
 * corresponding Next.js route, so they fell through to next.config.js's
 * generic `/api/:path*` rewrite -- a raw proxy that forwards the browser's
 * original headers as-is. The browser only ever sends the access_token as
 * an httpOnly cookie; agent-service deliberately never reads cookies, so
 * every request there got a 401 regardless of session validity, and
 * authenticatedFetch's retry-after-refresh got 401 again and forced a
 * logout. See ../../proxy/__tests__/route.test.ts for the matching fix on
 * the MCP proxy surface.
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

describe("admin web-search catch-all proxy", () => {
  it("forwards GET /content-providers to the backend path", async () => {
    await GET(request("http://x/api/admin/web-search/content-providers"), {
      params: Promise.resolve({ path: ["content-providers"] }),
    });

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      {
        service: "agent",
        path: "/api/v1/admin/web-search/content-providers",
      }
    );
  });

  it("forwards GET /search-providers to the backend path", async () => {
    await GET(request("http://x/api/admin/web-search/search-providers"), {
      params: Promise.resolve({ path: ["search-providers"] }),
    });

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      {
        service: "agent",
        path: "/api/v1/admin/web-search/search-providers",
      }
    );
  });

  it("forwards POST /content-providers/crawl to the backend path", async () => {
    await POST(
      request("http://x/api/admin/web-search/content-providers/crawl", {
        method: "POST",
        body: JSON.stringify({ url: "https://example.com" }),
      }),
      { params: Promise.resolve({ path: ["content-providers", "crawl"] }) }
    );

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      {
        service: "agent",
        path: "/api/v1/admin/web-search/content-providers/crawl",
      },
      { method: "POST" }
    );
  });
});
