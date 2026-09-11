/**
 * The load-time refit must wait until xyflow has actually measured the
 * graph. A draft/preview populates the store asynchronously and each node
 * first mounts as a zero-size skeleton (TemplateNode, while its template
 * loads), so fitting on the `nodes.length` 0→N change alone frames nothing
 * and the real graph ends up off-screen. The gate is `useNodesInitialized`.
 */

import { act, render } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { FlowCanvas } from "../FlowCanvas";
import type { PortType } from "../types/flow";

const fitViewSpy = jest.fn();
let mockNodesInitialized = false;

jest.mock("@xyflow/react", () => {
  const actual = jest.requireActual("@xyflow/react");
  return {
    ...actual,
    useNodesInitialized: () => mockNodesInitialized,
    useReactFlow: (...args: unknown[]) => {
      const instance = actual.useReactFlow(...args);
      return {
        ...instance,
        fitView: (...fvArgs: unknown[]) => {
          fitViewSpy(...fvArgs);
          return instance.fitView(...fvArgs);
        },
      };
    },
  };
});

function lookupAlwaysMessage(): PortType[] | null {
  return ["Message"];
}

function loadGraph(store: ReturnType<typeof createFlowStore>) {
  store.getState().setNodes([
    {
      id: "n1",
      position: { x: 0, y: 0 },
      data: { type: "ChatInput", templateVersion: 1, values: {} },
    },
    {
      id: "n2",
      position: { x: 4000, y: 3000 },
      data: { type: "ChatOutput", templateVersion: 1, values: {} },
    },
  ]);
}

describe("FlowCanvas — load-time fitView gating", () => {
  beforeEach(() => {
    fitViewSpy.mockClear();
    mockNodesInitialized = false;
  });

  it("does not refit while the async-loaded nodes are still unmeasured", () => {
    const store = createFlowStore(); // starts empty, like a draft mid-fetch
    render(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
      </div>
    );

    act(() => loadGraph(store));

    expect(fitViewSpy).not.toHaveBeenCalled();
  });

  it("refits exactly once, after the loaded graph reports measured dimensions", () => {
    const store = createFlowStore();
    const view = render(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
      </div>
    );

    act(() => loadGraph(store));
    expect(fitViewSpy).not.toHaveBeenCalled();

    mockNodesInitialized = true;
    view.rerender(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
      </div>
    );

    expect(fitViewSpy).toHaveBeenCalledTimes(1);

    // A later re-render (e.g. the user adds a node) must not re-center.
    view.rerender(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
      </div>
    );
    expect(fitViewSpy).toHaveBeenCalledTimes(1);
  });

  it("also fits once when the graph is already in the store at mount", () => {
    const store = createFlowStore();
    loadGraph(store); // synchronously present before the canvas mounts

    const view = render(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
      </div>
    );
    // Still nothing until xyflow has measured the nodes.
    expect(fitViewSpy).not.toHaveBeenCalled();

    mockNodesInitialized = true;
    view.rerender(
      <div style={{ width: 800, height: 600 }}>
        <FlowCanvas store={store} lookupHandleTypes={lookupAlwaysMessage} />
      </div>
    );

    expect(fitViewSpy).toHaveBeenCalledTimes(1);
  });
});
