import { needsGeneratedName } from "./sessionNaming";

describe("needsGeneratedName", () => {
  it("asks for a name when the session has none", () => {
    expect(needsGeneratedName({ description: undefined })).toBe(true);
  });

  it("asks for a name when the description is only whitespace", () => {
    expect(needsGeneratedName({ description: "   " })).toBe(true);
  });

  it("leaves a settled title alone", () => {
    expect(
      needsGeneratedName({
        description: "Ingress sertifika yenileme",
        name_provisional: false,
      })
    ).toBe(false);
  });

  it("asks again when the stored name came from a fallback", () => {
    // The backend names a session even when the model is unreachable, so the
    // sidebar is never empty. That name is a truncated question, and without
    // this flag the client can never tell it apart from a real title -- the
    // session would keep the truncation for good.
    expect(
      needsGeneratedName({
        description: "Kubernetes ingress controller'ım…",
        name_provisional: true,
      })
    ).toBe(true);
  });

  it("treats a missing flag as settled rather than guessing", () => {
    // Older rows predate the flag. Re-naming every one of them on open would
    // spend a model call per session the user merely scrolled past.
    expect(needsGeneratedName({ description: "Docker exit 137" })).toBe(false);
  });
});
