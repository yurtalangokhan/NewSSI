import { expandAgentIntoFlow } from "../utils/expandAgentIntoFlow";

describe("expandAgentIntoFlow", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("fetches the expand endpoint, converts the spec, and pastes it at the given position", async () => {
    const wireSpec = {
      version: "1.0",
      nodes: [
        {
          id: "n1",
          type: "ReActAgent",
          template_version: 1,
          position: { x: 0, y: 0 },
          values: { system_prompt: "hi" },
        },
      ],
      edges: [],
    };
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => wireSpec,
    }) as unknown as typeof fetch;

    const paste = jest.fn();
    const store = { getState: () => ({ paste }) } as any;

    await expandAgentIntoFlow("agent-1", store, { x: 100, y: 200 });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/agent-definitions/agent-1/expand",
      expect.objectContaining({ method: "POST" })
    );
    expect(paste).toHaveBeenCalledTimes(1);
    const [selection, position] = paste.mock.calls[0];
    expect(selection.nodes).toHaveLength(1);
    expect(selection.nodes[0].data.type).toBe("ReActAgent");
    expect(position).toEqual({ x: 100, y: 200 });
  });

  it("throws when the endpoint responds with an error status", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      statusText: "Bad Request",
    }) as unknown as typeof fetch;

    const store = { getState: () => ({ paste: jest.fn() }) } as any;

    await expect(
      expandAgentIntoFlow("agent-1", store, { x: 0, y: 0 })
    ).rejects.toThrow("Bad Request");
  });
});
