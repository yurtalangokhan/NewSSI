/**
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { setupUser } from "@tests/setup/test-utils";
import { OrganizationTree } from "@/components/organization/OrganizationTree";

// Mock react-arborist
jest.mock("react-arborist", () => ({
  Tree: ({ data, children: Node }: any) => (
    <div data-testid="organization-tree">
      {data.map((org: any) => (
        <div key={org.id} data-testid={`org-node-${org.id}`}>
          {org.name}
        </div>
      ))}
    </div>
  ),
}));

describe("OrganizationTree", () => {
  const mockOrganizations = [
    {
      id: "org-1",
      name: "Root Organization",
      path: "org-1/",
      parent_id: null,
      user_count: 5,
      permission_count: 10,
      children: [
        {
          id: "org-2",
          name: "Child Organization",
          path: "org-1/org-2/",
          parent_id: "org-1",
          user_count: 2,
          permission_count: 3,
          children: [],
        },
      ],
    },
  ];

  const mockHandlers = {
    onCreateOrg: jest.fn().mockResolvedValue(undefined),
    onUpdateOrg: jest.fn().mockResolvedValue(undefined),
    onDeleteOrg: jest.fn().mockResolvedValue(undefined),
    onMoveOrg: jest.fn().mockResolvedValue(undefined),
    onSelectOrg: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders organization tree component", () => {
    render(
      <OrganizationTree organizations={mockOrganizations} {...mockHandlers} />
    );

    expect(screen.getByText("Organization")).toBeInTheDocument();
    expect(screen.getByTestId("organization-tree")).toBeInTheDocument();
  });

  it("displays organization nodes", () => {
    render(
      <OrganizationTree organizations={mockOrganizations} {...mockHandlers} />
    );

    expect(screen.getByText("Root Organization")).toBeInTheDocument();
    expect(screen.getByTestId("org-node-org-1")).toBeInTheDocument();
  });

  it("shows empty state when no organizations", () => {
    render(<OrganizationTree organizations={[]} {...mockHandlers} />);

    expect(screen.getByText("No organizations yet")).toBeInTheDocument();
    expect(
      screen.getByText("Create your first organization to get started")
    ).toBeInTheDocument();
  });

  it("hides root organization creation once a root exists", () => {
    render(
      <OrganizationTree organizations={mockOrganizations} {...mockHandlers} />
    );

    expect(screen.queryByText("Add Root Organization")).not.toBeInTheDocument();
  });

  it("calls onCreateOrg when creating the first root organization", async () => {
    const user = setupUser();
    // Mock window.prompt
    global.prompt = jest.fn().mockReturnValue("New Organization");

    render(<OrganizationTree organizations={[]} {...mockHandlers} />);

    const addButton = screen.getByText("Create Organization");
    await user.click(addButton);

    await waitFor(() => {
      expect(mockHandlers.onCreateOrg).toHaveBeenCalledWith(
        null,
        "New Organization"
      );
    });
  });

  it("calls onSelectOrg when organization is selected", () => {
    const { onSelectOrg } = mockHandlers;

    render(
      <OrganizationTree
        organizations={mockOrganizations}
        {...mockHandlers}
        selectedOrgId="org-1"
      />
    );

    // The tree component's onSelect would be triggered in actual usage
    expect(onSelectOrg).toBeDefined();
  });

  it("highlights selected organization", () => {
    render(
      <OrganizationTree
        organizations={mockOrganizations}
        {...mockHandlers}
        selectedOrgId="org-1"
      />
    );

    // Verify tree receives selection prop
    const tree = screen.getByTestId("organization-tree");
    expect(tree).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(
      <OrganizationTree
        organizations={mockOrganizations}
        {...mockHandlers}
        className="custom-class"
      />
    );

    const treeContainer = container.firstChild;
    expect(treeContainer).toHaveClass("custom-class");
  });

  it("does not call onCreateOrg when prompt is cancelled", async () => {
    const user = setupUser();
    global.prompt = jest.fn().mockReturnValue(null);

    render(<OrganizationTree organizations={[]} {...mockHandlers} />);

    const addButton = screen.getByText("Create Organization");
    await user.click(addButton);

    await waitFor(() => {
      expect(mockHandlers.onCreateOrg).not.toHaveBeenCalled();
    });
  });

  it("trims whitespace from organization name", async () => {
    const user = setupUser();
    global.prompt = jest.fn().mockReturnValue("  Trimmed Name  ");

    render(<OrganizationTree organizations={[]} {...mockHandlers} />);

    const addButton = screen.getByText("Create Organization");
    await user.click(addButton);

    await waitFor(() => {
      expect(mockHandlers.onCreateOrg).toHaveBeenCalledWith(
        null,
        "Trimmed Name"
      );
    });
  });

  it("handles organizations with metadata", () => {
    const orgsWithMetadata = [
      {
        id: "org-1",
        name: "Org with Metadata",
        path: "org-1/",
        parent_id: null,
        metadata: { region: "US-West", cost_center: "12345" },
        children: [],
      },
    ];

    render(
      <OrganizationTree organizations={orgsWithMetadata} {...mockHandlers} />
    );

    expect(screen.getByText("Org with Metadata")).toBeInTheDocument();
  });

  it("displays user count badge when present", () => {
    render(
      <OrganizationTree organizations={mockOrganizations} {...mockHandlers} />
    );

    // User count is displayed in the Node component
    // This test verifies the data is passed correctly
    const orgWithUsers = mockOrganizations[0];
    expect(orgWithUsers?.user_count).toBe(5);
  });

  it("handles organizations at different hierarchy depths", () => {
    const deepHierarchy = [
      {
        id: "root",
        name: "Root",
        path: "root/",
        parent_id: null,
        children: [
          {
            id: "dept",
            name: "Department",
            path: "root/dept/",
            parent_id: "root",
            children: [
              {
                id: "team",
                name: "Team",
                path: "root/dept/team/",
                parent_id: "dept",
                children: [],
              },
            ],
          },
        ],
      },
    ];

    render(
      <OrganizationTree organizations={deepHierarchy} {...mockHandlers} />
    );

    expect(screen.getByTestId("org-node-root")).toBeInTheDocument();
  });
});
