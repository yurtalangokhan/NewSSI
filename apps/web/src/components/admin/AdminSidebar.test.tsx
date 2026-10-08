/**
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import AdminSidebar from "@/sections/sidebar/AdminSidebar";

const mockUseUser = jest.fn();

jest.mock("next/navigation", () => ({
  usePathname: () => "/admin/organizations",
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock("@/app/admin/kg/utils", () => ({
  useIsKGExposed: () => ({ kgExposed: false }),
}));
jest.mock("@/lib/hooks/useCustomAnalyticsEnabled", () => ({
  useCustomAnalyticsEnabled: () => ({ customAnalyticsEnabled: false }),
}));
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => mockUseUser(),
}));
jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => ({ settings: {}, webVersion: null }),
}));
jest.mock("@/lib/api/domains/billing/hooks", () => ({
  useBillingInformation: () => ({ data: null }),
  useLicense: () => ({ data: null }),
}));
jest.mock("@/components/settings/usePaidEnterpriseFeaturesEnabled", () => ({
  usePaidEnterpriseFeaturesEnabled: () => false,
}));
jest.mock("@/providers/AppSidebarProvider", () => ({
  useAppSidebarContext: () => ({ folded: false, setFolded: jest.fn() }),
}));
jest.mock("@/sections/sidebar/SidebarWrapper", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/sections/sidebar/SidebarBody", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/sections/sidebar/SidebarSection", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/refresh-components/buttons/SidebarTab", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/sections/sidebar/UserAvatarPopover", () => ({
  __esModule: true,
  default: () => null,
}));

it("keeps the admin menu visible while existing permissions revalidate", () => {
  mockUseUser.mockReturnValue({
    permissions: ["organization:read"],
    isPermissionsLoading: false,
    hasAllPermissions: () => true,
  });
  const { rerender } = render(
    <AdminSidebar enableCloudSS={false} enableEnterpriseSS={false} />
  );
  expect(
    screen.getByText("admin.navigation.routes.organizations.sidebar")
  ).toBeInTheDocument();

  mockUseUser.mockReturnValue({
    permissions: ["organization:read"],
    isPermissionsLoading: true,
    hasAllPermissions: () => true,
  });
  rerender(<AdminSidebar enableCloudSS={false} enableEnterpriseSS={false} />);

  expect(
    screen.getByText("admin.navigation.routes.organizations.sidebar")
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("status", { name: "Loading navigation..." })
  ).not.toBeInTheDocument();

  mockUseUser.mockReturnValue({
    permissions: [],
    isPermissionsLoading: false,
    hasAllPermissions: () => false,
  });
  rerender(<AdminSidebar enableCloudSS={false} enableEnterpriseSS={false} />);

  expect(
    screen.queryByText("admin.navigation.routes.organizations.sidebar")
  ).not.toBeInTheDocument();
});

it("shows a skeleton until the initial permissions arrive", () => {
  mockUseUser.mockReturnValue({
    permissions: [],
    isPermissionsLoading: true,
    hasAllPermissions: () => false,
  });

  render(<AdminSidebar enableCloudSS={false} enableEnterpriseSS={false} />);

  expect(
    screen.getByRole("status", { name: "Loading navigation..." })
  ).toBeInTheDocument();
});
