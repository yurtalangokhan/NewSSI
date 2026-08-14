import {
  createIdempotencyKey,
  withIdempotencyKey,
} from "@/lib/api/idempotency";

describe("idempotency helpers", () => {
  it("creates UUID idempotency keys", () => {
    const key = createIdempotencyKey();

    expect(key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    );
  });

  it("adds the Idempotency-Key header without mutating the input headers", () => {
    const original = {
      Accept: "application/json",
    };

    const headers = withIdempotencyKey(original, "idem-web-123");

    expect(headers).toEqual({
      Accept: "application/json",
      "Idempotency-Key": "idem-web-123",
    });
    expect(original).toEqual({
      Accept: "application/json",
    });
  });

  it("replaces plain object idempotency headers case-insensitively", () => {
    const headers = withIdempotencyKey(
      {
        Accept: "application/json",
        "idempotency-key": "old-key",
      },
      "new-key"
    );

    expect(headers).toEqual({
      Accept: "application/json",
      "Idempotency-Key": "new-key",
    });
  });

  it("preserves existing Headers values", () => {
    const headers = withIdempotencyKey(
      new Headers({ Authorization: "Bearer token" }),
      "idem-web-456"
    );

    expect(new Headers(headers).get("authorization")).toBe("Bearer token");
    expect(new Headers(headers).get("idempotency-key")).toBe("idem-web-456");
  });
});
