import React from "react";
import { render } from "@testing-library/react";
import SidebarWrapper from "@/sections/sidebar/SidebarWrapper";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock("@/refresh-components/Logo", () => ({
  __esModule: true,
  default: () => <span>logo</span>,
}));
jest.mock("@opal/components", () => ({
  Button: () => <button type="button" />,
}));

describe("SidebarWrapper", () => {
  it("uses the default surface unless the TÜRKSAT theme is requested", () => {
    const { container } = render(<SidebarWrapper>content</SidebarWrapper>);
    const aside = container.querySelector("aside")!;

    expect(aside).not.toHaveAttribute("data-sidebar-theme");
    expect(aside).toHaveClass("bg-background-tint-02");
  });

  it("marks the sidebar for the TÜRKSAT theme and drops the default surface", () => {
    const { container } = render(
      <SidebarWrapper turksatTheme>content</SidebarWrapper>
    );
    const aside = container.querySelector("aside")!;

    expect(aside).toHaveAttribute("data-sidebar-theme", "turksat");
    expect(aside).not.toHaveClass("bg-background-tint-02");
  });
});
