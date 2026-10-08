/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from "@tests/setup/test-utils";
import { ClientLayout } from "@/components/admin/ClientLayout";
import { ApplicationStatus } from "@/interfaces/settings";

const replaceMock = jest.fn();
const prefetchMock = jest.fn();
const mockUseUser = jest.fn();
let mockPathname = "/admin/roles";

jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
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

jest.mock("@/lib/api/domains/session/api", () => ({
  logout: jest.fn(),
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
    mockPathname = "/admin/roles";
    mockUseUser.mockReturnValue({
      user: { id: "admin-user" },
      permissionsError: "Failed to fetch permissions",
      isPermissionsLoading: false,
      hasAllPermissions: () => false,
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("redirects when route permissions fail to load and deny the route", async () => {
    render(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/error/403");
    });
  });

  it("does not redirect to 403 while route permissions are loading", () => {
    mockUseUser.mockReturnValue({
      user: { id: "admin-user" },
      permissionsError: null,
      isPermissionsLoading: true,
      hasAllPermissions: () => false,
    });

    render(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );

    expect(screen.queryByText("Admin content")).not.toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalledWith("/error/403");
  });

  it("keeps an authorized admin page visible during permission revalidation", () => {
    mockUseUser.mockReturnValue({
      isPermissionsLoading: false,
      hasAllPermissions: () => true,
    });
    const { rerender } = render(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );
    expect(screen.getByText("Admin content")).toBeInTheDocument();

    mockUseUser.mockReturnValue({
      isPermissionsLoading: true,
      hasAllPermissions: () => true,
    });
    rerender(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );

    expect(screen.getByText("Admin content")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalledWith("/error/403");

    mockUseUser.mockReturnValue({
      isPermissionsLoading: false,
      hasAllPermissions: () => false,
    });
    rerender(
      <ClientLayout enableEnterprise={false} enableCloud={false}>
        <div>Admin content</div>
      </ClientLayout>
    );
    expect(screen.queryByText("Admin content")).not.toBeInTheDocument();
    expect(replaceMock).toHaveBeenCalledWith("/error/403");
  });

  it("still redirects admins when route permissions load and deny the route", async () => {
    mockUseUser.mockReturnValue({
      user: { id: "admin-user" },
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

it("denies unknown admin routes even with unrelated view access", async () => {
  mockPathname = "/admin/unregistered";
  mockUseUser.mockReturnValue({
    isPermissionsLoading: false,
    hasAllPermissions: () => true,
  });
  render(
    <ClientLayout enableEnterprise={false} enableCloud={false}>
      <div>Secret content</div>
    </ClientLayout>
  );
  expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/error/403"));
});
