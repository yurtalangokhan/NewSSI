import { forwardBackendResponse } from "@/lib/api/backendResponse";

describe("forwardBackendResponse", () => {
  it("preserves the backend status code", async () => {
    const response = new Response(JSON.stringify({ ok: true }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });

    const result = await forwardBackendResponse(response);

    expect(result.status).toBe(201);
    expect(await result.json()).toEqual({ ok: true });
  });

  it("forwards the Idempotency-Replayed header", async () => {
    const response = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Replayed": "true",
      },
    });

    const result = await forwardBackendResponse(response);

    expect(result.headers.get("Idempotency-Replayed")).toBe("true");
  });

  it("preserves 409 idempotency_key_reused errors", async () => {
    const response = new Response(
      JSON.stringify({
        error: { code: "idempotency_key_reused", message: "conflict" },
      }),
      {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }
    );

    const result = await forwardBackendResponse(response);

    expect(result.status).toBe(409);
    const body = await result.json();
    expect(body.error.code).toBe("idempotency_key_reused");
  });

  it("preserves 400 idempotency_key_required errors", async () => {
    const response = new Response(
      JSON.stringify({
        error: { code: "idempotency_key_required", message: "key required" },
      }),
      {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }
    );

    const result = await forwardBackendResponse(response);

    expect(result.status).toBe(400);
    const body = await result.json();
    expect(body.error.code).toBe("idempotency_key_required");
  });

  it("handles empty responses", async () => {
    const response = new Response(null, { status: 204 });

    const result = await forwardBackendResponse(response);

    expect(result.status).toBe(204);
    expect(result.body).toBeNull();
  });

  it("handles non-JSON responses as raw text", async () => {
    const response = new Response("plain text", {
      status: 200,
      headers: { "Content-Type": "text/plain" },
    });

    const result = await forwardBackendResponse(response);

    expect(result.status).toBe(200);
    expect(await result.text()).toBe("plain text");
  });

  it("does not add Idempotency-Replayed when absent", async () => {
    const response = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

    const result = await forwardBackendResponse(response);

    expect(result.headers.get("Idempotency-Replayed")).toBeNull();
  });
});
