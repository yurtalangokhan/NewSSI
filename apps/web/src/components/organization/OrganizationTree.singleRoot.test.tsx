import { screen } from "@testing-library/react";
import "@/i18n/config";

import { OrganizationTree } from "@/components/organization/OrganizationTree";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("react-arborist", () => ({
  Tree: ({
    onMove,
    children,
    data,
    initialOpenState,
    selection,
    searchTerm,
    searchMatch,
  }: any) => {
    const flattened = (nodes: any[]): any[] =>
      nodes.flatMap((node) => [node, ...flattened(node.children ?? [])]);
    const visibleNode = searchTerm
      ? flattened(data).find((node) => searchMatch({ data: node }, searchTerm))
      : data[0];

    return (
      <div
        data-initial-open-state={JSON.stringify(initialOpenState)}
        data-search-term={searchTerm}
      >
        <button
          data-testid="organization-tree"
          onClick={() => onMove({ dragIds: ["child"], parentId: null })}
        >
          Simulate root drop
        </button>
        {visibleNode &&
          children({
            node: {
              data: visibleNode,
              isInternal: false,
              isSelected: visibleNode.id === selection,
              isOpen: false,
              toggle: jest.fn(),
            },
            style: {},
            dragHandle: null,
          })}
      </div>
    );
  },
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
        selectedOrgId="root"
        {...handlers}
      />
    );

    expect(screen.queryByText("Add Root Organization")).not.toBeInTheDocument();
  });

  it("renders organization names with the highest-contrast text token", () => {
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

    expect(screen.getByText("Enterprise")).toHaveClass("text-text-05");
  });

  it("shows search matches through the existing tree row renderer", async () => {
    const user = setupUser();
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
                id: "platform",
                name: "Platform",
                path: "/enterprise/platform",
                parent_id: "root",
                children: [],
              },
            ],
          },
        ]}
        {...handlers}
      />
    );

    await user.type(
      screen.getByRole("textbox", { name: "Search organizations" }),
      "plat"
    );

    expect(screen.getByText("Platform").parentElement).toHaveAttribute(
      "data-search-match",
      "true"
    );
    expect(screen.getByText("1 result")).toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("differentiates the selected organization with a light gray background", () => {
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
        selectedOrgId="root"
        {...handlers}
      />
    );

    expect(screen.getByText("Enterprise").parentElement).toHaveClass(
      "bg-background-neutral-02"
    );
  });

  it("gives direct subitems of the selected organization the same gray background", () => {
    render(
      <OrganizationTree
        organizations={[
          {
            id: "child",
            name: "Platform",
            path: "/enterprise/platform",
            parent_id: "root",
            children: [],
          },
        ]}
        selectedOrgId="root"
        {...handlers}
      />
    );

    expect(screen.getByText("Platform").parentElement).toHaveClass(
      "bg-background-neutral-02"
    );
    expect(screen.getByText("Platform").parentElement).not.toHaveClass(
      "border-border-primary"
    );
  });

  it("opens root organizations initially without opening level-2 nodes", () => {
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
                id: "division",
                name: "Division",
                path: "/enterprise/division",
                parent_id: "root",
                children: [
                  {
                    id: "team",
                    name: "Team",
                    path: "/enterprise/division/team",
                    parent_id: "division",
                    children: [],
                  },
                ],
              },
            ],
          },
        ]}
        {...handlers}
      />
    );

    expect(
      screen.getByTestId("organization-tree").parentElement
    ).toHaveAttribute(
      "data-initial-open-state",
      JSON.stringify({ root: true })
    );
  });

  it("uses the single empty-state action to create the root organization", async () => {
    const promptSpy = jest.spyOn(window, "prompt");
    const user = setupUser();
    render(<OrganizationTree organizations={[]} {...handlers} />);

    expect(
      screen.getAllByRole("button", { name: /Create Organization/i })
    ).toHaveLength(1);
    expect(
      screen.queryByRole("button", { name: "Add Root Organization" })
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Create Organization" })
    );

    const input = screen.getByRole("textbox", {
      name: "New root organization name",
    });
    await user.type(input, " Enterprise ");
    await user.keyboard("{Enter}");

    expect(promptSpy).not.toHaveBeenCalled();
    expect(handlers.onCreateOrg).toHaveBeenCalledWith(null, "Enterprise");
  });

  it("creates a child organization from an inline tree input", async () => {
    const promptSpy = jest.spyOn(window, "prompt");
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
        selectedOrgId="root"
        {...handlers}
      />
    );

    await user.click(
      screen.getByRole("button", { name: "Add child to Enterprise" })
    );
    const input = screen.getByRole("textbox", {
      name: "New child organization name",
    });
    await user.type(input, "Operations");
    await user.keyboard("{Enter}");

    expect(promptSpy).not.toHaveBeenCalled();
    expect(handlers.onCreateOrg).toHaveBeenCalledWith("root", "Operations");
  });

  it("cancels inline creation with Escape", async () => {
    const user = setupUser();
    render(<OrganizationTree organizations={[]} {...handlers} />);

    await user.click(
      screen.getByRole("button", { name: "Create Organization" })
    );
    await user.type(
      screen.getByRole("textbox", { name: "New root organization name" }),
      "Enterprise"
    );
    await user.keyboard("{Escape}");

    expect(handlers.onCreateOrg).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("textbox", { name: "New root organization name" })
    ).not.toBeInTheDocument();
  });

  it("does not submit a whitespace-only organization name", async () => {
    const user = setupUser();
    render(<OrganizationTree organizations={[]} {...handlers} />);

    await user.click(
      screen.getByRole("button", { name: "Create Organization" })
    );
    await user.type(
      screen.getByRole("textbox", { name: "New root organization name" }),
      "   "
    );
    await user.keyboard("{Enter}");

    expect(handlers.onCreateOrg).not.toHaveBeenCalled();
    expect(
      screen.getByRole("textbox", { name: "New root organization name" })
    ).toBeInTheDocument();
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
        selectedOrgId="root"
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

  it("hides row actions when the organization is not selected", () => {
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
      screen.queryByRole("button", { name: "Rename Enterprise" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Add child to Enterprise" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete Enterprise" })
    ).not.toBeInTheDocument();
  });
});
