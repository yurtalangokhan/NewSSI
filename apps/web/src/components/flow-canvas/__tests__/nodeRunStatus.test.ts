import { createFlowStore } from "../stores/flowStore";

describe("flowStore nodeRunStatus slice", () => {
  it("45.1 — starts with empty nodeRunStatus map and allows updates", () => {
    const store = createFlowStore();
    expect(store.getState().nodeRunStatus).toEqual({});

    store.getState().updateNodeRunStatus("n1", {
      status: "running",
      startedAt: 1000,
    });

    expect(store.getState().nodeRunStatus["n1"]).toEqual({
      status: "running",
      startedAt: 1000,
      endedAt: null,
      durationMs: null,
      tokenCount: null,
    });

    store.getState().updateNodeRunStatus("n1", {
      status: "done",
      endedAt: 2500,
      durationMs: 1500,
      tokenCount: 42,
    });

    expect(store.getState().nodeRunStatus["n1"]).toEqual({
      status: "done",
      startedAt: 1000,
      endedAt: 2500,
      durationMs: 1500,
      tokenCount: 42,
    });
  });

  it("45.2 — resetNodeRunStatus clears all statuses", () => {
    const store = createFlowStore();
    store.getState().updateNodeRunStatus("n1", { status: "running" });
    store.getState().updateNodeRunStatus("n2", { status: "done" });
    expect(Object.keys(store.getState().nodeRunStatus)).toHaveLength(2);

    store.getState().resetNodeRunStatus();
    expect(store.getState().nodeRunStatus).toEqual({});
  });
});
