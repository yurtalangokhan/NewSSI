import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

import { GET } from "./route";

const SESSION = "3a19f671-7d34-4cfd-9ea4-21e17491b3f5";
const call = (cookie = "access_token=real-session-token") =>
  GET(
    new NextRequest(
      `http://localhost/api/chat/sessions/${SESSION}/active-run`,
      {
        headers: { cookie },
      }
    ),
    { params: Promise.resolve({ sessionId: SESSION }) }
  );

describe("GET /api/chat/sessions/[sessionId]/active-run", () => {
  let fetchSpy: jest.SpyInstance;
  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });
  afterEach(() => fetchSpy.mockRestore());

  it("targets the session's active-run endpoint with the cookie's token", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ active_run: null }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    const response = await call();

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain(`/chat/sessions/${SESSION}/active-run`);
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer real-session-token"
    );
    expect(await response.json()).toEqual({ active_run: null });
  });

  it("keeps the backend's status and its correlation and language headers", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: "request.not_found" } }), {
        status: 404,
        headers: {
          "content-type": "application/json",
          "x-request-id": "req-7",
          "content-language": "tr",
        },
      })
    );
    const response = await call();

    expect(response.status).toBe(404);
    expect(response.headers.get("x-request-id")).toBe("req-7");
    expect(response.headers.get("content-language")).toBe("tr");
  });

  it("answers a structured error when the backend is unreachable", async () => {
    jest.spyOn(console, "error").mockImplementation(() => undefined);
    fetchSpy.mockRejectedValueOnce(new TypeError("fetch failed"));
    const response = await call();

    expect(response.status).toBeGreaterThanOrEqual(500);
    expect(response.headers.get("content-type")).toContain("application/json");
  });
});
