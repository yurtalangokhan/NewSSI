import { render } from "@testing-library/react";
import Medallion from "@/refresh-components/avatars/Medallion";

const svgOf = (c: HTMLElement) => c.querySelector("svg") as SVGSVGElement;

describe("Medallion", () => {
  it("renders an svg sized to the given px", () => {
    const { container } = render(
      <Medallion name="Ada" variant="agent" size={36} />
    );
    expect(svgOf(container)).toHaveAttribute("width", "36");
    expect(svgOf(container)).toHaveAttribute("height", "36");
    expect(svgOf(container)).toHaveAttribute("viewBox", "0 0 48 48");
  });

  it("agent variant draws a closed constellation polygon and no flow path", () => {
    const { container } = render(
      <Medallion name="Ada" variant="agent" size={36} />
    );
    expect(container.querySelector("polygon")).toBeInTheDocument();
    expect(
      container.querySelector('[data-part="flowpath"]')
    ).not.toBeInTheDocument();
  });

  it("flow variant draws an open flowing path (dash animation) and no polygon", () => {
    const { container } = render(
      <Medallion name="Fatura" variant="flow" size={36} />
    );
    const path = container.querySelector('[data-part="flowpath"]');
    expect(path).toBeInTheDocument();
    expect(path?.getAttribute("class")).toContain(
      "motion-safe:animate-transponder-flow"
    );
    expect(container.querySelector("polygon")).not.toBeInTheDocument();
  });

  it("full build (size >= 22) includes bezel + arm mark and animates the constellation", () => {
    const { container } = render(
      <Medallion name="Ada" variant="agent" size={30} />
    );
    expect(container.querySelector('[data-part="bezel"]')).toBeInTheDocument();
    expect(container.querySelector('[data-part="arm"]')).toBeInTheDocument();
    expect(
      container
        .querySelector('[data-part="constellation"]')
        ?.getAttribute("class")
    ).toContain("motion-safe:animate-transponder-orbit");
  });

  it("simplified build (size < 22) drops bezel, arm mark and every animation class", () => {
    const { container } = render(
      <Medallion name="Ada" variant="agent" size={16} />
    );
    expect(
      container.querySelector('[data-part="bezel"]')
    ).not.toBeInTheDocument();
    expect(
      container.querySelector('[data-part="arm"]')
    ).not.toBeInTheDocument();
    expect(container.innerHTML).not.toContain("animate-transponder");
  });

  it("is deterministic for a given name", () => {
    const a = render(<Medallion name="Rapor" variant="agent" size={30} />)
      .container.innerHTML;
    const b = render(<Medallion name="Rapor" variant="agent" size={30} />)
      .container.innerHTML;
    expect(a).toBe(b);
  });
});
