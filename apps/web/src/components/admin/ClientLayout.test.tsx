/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from "@tests/setup/test-utils";
import { ClientLayout } from "@/components/admin/ClientLayout";
import { ApplicationStatus } from "@/interfaces/settings";

const replaceMock = jest.fn();
const prefetchMock = jest.fn();
const mockUseUser = jest.fn();

jest.mock("next/navigation", () => ({
  usePathname: () => "/admin/roles",
  useRouter: () => ({
    replace: replaceMock,
    prefetch: prefetchMock,
  }),
}));

jest.mock("@/providers/SettingsProvider", () => ({
  useSettingsContext: () => ({
    settings: {
      application_status: ApplicationStatus.ACTIVE,
    },
  }),
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => mockUseUser(),
}));

jest.mock("@/sections/sidebar/AdminSidebar", () => ({
  __esModule: true,
  default: () => <aside data-testid="admin-sidebar" />,
}));

jest.mock("../header/AnnouncementBanner", () => ({
  AnnouncementBanner: () => null,
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? "",
  }),
}));

describe("ClientLayout", () => {
  beforeEach(() => {
    mockUseUser.mockReturnValue({
      user: { id: "admin-user" },
      isAdmin: true,
      permissionsError: "Failed to fetch permissions",
      isPermissionsLoading: false,
      hasAllPermissions: () => false,
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("does not redirect admins to 403 when route permissions temporarily fail to load", () => {
    render(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );

    expect(screen.getByText("Admin content")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalledWith("/error/403");
  });

  it("does not redirect to 403 while route permissions are loading", () => {
    mockUseUser.mockReturnValue({
      user: { id: "admin-user" },
      isAdmin: true,
      permissionsError: null,
      isPermissionsLoading: true,
      hasAllPermissions: () => false,
    });

    render(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );

    expect(screen.getByText("Admin content")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalledWith("/error/403");
  });

  it("still redirects admins when route permissions load and deny the route", async () => {
    mockUseUser.mockReturnValue({
      user: { id: "admin-user" },
      isAdmin: true,
      permissionsError: null,
      isPermissionsLoading: false,
      hasAllPermissions: () => false,
    });

    render(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/error/403");
    });
  });
});
