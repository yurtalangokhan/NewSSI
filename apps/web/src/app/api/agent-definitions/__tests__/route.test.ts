/**
 * 28.1 — verifies, rather than trusts, the brief's claim that the
 * existing `[...path]/route.ts` catch-all already proxies every P3 flow
 * endpoint. A routing regression here fails silently as a 404 at
 * runtime, so this is worth a real test, not an inspection.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { NextRequest } from "next/server";

jest.mock("@/lib/api/proxy", () => ({
  proxyToBackend: jest.fn(async () => new Response(null, { status: 200 })),
}));

import { proxyToBackend } from "@/lib/api/proxy";
import { GET, POST, PUT } from "../[...path]/route";

const mockProxyToBackend = proxyToBackend as jest.Mock;

function request(url: string) {
  return new NextRequest(url);
}

function paramsFor(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

const DEFINITION_ID = "11111111-1111-1111-1111-111111111111";

beforeEach(() => {
  mockProxyToBackend.mockClear();
});

describe("agent-definitions catch-all — 28.1, every P3 flow endpoint reaches the backend path", () => {
  it("GET .../flow/draft", async () => {
    await GET(
      request("http://x/api/agent-definitions/x"),
      paramsFor([DEFINITION_ID, "flow", "draft"])
    );
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      `/agent-definitions/${DEFINITION_ID}/flow/draft`
    );
  });

  it("PUT .../flow/draft", async () => {
    await PUT(
      request("http://x/api/agent-definitions/x"),
      paramsFor([DEFINITION_ID, "flow", "draft"])
    );
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      `/agent-definitions/${DEFINITION_ID}/flow/draft`,
      { method: "PUT" }
    );
  });

  it("GET .../flow/versions", async () => {
    await GET(
      request("http://x/api/agent-definitions/x"),
      paramsFor([DEFINITION_ID, "flow", "versions"])
    );
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      `/agent-definitions/${DEFINITION_ID}/flow/versions`
    );
  });

  it("POST .../flow/publish", async () => {
    await POST(
      request("http://x/api/agent-definitions/x"),
      paramsFor([DEFINITION_ID, "flow", "publish"])
    );
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      `/agent-definitions/${DEFINITION_ID}/flow/publish`,
      { method: "POST" }
    );
  });

  it("POST .../flow/rollback", async () => {
    await POST(
      request("http://x/api/agent-definitions/x"),
      paramsFor([DEFINITION_ID, "flow", "rollback"])
    );
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      `/agent-definitions/${DEFINITION_ID}/flow/rollback`,
      { method: "POST" }
    );
  });

  it("POST .../validate-flow", async () => {
    await POST(
      request("http://x/api/agent-definitions/x"),
      paramsFor(["validate-flow"])
    );
    expect(mockProxyToBackend).toHaveBeenCalledWith(
      expect.anything(),
      "/agent-definitions/validate-flow",
      { method: "POST" }
    );
  });
});
