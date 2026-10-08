/**
 * /api/agents/composition/catalog had no matching Next.js route. Existing
 * routes only covered /api/agents/catalog (exact) and /api/agents/{agentId}
 * (one dynamic segment) -- neither matches a two-segment path -- so calls
 * to the composition catalog fell through to next.config.js's generic
 * /api/:path* rewrite, which forwards the browser's request unchanged. The
 * browser only carries the access_token as an httpOnly cookie;
 * agent-service never reads cookies, so every request there got a 401
 * regardless of session validity, and authenticatedFetch's
 * retry-after-refresh got 401 again and forced a logout -- indistinguishable
 * in DevTools from the working /api/agents/catalog request, since Chrome's
 * Network panel labels both simply "catalog".
 */
import { NextRequest } from "next/server";

jest.mock("@/lib/api/proxy", () => ({
  proxyToBackend: jest.fn(async () => new Response(null, { status: 200 })),
}));

import { proxyToBackend } from "@/lib/api/proxy";
import { GET } from "../route";

const mockProxyToBackend = proxyToBackend as jest.Mock;

beforeEach(() => {
  mockProxyToBackend.mockClear();
});

it("forwards to the composition catalog backend path", async () => {
  const request = new NextRequest(
    "http://localhost/api/agents/composition/catalog"
  );

  await GET(request);

  expect(mockProxyToBackend).toHaveBeenCalledWith(
    expect.anything(),
    {
      service: "agent",
      path: "/api/v1/agents/composition/catalog",
    }
  );
});
