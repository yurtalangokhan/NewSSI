import { screen } from "@testing-library/react";

import { OrganizationTree } from "@/components/organization/OrganizationTree";
import { render } from "@tests/setup/test-utils";

jest.mock("react-arborist", () => ({
  Tree: ({ onMove }: { onMove: (args: unknown) => void }) => (
    <button
      data-testid="organization-tree"
      onClick={() => onMove({ dragIds: ["child"], parentId: null })}
    >
      Simulate root drop
    </button>
  ),
}));

const handlers = {
  onCreateOrg: jest.fn().mockResolvedValue(undefined),
  onUpdateOrg: jest.fn().mockResolvedValue(undefined),
  onDeleteOrg: jest.fn().mockResolvedValue(undefined),
  onMoveOrg: jest.fn().mockResolvedValue(undefined),
  onSelectOrg: jest.fn(),
};

describe("OrganizationTree single-root action", () => {
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
});
