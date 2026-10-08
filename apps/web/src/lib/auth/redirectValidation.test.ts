import { validateInternalRedirect } from "@/lib/auth/redirectValidation";

describe("validateInternalRedirect", () => {
  it.each([
    "https://evil.example/",
    "//evil.example/",
    "http://evil.example",
    "javascript:alert(1)",
    "/\\evil.example",
    "/%5Cevil.example",
    "https:/evil.example",
  ])("rejects %s", (candidate) => {
    expect(validateInternalRedirect(candidate)).toBeNull();
  });

  it.each(["/app", "/app/chat?id=1", "/settings#tab"])(
    "accepts %s",
    (candidate) => {
      expect(validateInternalRedirect(candidate)).toBe(candidate);
    }
  );

  it("rejects null and undefined", () => {
    expect(validateInternalRedirect(null)).toBeNull();
    expect(validateInternalRedirect(undefined)).toBeNull();
  });
});
