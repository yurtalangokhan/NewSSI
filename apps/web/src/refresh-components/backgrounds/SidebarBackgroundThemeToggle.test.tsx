import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SidebarBackgroundThemeToggle } from "./SidebarBackgroundThemeToggle";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("SidebarBackgroundThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts switched on", () => {
    render(<SidebarBackgroundThemeToggle />);

    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("switches the sidebar theme off and remembers it", async () => {
    render(<SidebarBackgroundThemeToggle />);

    await userEvent.click(screen.getByRole("switch"));

    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(
      window.localStorage.getItem("agentic_sidebar_background_theme")
    ).toBe("off");
  });

  it("reflects a preference stored earlier", () => {
    window.localStorage.setItem("agentic_sidebar_background_theme", "off");

    render(<SidebarBackgroundThemeToggle />);

    expect(screen.getByRole("switch")).not.toBeChecked();
  });
});
