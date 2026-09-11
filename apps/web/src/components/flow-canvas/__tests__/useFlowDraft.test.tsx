/**
 * Tests for useFlowDraft — load-on-mount + debounced autosave. Uses a
 * fully injected `FlowDraftApi` (not a mocked global `fetch`) for the
 * debounce tests, since the thing under test is the hook's own timing
 * logic, not the network layer; a separate test drives the *real*
 * default API against a mocked `fetch` specifically to prove 28.5 (never
 * calls publish) against the actual request URLs.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import {
  useFlowDraft,
  saveDraftNow,
  type FlowDraftApi,
} from "../hooks/useFlowDraft";
import type { WireFlowSpec } from "../types/flow";

const DEFINITION_ID = "11111111-1111-1111-1111-111111111111";

function specFixture(): WireFlowSpec {
  return {
    version: "1.0",
    nodes: [
      {
        id: "chatinput-1",
        type: "ChatInput",
        template_version: 1,
        position: { x: 10, y: 20 },
        values: {},
      },
    ],
    edges: [],
    viewport: { x: 5, y: 5, zoom: 1.5 },
  };
}

describe("useFlowDraft — 28.3, loads the draft into the canvas on mount", () => {
  it("populates store.nodes/edges/viewport from the fetched spec", async () => {
    const store = createFlowStore();
    const api: FlowDraftApi = {
      loadDraft: jest.fn().mockResolvedValue(specFixture()),
      saveDraft: jest.fn().mockResolvedValue(undefined),
    };

    const { result } = renderHook(() =>
      useFlowDraft(DEFINITION_ID, store, { api })
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(store.getState().nodes).toHaveLength(1);
    expect(store.getState().nodes[0]!.id).toBe("chatinput-1");
    expect(store.getState().viewport).toEqual({ x: 5, y: 5, zoom: 1.5 });
    expect(store.getState().isDirty).toBe(false);
  });

  it("leaves an empty canvas when there is no draft yet (404)", async () => {
    const store = createFlowStore();
    const api: FlowDraftApi = {
      loadDraft: jest.fn().mockResolvedValue(null),
      saveDraft: jest.fn().mockResolvedValue(undefined),
    };

    const { result } = renderHook(() =>
      useFlowDraft(DEFINITION_ID, store, { api })
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(store.getState().nodes).toHaveLength(0);
    expect(result.current.loadError).toBeNull();
  });
});

describe("useFlowDraft — 28.4, autosave is debounced, not per keystroke", () => {
  it("saves once after a burst of edits settles, with the final state", async () => {
    jest.useFakeTimers();
    const store = createFlowStore();
    const saveDraft = jest.fn().mockResolvedValue(undefined);
    const api: FlowDraftApi = {
      loadDraft: jest.fn().mockResolvedValue(null),
      saveDraft,
    };

    renderHook(() =>
      useFlowDraft(DEFINITION_ID, store, { api, debounceMs: 1000 })
    );
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      store.getState().setNodes([
        {
          id: "n1",
          type: "templateNode",
          position: { x: 0, y: 0 },
          data: { type: "ChatInput", templateVersion: 1, values: {} },
        },
      ]);
    });
    act(() => {
      jest.advanceTimersByTime(400);
    });
    act(() => {
      store
        .getState()
        .setNodes((current) =>
          current.map((n) => ({ ...n, position: { x: 10, y: 10 } }))
        );
    });
    act(() => {
      jest.advanceTimersByTime(400);
    });
    act(() => {
      store
        .getState()
        .setNodes((current) =>
          current.map((n) => ({ ...n, position: { x: 20, y: 20 } }))
        );
    });

    // Still within the debounce window of the *last* edit — no save yet.
    act(() => {
      jest.advanceTimersByTime(400);
    });
    expect(saveDraft).not.toHaveBeenCalled();

    act(() => {
      jest.advanceTimersByTime(700);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(saveDraft).toHaveBeenCalledTimes(1);
    const [, savedSpec] = saveDraft.mock.calls[0]!;
    expect(savedSpec.nodes[0]!.position).toEqual({ x: 20, y: 20 });

    jest.useRealTimers();
  });
});

describe("useFlowDraft — 28.5, autosave never calls publish", () => {
  it("only ever requests the draft endpoint, never .../flow/publish", async () => {
    jest.useFakeTimers();
    const store = createFlowStore();
    const mockFetch = jest
      .fn()
      .mockImplementation(async (url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      });
    global.fetch = mockFetch as unknown as typeof fetch;

    renderHook(() => useFlowDraft(DEFINITION_ID, store, { debounceMs: 500 }));
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      store.getState().setNodes([
        {
          id: "n1",
          type: "templateNode",
          position: { x: 0, y: 0 },
          data: { type: "ChatInput", templateVersion: 1, values: {} },
        },
      ]);
    });
    act(() => {
      jest.advanceTimersByTime(600);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalled();
    for (const call of mockFetch.mock.calls) {
      // `endsWith`, not `toContain`: the load path reads `/flow/published`
      // to seed the canvas when no draft row exists, and that URL contains
      // "/flow/publish" as a substring without being the publish endpoint.
      expect(String(call[0]).endsWith("/flow/publish")).toBe(false);
    }

    jest.useRealTimers();
  });
});

/**
 * Regression tests for the wiped-draft data loss.
 *
 * Publishing consumes the draft row, so a published flow routinely has no
 * draft. The studio then opened on an empty canvas and the very next
 * flush (`saveDraftNow` from the exit guard or `beforeunload`) persisted
 * that emptiness as the new draft — version history showed a draft with
 * every node removed, and the viewer modal reported "no flow designed".
 */
