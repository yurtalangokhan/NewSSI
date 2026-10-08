import { isSafeProxyPath, stripTrustedContextHeaders } from "./proxySecurity";

describe("stripTrustedContextHeaders", () => {
  it("removes the identity header a client must not be able to assert", () => {
    const headers = new Headers({ "x-user-id": "someone-else" });

    stripTrustedContextHeaders(headers);

    expect(headers.get("x-user-id")).toBeNull();
  });

  it("removes every x-internal-* header regardless of case", () => {
    const headers = new Headers({
      "X-Internal-Service-Token": "leaked",
      "x-internal-tenant-id": "other-tenant",
    });

    stripTrustedContextHeaders(headers);

    expect(headers.get("x-internal-service-token")).toBeNull();
    expect(headers.get("x-internal-tenant-id")).toBeNull();
  });

  it("leaves ordinary headers alone", () => {
    const headers = new Headers({
      authorization: "Bearer t",
      "content-type": "application/json",
    });

    stripTrustedContextHeaders(headers);

    expect(headers.get("authorization")).toBe("Bearer t");
    expect(headers.get("content-type")).toBe("application/json");
  });
});

describe("isSafeProxyPath", () => {
  it.each(["/threads/search", "/threads/abc-123/state", "/", "/a.b/c"])(
    "accepts the ordinary path %s",
    (path) => {
      expect(isSafeProxyPath(path)).toBe(true);
    }
  );

  it.each([
    "/../internal/user-service",
    "/threads/../../internal/rag-service",
    "/threads/%2e%2e/%2e%2e/internal",
    "/threads/%2E%2E/internal",
    "/..",
    "/threads/..",
    "\\..\\internal",
  ])("rejects the traversal attempt %s", (path) => {
    expect(isSafeProxyPath(path)).toBe(false);
  });

  it("rejects a malformed escape sequence rather than forwarding it", () => {
    expect(isSafeProxyPath("/threads/%E0%A4%A")).toBe(false);
  });

  it("does not reject a legitimate double dot inside a segment", () => {
    expect(isSafeProxyPath("/files/report..final.pdf")).toBe(true);
  });
});
