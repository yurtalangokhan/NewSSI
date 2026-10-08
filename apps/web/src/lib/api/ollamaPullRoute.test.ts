import { NextRequest } from "next/server";

jest.mock("@/lib/settings", () => ({
  appSettings: {
    ...jest.requireActual("@/lib/settings").appSettings,
    AGENT_SERVICE_URL: "http://apisix:8000",
  },
}));

describe("/api/admin/ollama/pull route", () => {
  let fetchSpy: jest.SpyInstance;

  beforeEach(() => {
    fetchSpy = jest.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
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
      "http://apisix:8000/agent-service/api/v1/admin/ollama/pull",
      expect.any(Object)
    );
    const [, init] = fetchSpy.mock.calls[0]!;
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe(
      "ollama-pull-key"
    );
  });
});
