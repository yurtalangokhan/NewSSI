/**
 * /api/mail-configs had no corresponding Next.js route, so calls to it
 * (list configs, available configs, user-credentials, per-config
 * test/send/delete) fell through to next.config.js's generic
 * `/api/:path*` rewrite -- a raw proxy that forwards the browser's
 * original headers as-is. The browser only ever sends the access_token as
 * an httpOnly cookie (authenticatedFetch never sets an Authorization
 * header itself), and agent-service deliberately never reads cookies, so
 * every request there got a 401 no matter how valid the session was, and
 * authenticatedFetch's retry-after-refresh got 401 again and forced a
 * logout. See src/app/api/proxy/__tests__/route.test.ts and
 * src/app/api/admin/web-search/__tests__/route.test.ts for the same fix on
 * two other surfaces.
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/api/proxy", () => ({
  proxyToBackend: jest.fn(async () => new Response(null, { status: 200 })),
}));

import { proxyToBackend } from "@/lib/api/proxy";
import { GET, POST, PUT, PATCH, DELETE } from "../[[...path]]/route";

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

describe("mail-configs catch-all proxy", () => {
  it("forwards the base path (list configs) with no segments", async () => {
    await GET(request("http://x/api/mail-configs?page=1&page_size=10"), {
      params: Promise.resolve({ path: undefined }),
    });

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/mail-configs" }
    );
  });

  it("forwards GET /available", async () => {
    await GET(request("http://x/api/mail-configs/available"), {
      params: Promise.resolve({ path: ["available"] }),
    });

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/mail-configs/available" }
    );
  });

  it("forwards PUT /user-credentials", async () => {
    await PUT(
      request("http://x/api/mail-configs/user-credentials", {
        method: "PUT",
        body: "{}",
      }),
      { params: Promise.resolve({ path: ["user-credentials"] }) }
    );

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/mail-configs/user-credentials" },
      { method: "PUT" }
    );
  });

  it("forwards POST /{id}/send", async () => {
    await POST(
      request("http://x/api/mail-configs/42/send", {
        method: "POST",
        body: "{}",
      }),
      { params: Promise.resolve({ path: ["42", "send"] }) }
    );

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/mail-configs/42/send" },
      { method: "POST" }
    );
  });

  it("forwards PATCH /{id}", async () => {
    await PATCH(
      request("http://x/api/mail-configs/42", { method: "PATCH", body: "{}" }),
      { params: Promise.resolve({ path: ["42"] }) }
    );

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/mail-configs/42" },
      { method: "PATCH" }
    );
  });

  it("forwards DELETE /{id}", async () => {
    await DELETE(
      request("http://x/api/mail-configs/42", { method: "DELETE" }),
      {
        params: Promise.resolve({ path: ["42"] }),
      }
    );

    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      { service: "agent", path: "/api/v1/mail-configs/42" },
      { method: "DELETE" }
    );
  });
});
