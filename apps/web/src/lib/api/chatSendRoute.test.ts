import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://apisix:8000",
  },
}));

describe("/api/chat/send-chat-message route", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("forwards the incoming Idempotency-Key to the backend stream endpoint", async () => {
    const { POST } = await import("@/app/api/chat/send-chat-message/route");

    fetchSpy.mockResolvedValueOnce(
      new Response("data: ok\n\n", {
        status: 200,
        headers: {
          "content-type": "text/event-stream",
        },
      })
    );

    const request = new NextRequest(
      "http://localhost/api/chat/send-chat-message",
      {
        method: "POST",
        body: JSON.stringify({ message: "retryable" }),
        headers: {
          "content-type": "application/json",
          "idempotency-key": "idem-stream-123",
          authorization: "Bearer access-token",
        },
      }
    );

    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://apisix:8000/agent-service/api/v1/chat/messages",
      expect.any(Object)
    );
    const [, init] = fetchSpy.mock.calls[0]!;
    const headers = new Headers(init.headers);
    expect(headers.get("Idempotency-Key")).toBe("idem-stream-123");
    expect(headers.get("Authorization")).toBe("Bearer access-token");
  });
});
