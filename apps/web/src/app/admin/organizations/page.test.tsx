import { screen, waitFor } from "@testing-library/react";

import OrganizationsPage from "@/app/admin/organizations/page";
import { render, setupUser } from "@tests/setup/test-utils";

let managementEditable = false;

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
              name: "Platform",
              path: "/platform",
              parent_id: null,
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
    return { data: undefined, isLoading: false };
  }),
  mutate: jest.fn(),
}));

jest.mock("@/components/organization/OrganizationTree", () => ({
  OrganizationTree: ({ organizations, onSelectOrg }: any) => (
    <div>
      <span>{organizations.length} root</span>
      <button onClick={() => onSelectOrg(organizations[0])}>Select Platform</button>
    </div>
  ),
}));

jest.mock("@/components/organization/OrganizationAccessPanel", () => ({
  OrganizationAccessPanel: ({ organization, editable }: any) => (
    <div>
      Access workspace for {organization.name}: {editable ? "editable" : "read only"}
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
    jest.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ role_in_org: "unit_manager" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
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
      (await screen.findAllByRole("option", { name: "Unit manager" }))[0]!
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
});
