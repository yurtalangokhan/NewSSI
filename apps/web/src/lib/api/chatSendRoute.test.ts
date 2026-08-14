import { NextRequest } from "next/server";

describe("/api/chat/send-chat-message route", () => {
  let fetchSpy: jest.SpyInstance;
  const previousInternalUrl = process.env.INTERNAL_URL;

  beforeEach(() => {
    process.env.INTERNAL_URL = "http://kong:8000";
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
    process.env.INTERNAL_URL = previousInternalUrl;
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
      "http://kong:8000/agent-service/api/v1/chat/send-chat-message",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "idem-stream-123",
          Authorization: "Bearer access-token",
        }),
      })
    );
  });
});
