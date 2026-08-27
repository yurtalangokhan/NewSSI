import {
  errorMessageFromUnknown,
  parseApiErrorPayload,
  parseApiErrorResponse,
  throwParsedApiError,
} from "@/lib/api/errors";

describe("api error parser", () => {
  it("parses the standard error envelope", () => {
    expect(
      parseApiErrorPayload(
        {
          error: {
            code: "collection.not_found",
            message: "Collection not found.",
            details: { collection_id: "abc" },
            field_errors: [
              {
                field: "name",
                code: "required",
                message: "Name is required.",
              },
            ],
            request_id: "req_123",
          },
        },
        404
      )
    ).toEqual({
      status: 404,
      code: "collection.not_found",
      userMessage: "Collection not found.",
      details: { collection_id: "abc" },
      fieldErrors: [
        {
          field: "name",
          code: "required",
          message: "Name is required.",
        },
      ],
      requestId: "req_123",
      raw: {
        error: {
          code: "collection.not_found",
          message: "Collection not found.",
          details: { collection_id: "abc" },
          field_errors: [
            {
              field: "name",
              code: "required",
              message: "Name is required.",
            },
          ],
          request_id: "req_123",
        },
      },
    });
  });

  it("parses legacy FastAPI string detail", () => {
    expect(
      parseApiErrorPayload({ detail: "Missing thing" }, 404)
    ).toMatchObject({
      status: 404,
      code: "request.not_found",
      userMessage: "Missing thing",
      details: {},
      fieldErrors: [],
    });
  });

  it("parses FastAPI validation details into field errors", () => {
    expect(
      parseApiErrorPayload(
        {
          detail: [
            {
              loc: ["body", "name"],
              msg: "Field required",
              type: "missing",
            },
          ],
        },
        422
      )
    ).toMatchObject({
      status: 422,
      code: "validation.failed",
      userMessage: "Request validation failed.",
      fieldErrors: [
        {
          field: "body.name",
          code: "missing",
          message: "Field required",
        },
      ],
    });
  });

  it("parses text payloads", () => {
    expect(parseApiErrorPayload("Gateway timeout", 503)).toMatchObject({
      status: 503,
      code: "dependency.unavailable",
      userMessage: "Gateway timeout",
    });
  });

  it("extracts safe messages from unknown errors", () => {
    expect(errorMessageFromUnknown(new Error("No access"))).toBe("No access");
    expect(errorMessageFromUnknown("plain failure")).toBe("plain failure");
    expect(errorMessageFromUnknown(null, "Fallback")).toBe("Fallback");
  });

  it("parses an error response body once", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "idempotency_key_reused",
          message: "Idempotency key was reused for a different request.",
        },
      }),
      {
        status: 409,
        headers: { "content-type": "application/json" },
      }
    );

    await expect(parseApiErrorResponse(response)).resolves.toMatchObject({
      status: 409,
      code: "idempotency_key_reused",
      userMessage: "Idempotency key was reused for a different request.",
    });
  });

  it("throwParsedApiError throws with envelope message", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "request.conflict",
          message: "Name already exists.",
        },
      }),
      {
        status: 409,
        headers: { "content-type": "application/json" },
      }
    );

    await expect(throwParsedApiError(response, "Fallback")).rejects.toThrow(
      "Name already exists."
    );
  });

  it("throwParsedApiError throws legacy FastAPI detail string", async () => {
    const response = new Response(JSON.stringify({ detail: "Not found" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });

    await expect(throwParsedApiError(response, "Fallback")).rejects.toThrow(
      "Not found"
    );
  });

  it("throwParsedApiError falls back when body is empty", async () => {
    const response = new Response(null, { status: 500 });

    await expect(
      throwParsedApiError(response, "Something went wrong")
    ).rejects.toThrow("Something went wrong");
  });
});
