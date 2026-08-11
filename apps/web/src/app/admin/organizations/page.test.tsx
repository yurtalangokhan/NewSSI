import { screen, waitFor } from "@testing-library/react";
import { mutate } from "swr";

import OrganizationsPage from "@/app/admin/organizations/page";
import { render, setupUser } from "@tests/setup/test-utils";

let managementEditable = false;
let organizationName = "Platform";
let organizationPath = "/platform";
let organizationChildren: any[] = [];
let globalCanCreateRoot = false;
let globalCanEditLayout = false;

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    hasPermission: (permission: string) =>
      (permission === "org:create" && globalCanCreateRoot) ||
      (permission === "org:update" && globalCanEditLayout),
  }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "admin.users.roles.enduser": "End User",
        "admin.users.roles.enterprise-admin": "Enterprise Admin",
        "admin.users.roles.system-admin": "System Admin",
      })[key] ?? key,
  }),
}));

jest.mock("swr", () => ({
  ...jest.requireActual("swr"),
  __esModule: true,
  default: jest.fn((key: string | null) => {
    if (key === "/api/user-service/organizations/tree") {
      return {
        data: {
          roots: [
            {
              id: "org-1",
              name: organizationName,
              path: organizationPath,
              parent_id: null,
              children: organizationChildren,
            },
          ],
        },
        isLoading: false,
      };
    }
    if (key?.endsWith("/users")) {
      return {
        data: {
          users: [
            {
              id: "membership-1",
              user_id: "user-1",
              organization_id: "org-1",
              role_in_org: "member",
              is_active: true,
              user: { id: "user-1", email: "member@example.com" },
            },
          ],
          count: 1,
        },
      };
    }
    if (key?.endsWith("/management-capability")) {
      return { data: { editable: managementEditable }, isLoading: false };
    }
    if (key === "/api/user-service/roles") {
      return {
        data: {
          roles: [
            { name: "enduser" },
            { name: "enterprise-admin" },
            { name: "system-admin" },
          ],
        },
        isLoading: false,
      };
    }
    return { data: undefined, isLoading: false };
  }),
  mutate: jest.fn(),
}));

jest.mock("@/components/organization/OrganizationTree", () => ({
  OrganizationTree: ({ organizations, onSelectOrg, onOpenDesigner }: any) => (
    <div>
      <span>{organizations.length} root</span>
      <button onClick={() => onSelectOrg(organizations[0])}>
        Select Platform
      </button>
      <button onClick={onOpenDesigner}>Open organization designer</button>
    </div>
  ),
}));

jest.mock("@/components/organization/OrganizationDesigner", () => ({
  OrganizationDesigner: ({
    selectedOrg,
    onClose,
    onCreateOrg,
    onUpdateOrg,
    onDeleteOrg,
    onMoveOrg,
    onAddUser,
    onRoleChange,
    onRemoveUser,
    onAccessSaveComplete,
    canCreateRoot,
    canEditLayout,
  }: any) => (
    <div role="dialog" aria-label="Organization designer">
      Designer selection: {selectedOrg?.name ?? "none"} {selectedOrg?.path}
      Children: {selectedOrg?.children?.map((child: any) => child.name).join(", ")}
      <span>{canCreateRoot ? "Root creation permitted" : "Root creation denied"}</span>
      <span>{canEditLayout ? "Layout editing permitted" : "Layout editing denied"}</span>
      <button onClick={onClose}>Close designer</button>
      <button
        onClick={() => onUpdateOrg(selectedOrg.id, { name: "Platform Core" })}
      >
        Rename in designer
      </button>
      <button onClick={() => onCreateOrg(selectedOrg?.id ?? null, "Security")}>Create in designer</button>
      <button onClick={() => onMoveOrg(selectedOrg.id, "org-2")}>Move in designer</button>
      <button onClick={() => onDeleteOrg(selectedOrg.id)}>Delete in designer</button>
      <button onClick={() => onAddUser("user-2", "member")}>Add member in designer</button>
      <button onClick={() => onRoleChange("user-1", "unit_manager")}>Change member role in designer</button>
      <button onClick={() => onRemoveUser("user-1")}>Remove member in designer</button>
      <button onClick={onAccessSaveComplete}>Complete access save in designer</button>
    </div>
  ),
}));

