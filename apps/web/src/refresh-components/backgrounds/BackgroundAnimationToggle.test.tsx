import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BackgroundAnimationToggle } from "./BackgroundAnimationToggle";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("BackgroundAnimationToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts switched on", () => {
    render(<BackgroundAnimationToggle />);

    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("switches animation off and remembers it", async () => {
    render(<BackgroundAnimationToggle />);

    await userEvent.click(screen.getByRole("switch"));

    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(window.localStorage.getItem("agentic_background_animation")).toBe(
      "off"
    );
  });

  it("reflects a preference stored earlier", () => {
    window.localStorage.setItem("agentic_background_animation", "off");

    render(<BackgroundAnimationToggle />);

    expect(screen.getByRole("switch")).not.toBeChecked();
  });
});
