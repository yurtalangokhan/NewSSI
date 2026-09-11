/**
 * Tests for FlowCanvas — the ported canvas shell.
 *
 * These assert on store state, not pixels — the canvas is integration-
 * shaped, and a real drag/connection gesture isn't meaningfully simulable
 * in jsdom. Where a real DOM event is needed (delete, drop), it's
 * dispatched directly; selection is driven by setting `selected: true` on
 * a seed node and letting xyflow's own `onSelectionChange` populate the
 * store naturally — priming the store's `lastSelection` directly before
 * mount does NOT work, because xyflow fires its own (empty) selection
 * change during mount and overwrites it (a real behavior worth knowing,
 * not a workaround).
 *
 * Brief: .tmp/flow-canvas-task-24-brief.md
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { FlowCanvas } from "../FlowCanvas";
import type { PortType } from "../types/flow";

function lookupAlwaysMessage(): PortType[] | null {
  return ["Message"];
}

function seededStore(selectedNodeId?: string) {
  const store = createFlowStore();
  store.getState().setNodes([
    {
      id: "n1",
      position: { x: 0, y: 0 },
      data: { type: "ChatInput", templateVersion: 1, values: {} },
      selected: selectedNodeId === "n1",
    },
    {
      id: "n2",
      position: { x: 200, y: 0 },
      data: { type: "ChatOutput", templateVersion: 1, values: {} },
      selected: selectedNodeId === "n2",
    },
  ]);
  store.getState().resetDirty();
  return store;
}

function renderCanvas(
  store: ReturnType<typeof createFlowStore>,
  readOnly = false
) {
  return render(
    <div style={{ width: 800, height: 600 }}>
      <FlowCanvas
        store={store}
        lookupHandleTypes={lookupAlwaysMessage}
        readOnly={readOnly}
      />
    </div>
  );
}

describe("FlowCanvas — mounting (24.1)", () => {
  it("mounts with nodes from the store, no SSR/ESM errors", () => {
    const store = seededStore();

    renderCanvas(store);

    expect(screen.getByTestId("flow-canvas-wrapper")).toBeInTheDocument();
  });
});

describe("FlowCanvas — delete (24.4, 24.5)", () => {
  it("24.4 — delete takes a snapshot before removing the selection", () => {
    const store = seededStore("n1");
    renderCanvas(store);

    expect(store.getState().past).toHaveLength(0);

    fireEvent.keyDown(screen.getByTestId("flow-canvas-wrapper"), {
      key: "Backspace",
    });

    expect(store.getState().past).toHaveLength(1);
    expect(store.getState().nodes.map((n) => n.id)).toEqual(["n2"]);
  });

  it("24.5 — undo after delete restores the removed node", () => {
    const store = seededStore("n1");
    renderCanvas(store);

    fireEvent.keyDown(screen.getByTestId("flow-canvas-wrapper"), {
      key: "Backspace",
    });
    expect(store.getState().nodes).toHaveLength(1);

    fireEvent.keyDown(screen.getByTestId("flow-canvas-wrapper"), {
      key: "z",
      ctrlKey: true,
    });

    expect(store.getState().nodes).toHaveLength(2);
  });

  it("delete does nothing when the event target is editable (typing in a field)", () => {
    const store = seededStore("n1");

    render(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
        <input data-testid="some-field" />
      </div>
    );

    fireEvent.keyDown(screen.getByTestId("some-field"), { key: "Backspace" });

    expect(store.getState().nodes).toHaveLength(2);
  });

  it("delete does nothing when nothing is selected", () => {
    const store = seededStore();
    renderCanvas(store);

    fireEvent.keyDown(screen.getByTestId("flow-canvas-wrapper"), {
      key: "Backspace",
    });

    expect(store.getState().nodes).toHaveLength(2);
    expect(store.getState().past).toHaveLength(0);
  });

  it("deleting a node also removes edges attached to it", () => {
    const store = seededStore("n1");
    store.getState().setEdges([
      {
        id: "e1",
        source: "n1",
        target: "n2",
        sourceHandle: "message",
        targetHandle: "message",
      },
    ]);
    store.getState().resetDirty();

    renderCanvas(store);

    fireEvent.keyDown(screen.getByTestId("flow-canvas-wrapper"), {
      key: "Backspace",
    });

    expect(store.getState().edges).toHaveLength(0);
  });
});

describe("FlowCanvas — read-only mode", () => {
  it("does not delete when readOnly is set", () => {
    const store = seededStore("n1");
    renderCanvas(store, true);

    fireEvent.keyDown(screen.getByTestId("flow-canvas-wrapper"), {
      key: "Backspace",
    });

    expect(store.getState().nodes).toHaveLength(2);
  });
});
