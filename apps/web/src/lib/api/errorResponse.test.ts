import { apiErrorResponse } from "@/lib/api/errorResponse";

describe("apiErrorResponse", () => {
  it("returns the standard error envelope for Next.js route handlers", async () => {
    const response = apiErrorResponse({
      status: 503,
      code: "dependency.unavailable",
      message: "Backend is unavailable.",
      details: { service: "agent" },
      requestId: "req_123",
    });

    await expect(response.json()).resolves.toEqual({
      error: {
        code: "dependency.unavailable",
        message: "Backend is unavailable.",
        details: { service: "agent" },
        field_errors: [],
        request_id: "req_123",
      },
    });
    expect(response.status).toBe(503);
  });
});
