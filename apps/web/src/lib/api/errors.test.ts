import {
  errorMessageFromUnknown,
  parseApiErrorPayload,
  parseApiErrorResponse,
  throwParsedApiError,
} from "@/lib/api/errors";

describe("api error parser", () => {
  it.each([
    [413, "request.payload_too_large"],
    [415, "request.unsupported_media_type"],
    [502, "dependency.invalid_response"],
    [504, "dependency.timeout"],
  ])("classifies HTTP %s without an error body", (status, code) => {
    expect(parseApiErrorPayload(null, status)).toMatchObject({ status, code });
  });

  it("localizes fallback text without translating stable codes or backend messages", () => {
    expect(parseApiErrorPayload(null, 504, "tr")).toMatchObject({
      code: "dependency.timeout",
      userMessage: "İstek zaman aşımına uğradı. Lütfen tekrar deneyin.",
    });
    expect(
      parseApiErrorPayload(
        {
          error: {
            code: "database.connection_failed",
            message: "Veritabanına ulaşılamıyor.",
          },
        },
        503,
        "en"
      )
    ).toMatchObject({
      code: "database.connection_failed",
      userMessage: "Veritabanına ulaşılamıyor.",
    });
  });

  it("preserves backend error metadata when throwing a domain request failure", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "dependency.timeout",
          message: "Bağımlılık zaman aşımına uğradı.",
          details: { dependency: "rag" },
          field_errors: [],
          request_id: "req-timeout",
        },
      }),
      { status: 504 }
    );
    await expect(
      throwParsedApiError(response, "Fallback")
    ).rejects.toMatchObject({
      name: "ApiRequestError",
      status: 504,
      code: "dependency.timeout",
      message: "Bağımlılık zaman aşımına uğradı.",
      requestId: "req-timeout",
      details: { dependency: "rag" },
      fieldErrors: [],
    });
  });
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

  it("replaces the gateway's HTML error page with the status message", async () => {
    // APISIX answers a dead or slow upstream with nginx's own page, not the envelope.
    const page =
      "<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n" +
      "<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>openresty</center>\r\n" +
      "</body>\r\n</html>\r\n";
    expect(parseApiErrorPayload(page, 502, "en")).toMatchObject({
      status: 502,
      code: "dependency.invalid_response",
      userMessage: "The service is currently unavailable. Please try again.",
      raw: page,
    });

    const response = new Response(
      page.replace(/502 Bad Gateway/g, "504 Gateway Time-out"),
      {
        status: 504,
        headers: { "content-type": "text/html" },
      }
    );
    await expect(parseApiErrorResponse(response, "tr")).resolves.toMatchObject({
      status: 504,
      code: "dependency.timeout",
      userMessage: "İstek zaman aşımına uğradı. Lütfen tekrar deneyin.",
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
