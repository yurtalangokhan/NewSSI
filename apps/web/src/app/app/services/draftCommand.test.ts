import {
  consumeAppDraftCommand,
  saveAppDraftCommand,
} from "@/app/app/services/draftCommand";

describe("app draft command storage", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      value: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        removeItem: (key: string) => values.delete(key),
        setItem: (key: string, value: string) => values.set(key, value),
      },
    });
  });

  it("saves and consumes a draft command once", () => {
    saveAppDraftCommand({
      agentId: "42",
      message: "hello",
      submitOnLoad: true,
    });

    expect(consumeAppDraftCommand({ agentId: "42" })).toEqual({
      agentId: "42",
      message: "hello",
      submitOnLoad: true,
    });
    expect(consumeAppDraftCommand({ agentId: "42" })).toBeNull();
  });

  it("keeps a draft command when the current agent does not match", () => {
    saveAppDraftCommand({
      agentId: "42",
      message: "hello",
      submitOnLoad: true,
    });

    expect(consumeAppDraftCommand({ agentId: "7" })).toBeNull();
    expect(consumeAppDraftCommand({ agentId: "42" })?.message).toBe("hello");
  });
});
