/**
 * Tests for the ported flowStore — nodes, edges, selection, dirty tracking,
 * undo/redo (Langflow's snapshot model), and paste.
 *
 * Ported from Langflow (MIT) — src/frontend/src/stores/flowStore.ts +
 * src/frontend/src/stores/flowsManagerStore.ts (undo/redo lives there
 * upstream; consolidated here since we edit one flow per mount, not many
 * flows in memory at once — Langflow's per-flow-id history keying was
 * dropped as unneeded complexity).
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Brief: .tmp/flow-canvas-task-21-brief.md
 */

import type { FlowNodeData } from "../types/flow";
import { createFlowStore } from "../stores/flowStore";

function node(id: string, overrides: Partial<FlowNodeData> = {}) {
  return {
    id,
    position: { x: 0, y: 0 },
    data: { type: "ChatInput", templateVersion: 1, values: {}, ...overrides },
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  sourceHandle = "output",
  targetHandle = "input"
) {
  return { id, source, target, sourceHandle, targetHandle };
}

describe("flowStore — node data shape (21.1)", () => {
  it("carries values only, no template/descriptor field", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1", { values: { a: 1 } })]);

    const stored = store.getState().nodes[0]!.data;
    expect(Object.keys(stored).sort()).toEqual([
      "templateVersion",
      "type",
      "values",
    ]);
  });
});

describe("flowStore — dirty tracking (21.2, and the selection nuance)", () => {
  it("setNodes marks the store dirty", () => {
    const store = createFlowStore();
    expect(store.getState().isDirty).toBe(false);

    store.getState().setNodes([node("n1")]);

    expect(store.getState().isDirty).toBe(true);
  });

  it("setEdges marks the store dirty", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1"), node("n2")]);
    store.getState().resetDirty();

    store.getState().setEdges([edge("e1", "n1", "n2")]);

    expect(store.getState().isDirty).toBe(true);
  });

  it("a pure selection change via onNodesChange does NOT mark the store dirty", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1")]);
    store.getState().resetDirty();

    store
      .getState()
      .onNodesChange([{ id: "n1", type: "select", selected: true }]);

    expect(store.getState().isDirty).toBe(false);
  });

  it("a position change via onNodesChange DOES mark the store dirty", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1")]);
    store.getState().resetDirty();

    store
      .getState()
      .onNodesChange([
        { id: "n1", type: "position", position: { x: 10, y: 10 } },
      ]);

    expect(store.getState().isDirty).toBe(true);
  });
});

describe("flowStore — undo/redo (21.3-21.6, 21.9)", () => {
  it("21.3 — takeSnapshot then undo restores the previous state", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1")]);
    store.getState().takeSnapshot();

    store.getState().setNodes([node("n1"), node("n2")]);
    expect(store.getState().nodes).toHaveLength(2);

    store.getState().undo();

    expect(store.getState().nodes).toHaveLength(1);
    expect(store.getState().nodes[0]!.id).toBe("n1");
  });

  it("21.4 — undo of a multi-node drag is one step, not one per node", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1"), node("n2"), node("n3")]);
    store.getState().takeSnapshot();

    // One gesture: drag 3 nodes, one onNodesChange call with 3 position changes.
    store.getState().onNodesChange([
      { id: "n1", type: "position", position: { x: 5, y: 5 } },
      { id: "n2", type: "position", position: { x: 6, y: 6 } },
      { id: "n3", type: "position", position: { x: 7, y: 7 } },
    ]);

    store.getState().undo();

    const positions = store.getState().nodes.map((n) => n.position);
    expect(positions).toEqual([
      { x: 0, y: 0 },
      { x: 0, y: 0 },
      { x: 0, y: 0 },
    ]);
  });

  it("21.5 — redo after undo restores the forward state", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1")]);
    store.getState().takeSnapshot();
    store.getState().setNodes([node("n1"), node("n2")]);

    store.getState().undo();
    expect(store.getState().nodes).toHaveLength(1);

    store.getState().redo();
    expect(store.getState().nodes).toHaveLength(2);
  });

  it("21.6 — a new mutation after undo clears the redo stack", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1")]);
    store.getState().takeSnapshot();
    store.getState().setNodes([node("n1"), node("n2")]);
    store.getState().takeSnapshot();
    store.getState().setNodes([node("n1"), node("n2"), node("n3")]);

    store.getState().undo(); // back to 2 nodes
    store.getState().takeSnapshot();
    store.getState().setNodes([node("n1")]); // a fresh edit

    store.getState().redo(); // must do nothing — redo stack was cleared

    expect(store.getState().nodes).toHaveLength(1);
  });

  it("21.9 — history depth is bounded", () => {
    const store = createFlowStore();
    const maxHistory = store.getState().maxHistorySize;

    for (let i = 0; i < maxHistory + 20; i++) {
      store.getState().setNodes([node(`n${i}`)]);
      store.getState().takeSnapshot();
    }

    expect(store.getState().past.length).toBeLessThanOrEqual(maxHistory);
  });

  it("takeSnapshot skips a duplicate of the last entry", () => {
    const store = createFlowStore();
    store.getState().setNodes([node("n1")]);
    store.getState().takeSnapshot();
    store.getState().takeSnapshot(); // identical state — must not push again

    expect(store.getState().past).toHaveLength(1);
  });
});

