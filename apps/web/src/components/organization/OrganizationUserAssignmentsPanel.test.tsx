import { screen, waitFor } from "@testing-library/react";
import "@/i18n/config";
import { render, setupUser } from "@tests/setup/test-utils";
import { OrganizationUserAssignmentsPanel } from "./OrganizationUserAssignmentsPanel";

const keys: string[] = [];
jest.mock("swr", () => ({
  ...jest.requireActual("swr"),
  __esModule: true,
  default: (key: string | null) => {
    if (key) keys.push(key);
    if (key === "/api/user-service/roles")
      return {
        data: {
          roles: [
            { name: "End User" },
            { name: "enduser" },
            { name: "system-admin" },
            { name: "enterprise-admin" },
            { name: "Unit Manager" },
            { name: "unit_manager" },
          ],
        },
        isLoading: false,
      };
    if (key?.includes("assignable-users"))
      return {
        data: {
          users: key.includes("query=alice")
            ? [
                {
                  id: "alice-id",
                  email: "alice@example.com",
                  first_name: "Alice",
                },
              ]
            : [],
          total: 1,
        },
        isLoading: false,
      };
    return { isLoading: false };
  },
}));

function setup(globalAccess = true) {
  const onAdd = jest.fn().mockResolvedValue(undefined);
  render(
    <OrganizationUserAssignmentsPanel
      organizationId="unit-b"
      globalAccess={globalAccess}
      assignments={[]}
      editable
      onAdd={onAdd}
      onRoleChange={jest.fn()}
      onRemove={jest.fn()}
    />
  );
  return { user: setupUser(), onAdd };
}

beforeEach(() => {
  keys.length = 0;
});

test("admins start with a role placeholder and see one unit manager without admin roles", async () => {
  const { user } = setup();
  await user.click(screen.getByRole("button", { name: "Add user" }));
  const role = screen.getByRole("combobox", { name: "New member role" });
  expect(role).toHaveTextContent("Select a role");
  await user.click(role);
  expect(screen.getAllByRole("option", { name: "Unit manager" })).toHaveLength(
    1
  );
  expect(
    screen.queryByRole("option", { name: "System Admin" })
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Enterprise Admin" })
  ).not.toBeInTheDocument();
});

test("unit managers search scoped users and submit with the sole End User role selected", async () => {
  const { user, onAdd } = setup(false);
  expect(keys).not.toContain("/api/user-service/roles");
  await user.click(screen.getByRole("button", { name: "Add user" }));
  const role = screen.getByRole("combobox", { name: "New member role" });
  expect(role).toHaveTextContent("End User");
  await user.click(role);
  expect(screen.getAllByRole("option")).toHaveLength(1);
  await user.keyboard("{Escape}");
  await user.type(screen.getByRole("combobox", { name: "User" }), "alice");
  const option = await screen.findByRole("option", {
    name: /alice@example.com/,
  });
  expect(keys).toContain(
    "/api/user-service/organizations/unit-b/assignable-users?query=alice&limit=20"
  );
  expect(keys).not.toContain("/api/user-service/users/");
  await user.click(option);
  await user.click(screen.getAllByRole("button", { name: "Add user" })[1]!);
  await waitFor(() =>
    expect(onAdd).toHaveBeenCalledWith("alice-id", "enduser")
  );
});

beforeAll(() => {
  HTMLElement.prototype.hasPointerCapture = jest.fn(() => false);
  HTMLElement.prototype.setPointerCapture = jest.fn();
  HTMLElement.prototype.releasePointerCapture = jest.fn();
  HTMLElement.prototype.scrollIntoView = jest.fn();
});

test.each(["member", "", null, undefined])(
  "unconfigured role %s shows the role placeholder without saving",
  (role) => {
    const onRoleChange = jest.fn();
    render(
      <OrganizationUserAssignmentsPanel
        organizationId="unit-b"
        globalAccess={false}
        assignments={[
          {
            id: "m1",
            user_id: "u1",
            organization_id: "unit-b",
            role_in_org: role as string,
            user: { id: "u1", email: "existing@example.com" },
          },
        ]}
        editable
        onAdd={jest.fn()}
        onRoleChange={onRoleChange}
        onRemove={jest.fn()}
      />
    );
    expect(
      screen.getByRole("combobox", { name: "Role for existing@example.com" })
    ).toHaveTextContent("Select a role");
    expect(onRoleChange).not.toHaveBeenCalled();
  }
);

test.each([
  ["End User", "End User"],
  ["unit_manager", "Unit manager"],
  ["Unit Manager", "Unit manager"],
  ["enterprise-admin", "Enterprise Admin"],
])("keeps configured existing role %s visible", (role, label) => {
  render(
    <OrganizationUserAssignmentsPanel
      organizationId="unit-b"
      globalAccess={false}
      assignments={[
        {
          id: "m1",
          user_id: "u1",
          organization_id: "unit-b",
          role_in_org: role!,
          user: { id: "u1", email: "existing@example.com" },
        },
      ]}
      editable
      onAdd={jest.fn()}
      onRoleChange={jest.fn()}
      onRemove={jest.fn()}
    />
  );
  expect(
    screen.getByRole("combobox", { name: "Role for existing@example.com" })
  ).toHaveTextContent(label!);
});
