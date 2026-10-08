import { NextRequest } from "next/server";
import { proxyToBackend } from "./proxy";
import { POST as sendChat } from "@/app/api/chat/send-chat-message/route";
import { POST as pullModel } from "@/app/api/admin/ollama/pull/route";
import { GET as langgraph } from "@/app/api/langgraph/[...path]/route";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://localhost:8000/agent-service",
  },
}));

const routes = [
  [
    "proxy",
    (request: NextRequest) => proxyToBackend(request, "/api/chat/messages"),
  ],
  ["chat", sendChat],
  ["ollama", pullModel],
  ["langgraph", langgraph],
] as const;

function request() {
  return new NextRequest("http://localhost/api/langgraph/threads", {
    method: "POST",
    body: "{}",
    headers: { "X-Language": "tr", "X-Request-ID": "req-safe" },
  });
}

beforeEach(() => jest.spyOn(console, "error").mockImplementation(() => {}));
afterEach(() => jest.restoreAllMocks());

describe.each(routes)("%s error handling", (_name, route) => {
  it.each([
    [
      new TypeError("private-host connection failed"),
      503,
      "dependency.unavailable",
    ],
    [
      new DOMException("private-host timed out", "TimeoutError"),
      504,
      "dependency.timeout",
    ],
  ])("classifies transport failures safely", async (error, status, code) => {
    jest.spyOn(global, "fetch").mockRejectedValueOnce(error);
    const response = await route(request());
    expect(response.status).toBe(status);
    expect(response.headers.get("Content-Language")).toBe("tr");
    const body = await response.json();
    expect(body.error).toMatchObject({ code, request_id: "req-safe" });
    expect(JSON.stringify(body)).not.toContain("private-host");
  });

  it("preserves cancellation", async () => {
    const error = new DOMException("cancelled", "AbortError");
    jest.spyOn(global, "fetch").mockRejectedValueOnce(error);
    await expect(route(request())).rejects.toBe(error);
  });

  it("preserves localized backend envelopes and metadata", async () => {
    const body = {
      error: {
        code: "dependency.rate_limited",
        message: "Lütfen bekleyin.",
        details: { dependency: "ollama" },
        field_errors: [],
        request_id: "req-upstream",
      },
    };
    jest.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(body), {
        status: 503,
        headers: {
          "Content-Type": "application/json",
          "Content-Language": "tr",
          "X-Request-ID": "req-upstream",
          "Retry-After": "30",
        },
      })
    );
    const response = await route(request());
    expect(response.status).toBe(503);
    expect(response.headers.get("Content-Language")).toBe("tr");
    expect(response.headers.get("Retry-After")).toBe("30");
    expect(await response.json()).toEqual(body);
  });
});

describe.each([
  ["chat", sendChat],
  ["ollama", pullModel],
] as const)("%s stream safety", (_name, route) => {
  it("forwards request language to upstream", async () => {
    const fetchSpy = jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("data: ok\n\n"));
    await route(request());
    expect(
      new Headers(fetchSpy.mock.calls[0]?.[1]?.headers).get("X-Language")
    ).toBe("tr");
  });
  it("hides non-JSON upstream diagnostics", async () => {
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response("private-host stacktrace", { status: 502 })
      );
    const response = await route(request());
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({
      error: { code: "dependency.invalid_response" },
    });
  });
});
