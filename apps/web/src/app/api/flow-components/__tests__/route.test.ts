/**
 * 28.2 — the one new proxy route this task adds. Verifies all three
 * shapes it must forward (base, /options/{source}, /{type}) reach the
 * expected backend path.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { NextRequest } from "next/server";

jest.mock("@/lib/api/proxy", () => ({
  proxyToBackend: jest.fn(async () => new Response(null, { status: 200 })),
}));

import { proxyToBackend } from "@/lib/api/proxy";
import { GET } from "../[[...path]]/route";

const mockProxyToBackend = proxyToBackend as jest.Mock;

function request(url: string) {
  return new NextRequest(url);
}

beforeEach(() => {
  mockProxyToBackend.mockClear();
});

describe("flow-components proxy — 28.2", () => {
  it("forwards the base path with no segments", async () => {
    await GET(request("http://x/api/flow-components"), {
      params: Promise.resolve({ path: undefined }),
    });
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      "/flow-components"
    );
  });

  it("forwards /options/{source}", async () => {
    await GET(request("http://x/api/flow-components/options/llm.models"), {
      params: Promise.resolve({ path: ["options", "llm.models"] }),
    });
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      "/flow-components/options/llm.models"
    );
  });

  it("forwards /{type}", async () => {
    await GET(request("http://x/api/flow-components/ZeroShotAgent"), {
      params: Promise.resolve({ path: ["ZeroShotAgent"] }),
    });
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      "/flow-components/ZeroShotAgent"
    );
  });
});
