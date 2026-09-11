/**
 * Tests for useFlowValidation — debounced POST /validate-flow, mapping
 * errors/warnings onto nodes/edges by id.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { useFlowValidation } from "../hooks/useFlowValidation";

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

beforeEach(() => {
  global.fetch = jest.fn() as unknown as typeof fetch;
});

describe("useFlowValidation — 28.9, errors block publish, warnings do not", () => {
  it("hasErrors is true when the response carries errors", async () => {
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, {
        valid: false,
        errors: [
          {
            code: "FLOW_UNKNOWN_COMPONENT",
            message: "bad",
            node_id: "n1",
            edge_id: null,
          },
        ],
        warnings: [],
      })
    );
    const store = createFlowStore();

    const { result } = renderHook(() => useFlowValidation(store));

    await waitFor(() => expect(result.current.result).not.toBeNull());
    expect(result.current.hasErrors).toBe(true);
    expect(result.current.errorsByNode.get("n1")).toHaveLength(1);
  });

  it("hasErrors is false when only warnings are present", async () => {
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, {
        valid: true,
        errors: [],
        warnings: [
          {
            code: "FLOW_UNSTABLE_COMPONENT",
            message: "beta component",
            node_id: "n2",
            edge_id: null,
          },
        ],
      })
    );
    const store = createFlowStore();

    const { result } = renderHook(() => useFlowValidation(store));

    await waitFor(() => expect(result.current.result).not.toBeNull());
    expect(result.current.hasErrors).toBe(false);
    expect(result.current.warningsByNode.get("n2")).toHaveLength(1);
  });
});

describe("useFlowValidation — debounces re-validation on structural changes", () => {
  it("does not issue a second request for every rapid edit", async () => {
    jest.useFakeTimers();
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, { valid: true, errors: [], warnings: [] })
    );
    const store = createFlowStore();

    renderHook(() => useFlowValidation(store, { debounceMs: 500 }));
    await act(async () => {
      await Promise.resolve();
    });
    const callsAfterMount = (global.fetch as jest.Mock).mock.calls.length;
    expect(callsAfterMount).toBe(1); // validated once on mount

    act(() => {
      store.getState().setNodes([]);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    act(() => {
      store.getState().setEdges([]);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });

    expect((global.fetch as jest.Mock).mock.calls.length).toBe(callsAfterMount); // still debounced

    act(() => {
      jest.advanceTimersByTime(500);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect((global.fetch as jest.Mock).mock.calls.length).toBe(
      callsAfterMount + 1
    );

    jest.useRealTimers();
  });

  it("does not re-arm itself off its own setNodeErrors write (no infinite validation loop)", async () => {
    jest.useFakeTimers();
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, {
        valid: false,
        errors: [{ code: "X", message: "m", node_id: "n1", edge_id: null }],
        warnings: [],
      })
    );
    const store = createFlowStore();

    renderHook(() => useFlowValidation(store, { debounceMs: 500 }));
    await act(async () => {
      await Promise.resolve();
    });
    const callsAfterMount = (global.fetch as jest.Mock).mock.calls.length;
    expect(callsAfterMount).toBe(1);
    // The mount validation's response writes nodeErrors into the store —
    // that write must not be mistaken for a content edit and re-arm the
    // debounce timer. Advancing well past debounceMs with no further user
    // edit must not produce a second request.
    act(() => {
      jest.advanceTimersByTime(5000);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect((global.fetch as jest.Mock).mock.calls.length).toBe(callsAfterMount);

    jest.useRealTimers();
  });

  it("still re-validates on a real edit even after a setNodeErrors write", async () => {
    jest.useFakeTimers();
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, { valid: true, errors: [], warnings: [] })
    );
    const store = createFlowStore();

    renderHook(() => useFlowValidation(store, { debounceMs: 500 }));
    await act(async () => {
      await Promise.resolve();
    });
    const callsAfterMount = (global.fetch as jest.Mock).mock.calls.length;

    act(() => {
      store.getState().setNodes([]);
      jest.advanceTimersByTime(500);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect((global.fetch as jest.Mock).mock.calls.length).toBe(
      callsAfterMount + 1
    );

    jest.useRealTimers();
  });
});
