import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://apisix:8000",
  },
}));

describe("chat run proxy routes", () => {
  let fetchSpy: jest.SpyInstance;
  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });
  afterEach(() => fetchSpy.mockRestore());

  it("streams run events and forwards Last-Event-ID and after", async () => {
    const { GET } = await import("@/app/api/chat/runs/[runId]/events/route");
    fetchSpy.mockResolvedValueOnce(
      new Response("id: 3\ndata: x\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      })
    );
    const request = new NextRequest(
      "http://localhost/api/chat/runs/r1/events?after=2",
      {
        headers: { "last-event-id": "3" },
      }
    );
    const response = await GET(request, {
      params: Promise.resolve({ runId: "r1" }),
    });
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(await response.text()).toContain("id: 3");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/api/v1/chat/runs/r1/events?after=2");
    expect(new Headers(init.headers).get("last-event-id")).toBe("3");
  });

  it("passes a 404 through", async () => {
    const { GET } = await import("@/app/api/chat/runs/[runId]/events/route");
    fetchSpy.mockResolvedValueOnce(
      new Response('{"detail":"gone"}', {
        status: 404,
        headers: { "content-type": "application/json" },
      })
    );
    const response = await GET(
      new NextRequest("http://localhost/api/chat/runs/r1/events"),
      { params: Promise.resolve({ runId: "r1" }) }
    );
    expect(response.status).toBe(404);
  });

  it("returns the active run", async () => {
    const { GET } = await import(
      "@/app/api/chat/sessions/[sessionId]/active-run/route"
    );
    fetchSpy.mockResolvedValueOnce(
      new Response('{"active_run":null}', {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    const response = await GET(
      new NextRequest("http://localhost/api/chat/sessions/s1/active-run"),
      { params: Promise.resolve({ sessionId: "s1" }) }
    );
    expect(await response.json()).toEqual({ active_run: null });
    expect(String(fetchSpy.mock.calls[0][0])).toContain(
      "/api/v1/chat/sessions/s1/active-run"
    );
  });

  it("forwards the stopped send's client_request_id to the backend", async () => {
    const { POST } = await import(
      "@/app/api/chat/stop-chat-session/[chatSessionId]/route"
    );
    fetchSpy.mockResolvedValueOnce(
      new Response('{"success":true}', {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    const response = await POST(
      new NextRequest(
        "http://localhost/api/chat/stop-chat-session/s1?client_request_id=k1",
        { method: "POST" }
      ),
      { params: Promise.resolve({ chatSessionId: "s1" }) }
    );
    expect(response.status).toBe(200);
    const [url] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain(
      "/api/v1/chat/stop-chat-session/s1?client_request_id=k1"
    );
  });

  it("marks a session seen through the proxy", async () => {
    const { POST } = await import(
      "@/app/api/chat/sessions/[sessionId]/seen/route"
    );
    fetchSpy.mockResolvedValueOnce(
      new Response('{"success":true}', {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    const response = await POST(
      new NextRequest("http://localhost/api/chat/sessions/s1/seen", {
        method: "POST",
      }),
      { params: Promise.resolve({ sessionId: "s1" }) }
    );
    expect(response.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/api/v1/chat/sessions/s1/seen");
    expect(init.method).toBe("POST");
  });
});
