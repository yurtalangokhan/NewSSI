/**
 * `PortDot` is the palette hover preview's port indicator — same glow
 * visuals as the real on-canvas `NodeHandle` dot (utils/handleVisuals.ts),
 * but usable outside xyflow's node tree (no `<XyHandle>`/`Position`).
 */

import { render, screen } from "@testing-library/react";
import { PortDot } from "./PortDot";

describe("PortDot", () => {
  it("colors the dot by the handle's first declared type", () => {
    render(<PortDot types={["Model"]} testId="port-dot-output" />);

    const dot = screen.getByTestId("port-dot-output");
    expect(dot).toHaveStyle({ background: "#c026d3" });
  });

  it("falls back to the unknown-type color for an unrecognized type", () => {
    render(<PortDot types={["NotARealType"]} testId="port-dot-output" />);

    expect(screen.getByTestId("port-dot-output")).toHaveStyle({
      background: "#9CA3AF",
    });
  });

  it("applies the glow class only when glowing", () => {
    const { rerender } = render(
      <PortDot types={["Model"]} testId="port-dot-output" />
    );
    expect(screen.getByTestId("port-dot-output")).not.toHaveClass(
      "lf-handle-glow"
    );

    rerender(<PortDot types={["Model"]} glowing testId="port-dot-output" />);
    expect(screen.getByTestId("port-dot-output")).toHaveClass("lf-handle-glow");
  });
});
