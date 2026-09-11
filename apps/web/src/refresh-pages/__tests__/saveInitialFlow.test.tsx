import {
  saveInitialFlow,
  validateInlineFlow,
} from "@/refresh-pages/AgentEditorPage";

describe("saveInitialFlow", () => {
  afterEach(() => jest.clearAllMocks());

  it("publishes the draft immediately for a brand-new agent", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    global.fetch = jest.fn(async (url: any, init: any) => {
      calls.push({ url: String(url), method: init.method });
      return { ok: true, json: async () => ({}), text: async () => "" } as any;
    }) as any;

    await saveInitialFlow("def-1", true, { nodes: [], edges: [] });

    expect(calls).toEqual([
      { url: "/api/agent-definitions/def-1/flow/draft", method: "PUT" },
      { url: "/api/agent-definitions/def-1/flow/publish", method: "POST" },
    ]);
  });

  it("does not publish when editing an existing agent", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    global.fetch = jest.fn(async (url: any, init: any) => {
      calls.push({ url: String(url), method: init.method });
      return { ok: true, json: async () => ({}), text: async () => "" } as any;
    }) as any;

    await saveInitialFlow("def-1", false, { nodes: [], edges: [] });

    expect(calls).toEqual([
      { url: "/api/agent-definitions/def-1/flow/draft", method: "PUT" },
    ]);
  });

  it("throws when the auto-publish is rejected, so the caller can surface it", async () => {
    global.fetch = jest.fn(async (url: any) => {
      if (String(url).endsWith("/flow/publish")) {
        return {
          ok: false,
          status: 400,
          text: async () => '{"errors":[{"code":"FLOW_NO_ENTRY"}]}',
        } as any;
      }
      return { ok: true, json: async () => ({}), text: async () => "" } as any;
    }) as any;

    await expect(
      saveInitialFlow("def-1", true, { nodes: [], edges: [] })
    ).rejects.toThrow(/FLOW_NO_ENTRY/);
  });
});

describe("validateInlineFlow", () => {
  afterEach(() => jest.clearAllMocks());

  it("returns the server verdict for a valid flow", async () => {
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({ valid: true, errors: [] }),
    })) as any;

    await expect(validateInlineFlow({ nodes: [], edges: [] })).resolves.toEqual(
      {
        valid: true,
        errors: [],
      }
    );
  });

  it("surfaces the structural errors for an invalid flow", async () => {
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({
        valid: false,
        errors: [
          { code: "FLOW_NO_EXIT", message: "Flow has no Chat Output node" },
        ],
      }),
    })) as any;

    const result = await validateInlineFlow({ nodes: [], edges: [] });
    expect(result.valid).toBe(false);
    expect(result.errors[0]!.code).toBe("FLOW_NO_EXIT");
  });

  it("treats a failed validation request as invalid rather than letting creation through", async () => {
    global.fetch = jest.fn(async () => ({
      ok: false,
      status: 500,
      text: async () => "boom",
    })) as any;

    const result = await validateInlineFlow({ nodes: [], edges: [] });
    expect(result.valid).toBe(false);
    expect(result.errors[0]!.code).toBe("FLOW_VALIDATE_REQUEST_FAILED");
  });

  it("treats a network error as invalid", async () => {
    global.fetch = jest.fn(async () => {
      throw new Error("offline");
    }) as any;

    const result = await validateInlineFlow({ nodes: [], edges: [] });
    expect(result.valid).toBe(false);
    expect(result.errors[0]!.code).toBe("FLOW_VALIDATE_REQUEST_FAILED");
  });
});
