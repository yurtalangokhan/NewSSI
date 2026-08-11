import { screen } from "@testing-library/react";

import { OrganizationTree } from "@/components/organization/OrganizationTree";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("react-arborist", () => ({
  Tree: ({ onMove, children, data }: any) => (
    <div>
      <button
        data-testid="organization-tree"
        onClick={() => onMove({ dragIds: ["child"], parentId: null })}
      >
        Simulate root drop
      </button>
      {data[0] &&
        children({
          node: {
            data: data[0],
            isInternal: false,
            isSelected: false,
            isOpen: false,
            toggle: jest.fn(),
          },
          style: {},
          dragHandle: null,
        })}
    </div>
  ),
}));

const handlers = {
  onCreateOrg: jest.fn().mockResolvedValue(undefined),
  onUpdateOrg: jest.fn().mockResolvedValue(undefined),
  onDeleteOrg: jest.fn().mockResolvedValue(undefined),
  onMoveOrg: jest.fn().mockResolvedValue(undefined),
  onSelectOrg: jest.fn(),
  onOpenDesigner: jest.fn(),
};

describe("OrganizationTree single-root action", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("opens the visual designer from an accessible title-row control", async () => {
    const user = setupUser();
    render(<OrganizationTree organizations={[]} {...handlers} />);

    await user.click(
      screen.getByRole("button", { name: "Open organization designer" })
    );

    expect(handlers.onOpenDesigner).toHaveBeenCalledTimes(1);
  });

  it("hides root creation once the organization tree has a root", () => {
    render(
      <OrganizationTree
        organizations={[
          {
            id: "root",
            name: "Enterprise",
            path: "/enterprise",
            parent_id: null,
            children: [],
          },
        ]}
        {...handlers}
      />
    );

    expect(screen.queryByText("Add Root Organization")).not.toBeInTheDocument();
  });

  it("keeps first-root creation available for an empty tree", () => {
    render(<OrganizationTree organizations={[]} {...handlers} />);
    expect(screen.getByText("Create Organization")).toBeInTheDocument();
  });

  it("prevents moving a child to the root level", () => {
    render(
      <OrganizationTree
        organizations={[
          {
            id: "root",
            name: "Enterprise",
            path: "/enterprise",
            parent_id: null,
            children: [
              {
                id: "child",
                name: "Unit",
                path: "/enterprise/unit",
                parent_id: "root",
                children: [],
              },
            ],
          },
        ]}
        {...handlers}
      />
    );

    screen.getByTestId("organization-tree").click();
    expect(handlers.onMoveOrg).not.toHaveBeenCalled();
  });

  it("exposes rename, add-child, and delete as direct row actions", async () => {
    const user = setupUser();
    render(
      <OrganizationTree
        organizations={[
          {
            id: "root",
            name: "Enterprise",
            path: "/enterprise",
            parent_id: null,
            children: [],
          },
        ]}
        {...handlers}
      />
    );

    expect(
      screen.queryByRole("button", { name: "Actions for Enterprise" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Rename Enterprise" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add child to Enterprise" })
    ).toBeInTheDocument();

    jest.spyOn(window, "confirm").mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Delete Enterprise" }));
    expect(handlers.onDeleteOrg).toHaveBeenCalledWith("root");
  });
});
