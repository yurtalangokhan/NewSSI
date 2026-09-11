import { fireEvent, render, screen } from "@testing-library/react";
import { ReactFlow, ReactFlowProvider } from "@xyflow/react";
import React from "react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import { CanvasControls } from "../components/CanvasControls";

function renderControls(
  props: React.ComponentProps<typeof CanvasControls>,
  locale = "en"
) {
  const i18n = createI18nInstance(locale as any);
  return render(
    <I18nextProvider i18n={i18n}>
      <ReactFlowProvider>
        <ReactFlow nodes={[]} edges={[]}>
          <CanvasControls {...props} />
        </ReactFlow>
      </ReactFlowProvider>
    </I18nextProvider>
  );
}

describe("CanvasControls", () => {
  describe("fullscreen toggle", () => {
    it("renders maximize button when not in fullscreen", () => {
      const onToggle = jest.fn();
      renderControls({ isFullscreen: false, onToggleFullscreen: onToggle });

      const btn = screen.getByTestId("canvas-toggle-fullscreen");
      expect(btn).toHaveAttribute("aria-label", "Fullscreen");

      fireEvent.click(btn);
      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it("renders minimize button with exit label and active style when in fullscreen", () => {
      const onToggle = jest.fn();
      renderControls({ isFullscreen: true, onToggleFullscreen: onToggle });

      const btn = screen.getByTestId("canvas-toggle-fullscreen");
      expect(btn).toHaveAttribute("aria-label", "Exit Fullscreen (Esc)");
      expect(btn.className).toContain("bg-accent");

      fireEvent.click(btn);
      expect(onToggle).toHaveBeenCalledTimes(1);
    });
  });

  describe("zoom percentage indicator", () => {
    it("renders the zoom percentage button in 100% format for English", () => {
      renderControls({}, "en");
      const percentageBtn = screen.getByTestId("canvas-zoom-percentage");
      expect(percentageBtn).toBeInTheDocument();
      expect(percentageBtn.textContent).toBe("100%");
    });

    it("renders the zoom percentage button in %100 format for Turkish", () => {
      renderControls({}, "tr");
      const percentageBtn = screen.getByTestId("canvas-zoom-percentage");
      expect(percentageBtn).toBeInTheDocument();
      expect(percentageBtn.textContent).toBe("%100");
    });

    it("switches to input on single click and cancels on Escape", () => {
      renderControls({});
      const percentageBtn = screen.getByTestId("canvas-zoom-percentage");
      fireEvent.click(percentageBtn);

      const input = screen.getByTestId("canvas-zoom-input");
      expect(input).toBeInTheDocument();

      fireEvent.keyDown(input, { key: "Escape" });
      expect(screen.queryByTestId("canvas-zoom-input")).not.toBeInTheDocument();
      expect(screen.getByTestId("canvas-zoom-percentage")).toBeInTheDocument();
    });

    it("applies zoom on Enter", () => {
      renderControls({});
      const percentageBtn = screen.getByTestId("canvas-zoom-percentage");
      fireEvent.click(percentageBtn);

      const input = screen.getByTestId("canvas-zoom-input");
      fireEvent.change(input, { target: { value: "150" } });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(screen.queryByTestId("canvas-zoom-input")).not.toBeInTheDocument();
    });

    it("resets to 100% on double click", () => {
      renderControls({});
      const percentageBtn = screen.getByTestId("canvas-zoom-percentage");
      fireEvent.doubleClick(percentageBtn);

      expect(screen.queryByTestId("canvas-zoom-input")).not.toBeInTheDocument();
      expect(screen.getByTestId("canvas-zoom-percentage")).toBeInTheDocument();
    });

    it("renders in compact mode with smaller button styles", () => {
      renderControls({ compact: true });
      const controls = screen.getByTestId("canvas-controls");
      expect(controls.className).toContain("gap-0.5");
      const zoomOut = screen.getByTestId("canvas-zoom-out");
      expect(zoomOut.className).toContain("h-6 w-6");
    });
  });
});
