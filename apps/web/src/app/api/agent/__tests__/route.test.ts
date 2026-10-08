/**
 * The agent-service catch-all proxy used to buffer every request body
 * fully into the Node process (request.arrayBuffer()) before forwarding
 * a single byte — a RAG upload sat entirely in memory first. It also
 * cloned every incoming header verbatim, which would forward a
 * client-supplied trusted-context header (x-internal-*, x-user-id)
 * straight through if the gateway's own stripping ever had a gap.
 */
import { NextRequest } from "next/server";

// The route module reads the URL at import time (module-level
// `const AGENT_SERVICE_URL = getAgentServiceUrl()`), so the accessor is
// mocked rather than the environment — jest.mock is hoisted above the
// require below.
jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://agent-service:2024",
  },
}));
const { POST } =
  require("../[...path]/route") as typeof import("../[...path]/route");

function jsonResponse() {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("agent-service catch-all proxy", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue(jsonResponse());
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("forwards the request body as a stream instead of buffering it first", async () => {
    const request = new NextRequest("http://localhost/api/agent/threads", {
      method: "POST",
      body: "a".repeat(1024),
      headers: { "content-type": "application/octet-stream" },
    });
    const arrayBufferSpy = jest.spyOn(request, "arrayBuffer");

    await POST(request, { params: Promise.resolve({ path: ["threads"] }) });

    expect(arrayBufferSpy).not.toHaveBeenCalled();
    const [, init] = fetchSpy.mock.calls[0];
    expect(init.body).toBe(request.body);
    expect(init.duplex).toBe("half");
  });

  it("rejects a request whose declared Content-Length exceeds the proxy limit", async () => {
    const request = new NextRequest("http://localhost/api/agent/threads", {
      method: "POST",
      headers: { "content-length": String(300 * 1024 * 1024) },
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["threads"] }),
    });

    expect(response.status).toBe(413);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("never forwards a client-supplied trusted-context header", async () => {
    const request = new NextRequest("http://localhost/api/agent/threads", {
      method: "POST",
      headers: {
        "x-internal-service-token": "forged",
        "x-user-id": "forged-user",
        "content-type": "application/json",
      },
      body: "{}",
    });

    await POST(request, { params: Promise.resolve({ path: ["threads"] }) });

    const [, init] = fetchSpy.mock.calls[0];
    const forwardedHeaders = init.headers as Headers;
    expect(forwardedHeaders.get("x-internal-service-token")).toBeNull();
    expect(forwardedHeaders.get("x-user-id")).toBeNull();
  });
});
