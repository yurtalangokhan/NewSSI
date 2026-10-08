import { screen, within } from "@testing-library/react";
import UsersPage from "@/app/admin/users/page";
import { render } from "@tests/setup/test-utils";

const mockPending = new Set<string>();
const mockData: Record<string, unknown> = {
  "/api/user-service/roles/": {
    roles: [{ name: "enduser" }, { name: "system-admin" }],
  },
  "/api/user-service/users?is_active=true&limit=1": { total_items: 120 },
  "/api/user-service/users?is_active=false&limit=1": { total_items: 3 },
  "/api/user-service/users/role-distribution": {
    status: "ready",
    distribution: [{ role: "enduser", count: 120 }],
    computed_at: "2026-09-24T08:00:00+00:00",
  },
};
const readyDistribution = mockData["/api/user-service/users/role-distribution"];

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock("@/i18n/config", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
}));
jest.mock("@/lib/auth/roles", () => ({
  formatRoleName: (name: string) => name,
}));
jest.mock("@/lib/constants", () => ({
  ...jest.requireActual("@/lib/constants"),
  NEXT_PUBLIC_CLOUD_ENABLED: false,
}));
jest.mock("@/components/admin/users/SignedUpUserTable", () => ({
  __esModule: true,
  default: () => <div>User table</div>,
}));
jest.mock("@/components/admin/users/PendingUsersTable", () => ({
  __esModule: true,
  default: () => null,
}));
function mockSWRResult(key: string | null) {
  return {
    data: key && !mockPending.has(key) ? mockData[key] : undefined,
    isLoading: key ? mockPending.has(key) : false,
  };
}
jest.mock("swr", () => ({
  ...jest.requireActual("swr"),
  __esModule: true,
  default: (key: string | null) => mockSWRResult(key),
}));
jest.mock("@/lib/api/domains/access/hooks", () => ({
  useDirectoryRoles: () => mockSWRResult("/api/user-service/roles/"),
  useDirectoryUserStatusCount: (active: boolean) =>
    mockSWRResult(`/api/user-service/users?is_active=${active}&limit=1`),
  usePendingDirectoryUsers: () => mockSWRResult(null),
}));

beforeEach(() => {
  mockPending.clear();
  mockData["/api/user-service/users/role-distribution"] = readyDistribution;
});

test.each([
  "/api/user-service/users/role-distribution",
  "/api/user-service/users?is_active=true&limit=1",
  "/api/user-service/users?is_active=false&limit=1",
])("keeps the summary and role count visible while %s is pending", (key) => {
  mockPending.add(key);
  const { rerender } = render(<UsersPage />);
  expect(screen.getByText("admin.users.workspaceTitle")).toBeInTheDocument();
  expect(screen.getByText("User table")).toBeInTheDocument();
  const rolesTile = screen.getByText("admin.users.rolesAvailableLabel")
    .parentElement!;
  expect(within(rolesTile).getByText("2")).toBeInTheDocument();
  mockPending.clear();
  rerender(<UsersPage />);
  expect(
    screen.getByText("admin.users.roles.enduser · 120")
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "120 admin.users.activeStatus · 3 admin.users.inactiveStatus"
    )
  ).toBeInTheDocument();
});

test.each([
  ["pending", "admin.users.roleDistributionCalculating"],
  ["unavailable", "admin.users.roleDistributionUnavailable"],
])(
  "shows a terminal message instead of loading forever when the distribution is %s",
  (status, message) => {
    mockData["/api/user-service/users/role-distribution"] = {
      status,
      distribution: [],
      computed_at: null,
    };
    render(<UsersPage />);
    expect(screen.getAllByText(message).length).toBeGreaterThan(0);
  }
);
