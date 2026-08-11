import { screen } from "@testing-library/react";
import "@/i18n/config";

import { OrganizationDesignerInspector } from "@/components/organization/OrganizationDesignerInspector";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/components/organization/OrganizationAccessPanel", () => ({
  OrganizationAccessPanel: ({
    editable,
    onSaveComplete,
    resourceType,
  }: any) => (
    <div>
      {resourceType} access panel {editable ? "editable" : "read only"}
      <button onClick={onSaveComplete}>Complete access save</button>
    </div>
  ),
}));

jest.mock("@/components/organization/OrganizationUserAssignmentsPanel", () => ({
  OrganizationUserAssignmentsPanel: ({ editable }: { editable: boolean }) => (
    <div>Users panel {editable ? "editable" : "read only"}</div>
  ),
}));

const root = {
  id: "root",
  name: "Enterprise",
  path: "/enterprise",
  parent_id: null,
  children: [
    {
      id: "platform",
      name: "Platform",
      path: "/enterprise/platform",
      parent_id: "root",
      children: [],
    },
  ],
};
const operations = {
  id: "operations",
  name: "Operations",
  path: "/operations",
  parent_id: null,
  children: [],
};

const handlers = {
  onBeginCreateChild: jest.fn(),
  onBeginDelete: jest.fn(),
  onCreateOrg: jest.fn().mockResolvedValue(undefined),
  onUpdateOrg: jest.fn().mockResolvedValue(undefined),
  onDeleteOrg: jest.fn().mockResolvedValue(undefined),
  onMoveOrg: jest.fn().mockResolvedValue(undefined),
  onAddUser: jest.fn().mockResolvedValue(undefined),
  onRoleChange: jest.fn().mockResolvedValue(undefined),
  onRemoveUser: jest.fn().mockResolvedValue(undefined),
};

describe("OrganizationDesignerInspector", () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = jest.fn();
    HTMLElement.prototype.setPointerCapture = jest.fn();
    HTMLElement.prototype.releasePointerCapture = jest.fn();
    HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("aligns the inspector with the organization tabs", () => {
    render(
      <OrganizationDesignerInspector
        organization={root.children[0]!}
        organizations={[root, operations]}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    expect(
      screen.queryByRole("tab", { name: "Details" })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Users" })).toHaveAttribute(
      "data-state",
      "active"
    );
    expect(screen.getByText("Users panel editable")).toBeInTheDocument();
  });

  it("keeps every mutation surface disabled while capability loads", async () => {
    const user = setupUser();
    render(
      <OrganizationDesignerInspector
        organization={root.children[0]!}
        organizations={[root, operations]}
        members={[]}
        editable
        capabilityLoading
        {...handlers}
      />
    );

    expect(
      screen.queryByRole("tab", { name: "Details" })
    ).not.toBeInTheDocument();
    expect(screen.getByText("Users panel read only")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Agents" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Collections" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Access" })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("tablist")).toHaveClass(
      "bg-background-neutral-02",
      "[&_[data-state=active]]:bg-background-neutral-04",
      "[&_[data-state=active]]:text-text-05"
    );

    await user.click(screen.getByRole("tab", { name: "Agents" }));
    expect(
      screen.getByText("agent access panel read only")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Collections" }));
    expect(
      screen.getByText("rag_collection access panel read only")
    ).toBeInTheDocument();
  });

  it("exposes mobile map navigation and enables mutations after capability resolves", async () => {
    const onBackToMap = jest.fn();
    const onAccessSaveComplete = jest.fn();
    const user = setupUser();
    const { rerender } = render(
      <OrganizationDesignerInspector
        organization={root.children[0]!}
        organizations={[root, operations]}
        members={[]}
        editable
        capabilityLoading
        mobileOpen
        onBackToMap={onBackToMap}
        onAccessSaveComplete={onAccessSaveComplete}
        {...handlers}
      />
    );

    await user.click(screen.getByRole("button", { name: "Back to map" }));
    expect(onBackToMap).toHaveBeenCalledTimes(1);

    rerender(
      <OrganizationDesignerInspector
        organization={root.children[0]!}
        organizations={[root, operations]}
        members={[]}
        editable
        capabilityLoading={false}
        mobileOpen
        onBackToMap={onBackToMap}
        onAccessSaveComplete={onAccessSaveComplete}
        {...handlers}
      />
    );
    await user.click(screen.getByRole("tab", { name: "Agents" }));
    await user.click(
      screen.getByRole("button", { name: "Complete access save" })
    );
    expect(onAccessSaveComplete).toHaveBeenCalledTimes(1);
  });
});
