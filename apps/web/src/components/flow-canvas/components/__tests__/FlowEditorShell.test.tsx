/**
 * Regression test for: opening the canvas fullscreen from inside a modal
 * (AgentViewerModal → FlowAgentPreview) made it uninteractable — clicks,
 * zoom controls, everything landed on the modal behind it instead.
 *
 * Root cause: Radix Dialog's `disableOutsidePointerEvents` sets
 * `document.body.style.pointerEvents = "none"` while open, then re-enables
 * `pointer-events: auto` only on its own dialog content node so that one
 * stays clickable. The old portal-target logic nested the fullscreen
 * canvas *inside* that dialog content specifically to inherit that
 * `auto` — but that same ancestor is centered with a CSS `transform`,
 * which becomes the containing block for the canvas's `position: fixed`,
 * so "fullscreen" was actually clipped to the dialog's own (much
 * smaller) box instead of the viewport.
 *
 * Fix: portal straight to `document.body` (a true `position: fixed`
 * viewport, no transformed ancestor) and set `pointer-events: auto`
 * directly on the fullscreen container itself, so it doesn't need to
 * borrow that property from a dialog ancestor at all.
 */

import { act, render, fireEvent, screen } from "@testing-library/react";
import { createFlowStore } from "../../stores/flowStore";
import { FlowEditorShell } from "../FlowEditorShell";

describe("FlowEditorShell — fullscreen while nested in a modal", () => {
  afterEach(() => {
    document.body.style.pointerEvents = "";
  });

  it("portals fullscreen content directly under document.body, not inside a transformed dialog ancestor", () => {
    const store = createFlowStore();

    // Simulates AgentViewerModal: a Radix-style dialog wrapper the shell
    // is rendered inside of.
    render(
      <div
        role="dialog"
        style={{ transform: "translate(-50%, -50%)", overflow: "hidden" }}
      >
        <FlowEditorShell store={store} className="wrapper">
          <div>canvas content</div>
        </FlowEditorShell>
      </div>
    );

    act(() => {
      store.getState().setFullscreen(true);
    });

    const fullscreenShell = document.querySelector('[data-fullscreen="true"]');
    expect(fullscreenShell).toBeInTheDocument();
    // Must not be a descendant of the `role="dialog"` wrapper — that
    // ancestor's transform is exactly what clipped fullscreen down to
    // the modal's own box.
    expect(
      document.querySelector('[role="dialog"] [data-fullscreen="true"]')
    ).toBeNull();
    expect(fullscreenShell?.parentElement).toBe(document.body);
  });

  it("stays clickable while Radix has disabled pointer-events on the rest of the page", () => {
    const store = createFlowStore();
    const onCanvasClick = jest.fn();

    render(
      <div role="dialog">
        <FlowEditorShell store={store} className="wrapper">
          <button onClick={onCanvasClick}>zoom in</button>
        </FlowEditorShell>
      </div>
    );

    act(() => {
      store.getState().setFullscreen(true);
    });

    // What Radix's DismissableLayer does to <body> while the dialog is
    // open with disableOutsidePointerEvents (real Dialog behavior,
    // reproduced directly here since jsdom's fireEvent doesn't perform
    // real hit-testing against computed pointer-events).
    document.body.style.pointerEvents = "none";

    const fullscreenShell = document.querySelector(
      '[data-fullscreen="true"]'
    ) as HTMLElement;
    expect(fullscreenShell.style.pointerEvents).toBe("auto");

    fireEvent.click(screen.getByRole("button", { name: "zoom in" }));
    expect(onCanvasClick).toHaveBeenCalledTimes(1);
  });

  it("hides the parent dialog while fullscreen and restores its visibility on exit", () => {
    const store = createFlowStore();

    render(
      <div role="dialog" data-testid="parent-dialog">
        <FlowEditorShell store={store} className="wrapper">
          <div>canvas content</div>
        </FlowEditorShell>
      </div>
    );

    const dialog = screen.getByTestId("parent-dialog");
    expect(dialog.style.visibility).toBe("");

    act(() => {
      store.getState().setFullscreen(true);
    });

    expect(dialog.style.visibility).toBe("hidden");
    expect(dialog.style.pointerEvents).toBe("none");

    const fullscreenShell = document.querySelector('[data-fullscreen="true"]');
    expect(fullscreenShell?.className).toContain("z-canvas-fullscreen-modal");

    act(() => {
      store.getState().setFullscreen(false);
    });

    expect(dialog.style.visibility).toBe("");
    expect(dialog.style.pointerEvents).toBe("");
  });

  it("exits fullscreen on Escape when nested in a dialog without being blocked by parent dialog", () => {
    const store = createFlowStore();

    render(
      <div role="dialog" data-testid="parent-dialog">
        <FlowEditorShell store={store} className="wrapper">
          <div>canvas content</div>
        </FlowEditorShell>
      </div>
    );

    act(() => {
      store.getState().setFullscreen(true);
    });
    expect(store.getState().isFullscreen).toBe(true);

    act(() => {
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
      );
    });

    expect(store.getState().isFullscreen).toBe(false);
  });
});