jest.mock("@/components/organization/OrganizationAccessPanel", () => ({
  OrganizationAccessPanel: ({ organization, editable }: any) => (
    <div>
      Access workspace for {organization.name}:{" "}
      {editable ? "editable" : "read only"}
    </div>
  ),
}));

describe("OrganizationsPage", () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = jest.fn();
    HTMLElement.prototype.setPointerCapture = jest.fn();
    HTMLElement.prototype.releasePointerCapture = jest.fn();
    HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  beforeEach(() => {
    managementEditable = false;
    organizationName = "Platform";
    organizationPath = "/platform";
    organizationChildren = [];
    globalCanCreateRoot = false;
    globalCanEditLayout = false;
    // Serves organization CRUD and membership mutation endpoints used by this page.
    jest.spyOn(global, "fetch").mockImplementation(async (request, options) => {
      if (
        request === "/api/user-service/organizations/org-1" &&
        options?.method === "PATCH"
      ) {
        organizationName = "Platform Core";
      }
      return new Response(JSON.stringify({ role_in_org: "unit_manager" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("integrates Users and Access tabs without placeholder tabs", async () => {
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));

    expect(screen.getByRole("tab", { name: "Users" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Access" })).toBeInTheDocument();
    expect(screen.queryByText("Permissions")).not.toBeInTheDocument();
    expect(screen.queryByText("Statistics")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Access" }));
    expect(
      screen.getByText("Access workspace for Platform: read only")
    ).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/management-capability")
    );
  });

  it("opens without changing routes, reuses page handlers, and preserves selection on close", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(
      screen.getByRole("button", { name: "Open organization designer" })
    );

    expect(
      screen.getByRole("dialog", { name: "Organization designer" })
    ).toHaveTextContent("Designer selection: Platform");
    await user.click(screen.getByRole("button", { name: "Rename in designer" }));
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/user-service/organizations/org-1",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ name: "Platform Core" }),
        })
      )
    );

    await user.click(screen.getByRole("button", { name: "Close designer" }));
    expect(
      screen.queryByRole("dialog", { name: "Organization designer" })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Platform Core")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("resizes the organization pane with the accessible splitter", async () => {
    const user = setupUser();
    render(<OrganizationsPage />);

    const splitter = screen.getByRole("separator", {
      name: "Resize organization tree",
    });
    expect(splitter).toHaveAttribute("aria-valuenow", "480");

    splitter.focus();
    await user.keyboard("{ArrowRight}");
    expect(splitter).toHaveAttribute("aria-valuenow", "496");
    expect(screen.getByTestId("organization-tree-pane")).toHaveStyle({
      width: "496px",
    });
  });

  it("loads management capability and disables membership controls for a viewer", async () => {
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));

    expect(
      screen.getByRole("combobox", { name: "Role for member@example.com" })
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add user" })).toBeDisabled();
  });

  it("updates a member role through the organization membership PATCH route", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));

    await user.click(
      screen.getByRole("combobox", { name: "Role for member@example.com" })
    );
    await user.click(
      (await screen.findAllByRole("option", { name: "Birim Yöneticisi" }))[0]!
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/user-service/organizations/org-1/users/user-1",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ role_in_org: "unit_manager" }),
        })
      );
    });
  });

  it("uses the Users page role catalog plus Birim Yöneticisi", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Add user" }));
    await user.click(screen.getByRole("combobox", { name: "New member role" }));

    expect(
      screen.getByRole("option", { name: "End User" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Enterprise Admin" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "System Admin" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Birim Yöneticisi" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Viewer" })
    ).not.toBeInTheDocument();
  });

  it("reconciles the selected organization from refreshed hierarchy data", async () => {
    const user = setupUser();
    const view = render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));

    organizationPath = "/enterprise/platform";
    organizationChildren = [
      {
        id: "child-1",
        name: "Runtime",
        path: "/enterprise/platform/runtime",
        parent_id: "org-1",
        children: [],
      },
    ];
    view.rerender(<OrganizationsPage />);

    const designer = screen.getByRole("dialog", { name: "Organization designer" });
    expect(designer).toHaveTextContent("/enterprise/platform");
    expect(designer).toHaveTextContent("Children: Runtime");
  });

  it("revalidates exactly tree and layout after create", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));
    jest.mocked(mutate).mockClear();

    await user.click(screen.getByRole("button", { name: "Create in designer" }));
    await waitFor(() => expect(jest.mocked(mutate)).toHaveBeenCalledTimes(2));
    expect(jest.mocked(mutate).mock.calls).toEqual([
      ["/api/user-service/organizations/tree"],
      ["/api/user-service/organizations/layout"],
    ]);
  });

  it("revalidates exactly tree and layout after move", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));
    jest.mocked(mutate).mockClear();

    await user.click(screen.getByRole("button", { name: "Move in designer" }));
    await waitFor(() => expect(jest.mocked(mutate)).toHaveBeenCalledTimes(2));
    expect(jest.mocked(mutate).mock.calls).toEqual([
      ["/api/user-service/organizations/tree"],
      ["/api/user-service/organizations/layout"],
    ]);
  });

  it("revalidates exactly tree and layout after delete", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));
    jest.mocked(mutate).mockClear();

    await user.click(screen.getByRole("button", { name: "Delete in designer" }));
    await waitFor(() => expect(jest.mocked(mutate)).toHaveBeenCalledTimes(2));
    expect(jest.mocked(mutate).mock.calls).toEqual([
      ["/api/user-service/organizations/tree"],
      ["/api/user-service/organizations/layout"],
    ]);
  });

  it("revalidates exactly the tree after an Access save", async () => {
    managementEditable = true;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));
    jest.mocked(mutate).mockClear();

    await user.click(screen.getByRole("button", { name: "Complete access save in designer" }));
    await waitFor(() => expect(jest.mocked(mutate)).toHaveBeenCalledTimes(1));
    expect(jest.mocked(mutate).mock.calls).toEqual([
      ["/api/user-service/organizations/tree"],
    ]);
  });

  it.each([
    [true, "Root creation permitted"],
    [false, "Root creation denied"],
  ])("passes global org:create permission %s to the designer", async (allowed, label) => {
    globalCanCreateRoot = allowed;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it.each([
    [true, "Layout editing permitted"],
    [false, "Layout editing denied"],
  ])("passes coarse org:update permission %s to the designer", async (allowed, label) => {
    globalCanEditLayout = allowed;
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("keeps designer member add, role, and remove operations on existing handlers", async () => {
    managementEditable = true;
    jest.spyOn(window, "confirm").mockReturnValue(true);
    const user = setupUser();
    render(<OrganizationsPage />);
    await user.click(screen.getByRole("button", { name: "Select Platform" }));
    await user.click(screen.getByRole("button", { name: "Open organization designer" }));

    await user.click(screen.getByRole("button", { name: "Add member in designer" }));
    await user.click(screen.getByRole("button", { name: "Change member role in designer" }));
    await user.click(screen.getByRole("button", { name: "Remove member in designer" }));

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/organizations/org-1/users",
      expect.objectContaining({ method: "POST" })
    );
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/organizations/org-1/users/user-1",
      expect.objectContaining({ method: "PATCH" })
    );
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/organizations/org-1/users/user-1",
      expect.objectContaining({ method: "DELETE" })
    );
  });
});
