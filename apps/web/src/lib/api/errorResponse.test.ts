import {
  apiErrorResponse,
  errorResponseFromException,
} from "@/lib/api/errorResponse";
import { ApiRequestError, parseApiErrorPayload } from "@/lib/api/errors";

describe("apiErrorResponse", () => {
  it("preserves a typed dependency failure and hides unexpected exception details", async () => {
    const request = new Request("http://localhost/api/chat", {
      headers: { "X-Language": "tr", "X-Request-ID": "req-proxy" },
    });
    const typed = new ApiRequestError(
      parseApiErrorPayload(
        {
          error: {
            code: "dependency.timeout",
            message: "Zaman aşımı.",
          },
        },
        504
      )
    );
    const response = errorResponseFromException(typed, request);
    expect(response.status).toBe(504);
    expect(await response.json()).toMatchObject({
      error: {
        code: "dependency.timeout",
        message: "Zaman aşımı.",
        request_id: "req-proxy",
      },
    });
    const unexpected = errorResponseFromException(
      new Error("secret-password"),
      request
    );
    expect(unexpected.status).toBe(500);
    expect(await unexpected.json()).toMatchObject({
      error: {
        code: "internal.server_error",
        message: "Beklenmeyen bir hata oluştu.",
      },
    });
  });
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
