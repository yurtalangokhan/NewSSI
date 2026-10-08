import { act, fireEvent, screen, within } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { MermaidViewer } from "@/components/mermaid/MermaidViewer";

const SVG =
  '<svg id="mmdv999z" viewBox="0 0 10 10"><marker id="mmdv999z_arrow"></marker></svg>';

/**
 * jsdom has no `WheelEvent`/`PointerEvent` support wired into
 * `@testing-library`'s `fireEvent` (properties like `ctrlKey`, `button` and
 * `isPrimary` are silently dropped), so wheel and pointer interactions are
 * dispatched as real DOM events built and fired by hand, wrapped in `act`
 * since they trigger React state updates outside of `fireEvent`.
 */
function dispatchWheel(
  target: Element,
  init: { deltaX?: number; deltaY?: number; ctrlKey?: boolean }
) {
  const event = new WheelEvent("wheel", {
    bubbles: true,
    cancelable: true,
    ...init,
  });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
}

function dispatchPointer(
  target: Element,
  type: "pointerdown" | "pointermove" | "pointerup",
  init: {
    button?: number;
    isPrimary?: boolean;
    clientX: number;
    clientY: number;
  }
) {
  const event = new Event(type, { bubbles: true, cancelable: true }) as Event &
    typeof init & { pointerId: number };
  Object.assign(event, { pointerId: 1, button: 0, isPrimary: true, ...init });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
}

function renderViewer(onOpenChange = jest.fn()) {
  renderWithI18n(
    <MermaidViewer
      open
      onOpenChange={onOpenChange}
      title="mermaid · flowchart"
      svg={SVG}
      svgScopeId="mmdv999z"
    />
  );
  return onOpenChange;
}

describe("MermaidViewer", () => {
  it("shows a copy of the svg under its own ids", () => {
    renderViewer();
    const dialog = screen.getByRole("dialog", { name: "mermaid · flowchart" });
    const content = within(dialog).getByTestId("mermaid-viewer-content");

    expect(content.innerHTML).not.toContain('id="mmdv999z"');
    expect(content.querySelector("marker")?.id).toMatch(/^mmdv\d+z_arrow$/);
  });

  it("zooms with the buttons and resets", () => {
    renderViewer();
    const zoom = screen.getByTestId("mermaid-viewer-zoom");

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(zoom).toHaveTextContent("125%");
    fireEvent.click(screen.getByRole("button", { name: "Reset zoom" }));
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(zoom).toHaveTextContent("80%");
  });

  it("zooms and pans from the keyboard", () => {
    renderViewer();
    const canvas = screen.getByTestId("mermaid-viewer-canvas");
    const content = screen.getByTestId("mermaid-viewer-content");

    fireEvent.keyDown(canvas, { key: "+" });
    fireEvent.keyDown(canvas, { key: "ArrowLeft" });
    expect(content.style.transform).toBe("translate(40px, 0px) scale(1.25)");

    fireEvent.keyDown(canvas, { key: "0" });
    expect(content.style.transform).toBe("translate(0px, 0px) scale(1)");
  });

  it("zooms with ctrl+wheel and prevents the page from zooming", () => {
    renderViewer();
    const canvas = screen.getByTestId("mermaid-viewer-canvas");

    const event = dispatchWheel(canvas, { deltaY: -500, ctrlKey: true });

    expect(event.defaultPrevented).toBe(true);
    expect(screen.getByTestId("mermaid-viewer-zoom")).toHaveTextContent("272%");
  });

  it("pans with a plain wheel", () => {
    renderViewer();
    const canvas = screen.getByTestId("mermaid-viewer-canvas");
    const content = screen.getByTestId("mermaid-viewer-content");

    const event = dispatchWheel(canvas, { deltaX: 15, deltaY: 30 });

    expect(event.defaultPrevented).toBe(true);
    expect(content.style.transform).toBe("translate(-15px, -30px) scale(1)");
    expect(screen.getByTestId("mermaid-viewer-zoom")).toHaveTextContent("100%");
  });

  it("pans with a primary-button pointer drag", () => {
    renderViewer();
    const canvas = screen.getByTestId("mermaid-viewer-canvas");
    const content = screen.getByTestId("mermaid-viewer-content");

    dispatchPointer(canvas, "pointerdown", { clientX: 100, clientY: 100 });
    dispatchPointer(canvas, "pointermove", { clientX: 130, clientY: 80 });

    expect(content.style.transform).toBe("translate(30px, -20px) scale(1)");
  });

  it("does not start a drag on a right-click", () => {
    renderViewer();
    const canvas = screen.getByTestId("mermaid-viewer-canvas");
    const content = screen.getByTestId("mermaid-viewer-content");

    dispatchPointer(canvas, "pointerdown", {
      button: 2,
      clientX: 100,
      clientY: 100,
    });
    dispatchPointer(canvas, "pointermove", { clientX: 130, clientY: 80 });

    expect(content.style.transform).toBe("translate(0px, 0px) scale(1)");
  });

  it("closes on Escape", () => {
    const onOpenChange = renderViewer();

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("uses the Turkish percent format", () => {
    renderWithI18n(
      <MermaidViewer
        open
        onOpenChange={jest.fn()}
        title="t"
        svg={SVG}
        svgScopeId="mmdv999z"
      />,
      "tr"
    );

    expect(screen.getByTestId("mermaid-viewer-zoom")).toHaveTextContent("%100");
  });
});
