/**
 * `useDropHandler` is the confirmed-add path a palette drop actually goes
 * through — the fix for the "phantom Recently used" bug (see
 * ComponentSidebar.test.tsx's 25.7 block) depends on this being the ONLY
 * place usage is recorded. This guards that: recording only happens once a
 * node is actually added, never before.
 */

import { renderHook, act } from "@testing-library/react";
import { useDropHandler } from "./useCanvasWiring";
import { createFlowStore } from "../stores/flowStore";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const STORAGE_KEY = "flow-canvas:recent-components";

const GROUPED: GroupedComponentTemplates = {
  core: [
    {
      type: "ChatInput",
      category: "core",
      display_name: "Chat Input",
      description: "",
      icon: null,
      template_version: 1,
      lifecycle: "stable",
      kind: "execution",
      inputs: {},
      handles: {
        inputs: [],
        outputs: [{ name: "message", types: ["Message"] }],
      },
    },
  ],
};

beforeEach(() => {
  window.localStorage.clear();
});

describe("useDropHandler — records usage only on a confirmed add", () => {
  it("does not touch recents before the handler is called", () => {
    const store = createFlowStore();
    renderHook(() => useDropHandler(store, GROUPED));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("adds the node and records usage together once the handler runs", () => {
    const store = createFlowStore();
    const { result } = renderHook(() => useDropHandler(store, GROUPED));

    act(() => {
      result.current("ChatInput", { x: 10, y: 20 });
    });

    expect(store.getState().nodes).toHaveLength(1);
    expect(store.getState().nodes[0]!.data.type).toBe("ChatInput");
    expect(
      JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]")
    ).toEqual(["ChatInput"]);
  });

  it("does not add a node or record usage for an unknown component type", () => {
    const store = createFlowStore();
    const { result } = renderHook(() => useDropHandler(store, GROUPED));

    act(() => {
      result.current("NotRegistered", { x: 0, y: 0 });
    });

    expect(store.getState().nodes).toHaveLength(0);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