describe("useFlowDraft — a published flow with no draft row", () => {
  it("seeds the canvas from the published version when the draft 404s", async () => {
    const store = createFlowStore();
    const mockFetch = jest.fn().mockImplementation(async (url: string) => {
      if (String(url).endsWith("/flow/draft")) {
        return { ok: false, status: 404, json: async () => ({}) };
      }
      if (String(url).endsWith("/flow/published")) {
        return { ok: true, status: 200, json: async () => specFixture() };
      }
      throw new Error(`unexpected url ${url}`);
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const { result } = renderHook(() => useFlowDraft(DEFINITION_ID, store));

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(store.getState().nodes).toHaveLength(1);
    expect(store.getState().nodes[0]!.id).toBe("chatinput-1");
    // Seeding is not an edit — it must not arm the autosave.
    expect(store.getState().isDirty).toBe(false);
    expect(result.current.loadError).toBeNull();
  });

  it("reports no draft when neither a draft nor a published version exists", async () => {
    const store = createFlowStore();
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({}),
    }) as unknown as typeof fetch;

    const { result } = renderHook(() => useFlowDraft(DEFINITION_ID, store));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(store.getState().nodes).toHaveLength(0);
    expect(result.current.loadError).toBeNull();
  });
});

describe("useFlowDraft — an empty canvas never overwrites a stored draft", () => {
  it("skips the autosave PUT while the canvas holds no nodes", async () => {
    jest.useFakeTimers();
    const store = createFlowStore();
    const saveDraft = jest.fn().mockResolvedValue(undefined);
    const api: FlowDraftApi = {
      loadDraft: jest.fn().mockResolvedValue(null),
      saveDraft,
    };

    renderHook(() =>
      useFlowDraft(DEFINITION_ID, store, { api, debounceMs: 500 })
    );
    await act(async () => {
      await Promise.resolve();
    });

    // Dirties the store without putting anything on the canvas — exactly
    // what a stray change on a failed-to-load canvas looks like.
    act(() => {
      store.getState().setEdges([]);
    });
    expect(store.getState().isDirty).toBe(true);

    act(() => {
      jest.advanceTimersByTime(600);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(saveDraft).not.toHaveBeenCalled();

    jest.useRealTimers();
  });

  it("saveDraftNow does not PUT an empty canvas", async () => {
    const store = createFlowStore();
    const mockFetch = jest
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    global.fetch = mockFetch as unknown as typeof fetch;

    await saveDraftNow(DEFINITION_ID, store);

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("saveDraftNow still PUTs once the canvas has nodes", async () => {
    const store = createFlowStore();
    const mockFetch = jest
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    global.fetch = mockFetch as unknown as typeof fetch;

    act(() => {
      store.getState().setNodes([
        {
          id: "n1",
          type: "templateNode",
          position: { x: 0, y: 0 },
          data: { type: "ChatInput", templateVersion: 1, values: {} },
        },
      ]);
    });

    await saveDraftNow(DEFINITION_ID, store);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(String(mockFetch.mock.calls[0]![0])).toContain("/flow/draft");
  });
});
