import { NextRequest } from "next/server";

describe("/api/admin/ollama/pull route", () => {
  let fetchSpy: jest.SpyInstance;
  const previousInternalUrl = process.env.INTERNAL_URL;

  beforeEach(() => {
    process.env.INTERNAL_URL = "http://kong:8000";
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
    process.env.INTERNAL_URL = previousInternalUrl;
    jest.resetModules();
  });

  it("forwards Idempotency-Key to the upstream streaming endpoint", async () => {
    const { POST } = await import("@/app/api/admin/ollama/pull/route");
    fetchSpy.mockResolvedValueOnce(
      new Response("data: ok\n\n", {
        status: 200,
        headers: {
          "content-type": "text/event-stream",
        },
      })
    );

    const request = new NextRequest("http://localhost/api/admin/ollama/pull", {
      method: "POST",
      body: JSON.stringify({ model: "llama3.2" }),
      headers: {
        "content-type": "application/json",
        "idempotency-key": "ollama-pull-key",
      },
    });

    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://kong:8000/agent-service/api/v1/admin/ollama/pull",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "ollama-pull-key",
        }),
      })
    );
  });
});
