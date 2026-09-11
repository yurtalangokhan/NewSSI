/**
 * Fullscreen behaviour for the flow editor.
 *
 * Every case here is a bug that actually shipped, so they stay:
 *
 *  - expanding the page root dragged the create-agent form's "won't be
 *    saved yet" notice onto the fullscreen canvas;
 *  - expanding only `FlowCanvas` dropped the component palette, leaving
 *    nothing to drag components from;
 *  - rendering the overlay in place left the app's footer showing through,
 *    because `AppLayouts.Root` sets `container-type` and so becomes the
 *    containing block for `position: fixed` descendants — no `z-index`
 *    can fix that, only leaving the subtree via a portal;
 *  - unmounting while expanded left the page scroll-locked.
 */

import { act, render, screen } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { FlowEditorShell } from "../components/FlowEditorShell";

function renderShell() {
  const store = createFlowStore();
  const view = render(
    <FlowEditorShell store={store} className="inline-shell">
      <div data-testid="palette">palette</div>
      <div data-testid="canvas">canvas</div>
    </FlowEditorShell>
  );
  return { store, view };
}

describe("flow editor fullscreen", () => {
  afterEach(() => {
    document.body.style.overflow = "";
  });

  it("starts collapsed and renders inline", () => {
    const { store } = renderShell();

    expect(store.getState().isFullscreen).toBe(false);
    expect(screen.getByTestId("flow-editor-shell")).not.toHaveAttribute(
      "data-fullscreen"
    );
  });

  it("keeps the palette alongside the canvas when expanded", () => {
    const { store } = renderShell();

    act(() => store.getState().setFullscreen(true));

    // Both, not just the canvas — dropping the palette made the expanded
    // canvas unusable.
    expect(screen.getByTestId("palette")).toBeInTheDocument();
    expect(screen.getByTestId("canvas")).toBeInTheDocument();
  });

  it("escapes the app shell by portalling to document.body", () => {
    const { store, view } = renderShell();

    act(() => store.getState().setFullscreen(true));

    const shell = screen.getByTestId("flow-editor-shell");
    expect(shell).toHaveAttribute("data-fullscreen", "true");
    // Outside the component's own container, or the app shell's
    // `container-type` would trap the fixed overlay inside it.
    expect(view.container.contains(shell)).toBe(false);
    expect(document.body.contains(shell)).toBe(true);
    expect(shell.className).toContain("z-canvas-fullscreen");
  });

  it("carries the theme scope into the portal", () => {
    const { store } = renderShell();

    act(() => store.getState().setFullscreen(true));

    // The portal renders outside the editor page, so the `--lf-*` tokens
    // scoped to `.langflow-canvas` must be re-declared or the palette
    // resolves to nothing.
    expect(screen.getByTestId("flow-editor-shell").className).toContain(
      "langflow-canvas"
    );
  });

  it("locks page scroll while expanded and restores it on exit", () => {
    const { store } = renderShell();

    act(() => store.getState().setFullscreen(true));
    expect(document.body.style.overflow).toBe("hidden");

    act(() => store.getState().setFullscreen(false));
    expect(document.body.style.overflow).not.toBe("hidden");
  });

  it("exits on Escape", () => {
    const { store } = renderShell();
    act(() => store.getState().setFullscreen(true));

    act(() => {
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
      );
    });

    expect(store.getState().isFullscreen).toBe(false);
  });

  it("does not leave the page scroll-locked after unmounting while expanded", () => {
    const { store, view } = renderShell();

    act(() => store.getState().setFullscreen(true));
    expect(document.body.style.overflow).toBe("hidden");

    view.unmount();
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
