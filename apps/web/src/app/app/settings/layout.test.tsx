import { screen } from "@testing-library/react";

import SettingsLayout from "@/app/app/settings/layout";
import { render } from "@tests/setup/test-utils";

jest.mock("next/navigation", () => ({
  usePathname: () => "/app/settings/email",
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock("@/layouts/app-layouts", () => ({
  Root: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/layouts/settings-layouts", () => ({
  Root: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Header: () => <div>Settings</div>,
  Body: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

jest.mock("@/refresh-components/buttons/SidebarTab", () => ({
  __esModule: true,
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

describe("SettingsLayout", () => {
  it("links to the dedicated email settings page", () => {
    render(<SettingsLayout>Content</SettingsLayout>);

    expect(
      screen.getByRole("link", { name: "settingsLayout.emailTab" })
    ).toHaveAttribute("href", "/app/settings/email");
  });
});
