import {
  attachIdempotencyKey,
  createIdempotencyKey,
  deriveIdempotencyKey,
  getDerivedIncomingIdempotencyHeaders,
  getIncomingIdempotencyHeaders,
  refreshIdempotencyKey,
  withIdempotencyKey,
} from "@/lib/api/idempotency";

describe("idempotency helpers", () => {
  it("creates UUID idempotency keys", () => {
    const key = createIdempotencyKey();

    expect(key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    );
  });

  it("automatically attaches keys only to non-auth mutations", () => {
    const mutation = attachIdempotencyKey("/api/agents", { method: "POST" });
    const read = attachIdempotencyKey("/api/agents", { method: "GET" });
    const auth = attachIdempotencyKey("/api/auth/refresh", {
      method: "POST",
    });
    const absoluteAuth = attachIdempotencyKey(
      "http://user-service:8000/api/auth/logout",
      { method: "POST" }
    );

    expect(new Headers(mutation.headers).has("Idempotency-Key")).toBe(true);
    expect(new Headers(read.headers).has("Idempotency-Key")).toBe(false);
    expect(new Headers(auth.headers).has("Idempotency-Key")).toBe(false);
    expect(new Headers(absoluteAuth.headers).has("Idempotency-Key")).toBe(
      false
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

  it("refreshes an existing idempotency key without mutating other headers", () => {
    const refreshed = refreshIdempotencyKey({
      method: "POST",
      headers: {
        Accept: "application/json",
        "Idempotency-Key": "old-key",
      },
    });

    expect(new Headers(refreshed.headers).get("accept")).toBe(
      "application/json"
    );
    expect(new Headers(refreshed.headers).get("idempotency-key")).not.toBe(
      "old-key"
    );
  });

  it("does not add an idempotency key when refreshing an unkeyed request", () => {
    const init = { method: "GET" };

    expect(refreshIdempotencyKey(init)).toBe(init);
  });

  it("reads the incoming key for manual backend proxies", () => {
    expect(
      getIncomingIdempotencyHeaders(
        new Request("http://localhost", {
          headers: { "Idempotency-Key": "incoming-key" },
        })
      )
    ).toEqual({ "Idempotency-Key": "incoming-key" });
  });

  it("derives stable and scope-specific child keys", async () => {
    const profileKey = await deriveIdempotencyKey(
      "parent-operation-key",
      "profile"
    );

    await expect(
      deriveIdempotencyKey("parent-operation-key", "profile")
    ).resolves.toBe(profileKey);
    await expect(
      deriveIdempotencyKey("parent-operation-key", "settings")
    ).resolves.not.toBe(profileKey);
    expect(profileKey).toMatch(/^[0-9a-f]{64}$/);
  });

  it("derives an incoming child header only when the parent key exists", async () => {
    const request = new Request("http://localhost", {
      headers: { "Idempotency-Key": "parent-operation-key" },
    });

    await expect(
      getDerivedIncomingIdempotencyHeaders(request, "profile")
    ).resolves.toEqual({
      "Idempotency-Key": await deriveIdempotencyKey(
        "parent-operation-key",
        "profile"
      ),
    });
    await expect(
      getDerivedIncomingIdempotencyHeaders(
        new Request("http://localhost"),
        "profile"
      )
    ).resolves.toEqual({});
  });
});