describe("flowStore — paste (21.7, 21.8)", () => {
  it("21.7 — pasted nodes get fresh ids, never colliding with originals", () => {
    const store = createFlowStore();
    const original = node("n1", { type: "ZeroShotAgent" });
    store.getState().setNodes([original]);

    store
      .getState()
      .paste({ nodes: [original], edges: [] }, { x: 100, y: 100 });

    const ids = store.getState().nodes.map((n) => n.id);
    expect(ids).toContain("n1");
    expect(ids).toHaveLength(2);
    expect(ids[1]).not.toBe("n1");
    expect(ids[1]).toMatch(/^ZeroShotAgent-/);
  });

  it("21.8 — paste preserves internal edges between pasted nodes, re-pointed to the new ids", () => {
    const store = createFlowStore();
    const a = node("a", { type: "ChatInput" });
    const b = node("b", { type: "ZeroShotAgent" });
    store.getState().setNodes([a, b]);
    store.getState().setEdges([edge("e1", "a", "b", "message", "input")]);

    store
      .getState()
      .paste(
        { nodes: [a, b], edges: [edge("e1", "a", "b", "message", "input")] },
        { x: 200, y: 200 }
      );

    const newNodeIds = store
      .getState()
      .nodes.map((n) => n.id)
      .filter((id) => id !== "a" && id !== "b");
    expect(newNodeIds).toHaveLength(2);

    const newEdges = store.getState().edges.filter((e) => e.id !== "e1");
    expect(newEdges).toHaveLength(1);
    expect(newNodeIds).toContain(newEdges[0]!.source);
    expect(newNodeIds).toContain(newEdges[0]!.target);
    expect(newEdges[0]!.sourceHandle).toBe("message");
    expect(newEdges[0]!.targetHandle).toBe("input");
  });

  it("paste does not carry over an edge whose other endpoint is outside the selection", () => {
    const store = createFlowStore();
    const a = node("a", { type: "ChatInput" });
    const b = node("b", { type: "ZeroShotAgent" });
    const c = node("c", { type: "ChatOutput" });
    store.getState().setNodes([a, b, c]);
    store
      .getState()
      .setEdges([
        edge("e1", "a", "b", "message", "input"),
        edge("e2", "b", "c", "output", "message"),
      ]);

    // Only copy {a, b} and the edge between them — not c, not e2.
    store
      .getState()
      .paste(
        { nodes: [a, b], edges: [edge("e1", "a", "b", "message", "input")] },
        { x: 50, y: 50 }
      );

    const newEdges = store
      .getState()
      .edges.filter((e) => e.id !== "e1" && e.id !== "e2");
    expect(newEdges).toHaveLength(1); // only the internal a->b edge duplicated
  });
});
