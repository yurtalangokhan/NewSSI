import React from "react";
import { render, screen } from "@testing-library/react";
import Logo from "./Logo";

jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => ({
    enterpriseSettings: null,
  }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("Logo component", () => {
  it("renders CSS-switchable light and dark logo images when unfolded to prevent theme flash", () => {
    const { container } = render(<Logo />);
    const images = container.querySelectorAll("img");
    expect(images.length).toBe(2);

    const lightImage = images[0]!;
    const darkImage = images[1]!;

    // Light logo must have dark:hidden so it's hidden in dark mode
    expect(lightImage.getAttribute("src")).toContain("/logo.turksat.svg");
    expect(lightImage.className).toContain("dark:hidden");

    // Dark logo must have hidden dark:block so it's only shown in dark mode
    expect(darkImage.getAttribute("src")).toContain("/logo.turksat.white.svg");
    expect(darkImage.className).toContain("hidden");
    expect(darkImage.className).toContain("dark:block");
  });

  it("renders TurksatMark SVG when folded", () => {
    const { container } = render(<Logo folded />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("aria-label", "turksatMarkAriaLabel");

    const images = container.querySelectorAll("img");
    expect(images.length).toBe(0);
  });
});
