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
    rowHeight,
  }: any) => {
    const flattened = (nodes: any[]): any[] =>
      nodes.flatMap((node) => [node, ...flattened(node.children ?? [])]);
    const visibleNodes = flattened(data);

    return (
      <div
        data-initial-open-state={JSON.stringify(initialOpenState)}
        data-search-term={searchTerm}
        data-row-heights={JSON.stringify(
          visibleNodes.map((visibleNode) =>
            typeof rowHeight === "function"
              ? rowHeight({ data: visibleNode })
              : rowHeight
          )
        )}
      >
        <button
          data-testid="organization-tree"
          onClick={() => onMove({ dragIds: ["child"], parentId: null })}
        >
          Simulate root drop
        </button>
        {visibleNodes.map((visibleNode: any) => (
          <div key={visibleNode.id}>
            {children({
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
        ))}
      </div>
    );
  },
}));

const handlers = {
  onCreateOrg: jest.fn().mockResolvedValue(undefined),
  onUpdateOrg: jest.fn().mockResolvedValue(undefined),
  onDeleteOrg: jest.fn().mockResolvedValue(undefined),
  onMoveOrg: jest.fn().mockResolvedValue(true),
  onSelectOrg: jest.fn(),
  onOpenDesigner: jest.fn(),
};

describe("OrganizationTree single-root action", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
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

  it("does not render expand toggle icon for leaf organizations with no children", () => {
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

    expect(screen.queryByText("+")).not.toBeInTheDocument();
    expect(screen.queryByText("−")).not.toBeInTheDocument();
  });

  it("renders expand toggle icon for organizations with children", () => {
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
                name: "Child",
                path: "/enterprise/child",
                parent_id: "root",
                children: [],
              },
            ],
          },
        ]}
        {...handlers}
      />
    );

    expect(screen.getByText("+")).toBeInTheDocument();
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

  it("shows inert direct-member rows in a distinct style", async () => {
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
        showMembers
        membersByOrganizationId={{
          root: [
            {
              id: "membership-1",
              user_id: "user-1",
              organization_id: "root",
              role_in_org: "member",
              user: {
                id: "user-1",
                first_name: "Ada",
                last_name: "Lovelace",
                email: "ada@example.com",
              },
            },
          ],
        }}
        onShowMembersChange={jest.fn()}
        {...handlers}
      />
    );

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByTestId("organization-member-user-1")).toHaveClass(
      "bg-background-neutral-02"
    );
    expect(
      screen.queryByRole("button", { name: "Rename Ada Lovelace" })
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide users" }));
  });

  it("reserves extra row height only for units with visible members", () => {
    render(
      <OrganizationTree
        organizations={[
          {
            id: "with-members",
            name: "With members",
            path: "/with-members",
            parent_id: null,
            children: [
              {
                id: "without-members",
                name: "Without members",
                path: "/with-members/without-members",
                parent_id: "with-members",
                children: [],
              },
            ],
          },
        ]}
        showMembers
        membersByOrganizationId={{
          "with-members": [
            {
              id: "membership-1",
              user_id: "user-1",
              organization_id: "with-members",
              role_in_org: "member",
              user: { id: "user-1", email: "member@example.com" },
            },
          ],
        }}
        {...handlers}
      />
    );

    expect(
      screen.getByTestId("organization-tree").parentElement
    ).toHaveAttribute("data-row-heights", "[136,40]");
  });

  it("debounces remote search and reveals a keyboard-selected suggestion", async () => {
    jest.useFakeTimers();
    const user = setupUser();
    const onSearch = jest.fn();
    const onRevealResult = jest.fn();
    const runtime = {
      id: "runtime",
      name: "Runtime",
      path: "/enterprise/platform/runtime",
      parent_id: "platform",
      children: [],
    };
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
        searchResults={[runtime]}
        searchLoading={false}
        searchError={null}
        resultsLimited={false}
        onSearch={onSearch}
        onRevealResult={onRevealResult}
        {...handlers}
      />
    );

    const search = screen.getByRole("combobox", {
      name: "Search organizations",
    });
    await user.type(search, "ru");
    expect(onSearch).not.toHaveBeenCalled();
    await jest.advanceTimersByTimeAsync(249);
    expect(onSearch).not.toHaveBeenCalled();
    await jest.advanceTimersByTimeAsync(1);
    expect(onSearch).toHaveBeenCalledWith("ru");

    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Runtime/ })).toHaveTextContent(
      "/enterprise/platform/runtime"
    );
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onRevealResult).toHaveBeenCalledWith(runtime);
    jest.useRealTimers();
  });

  it("labels a capped remote result set", async () => {
    const user = setupUser();
    render(
      <OrganizationTree
        organizations={[]}
        searchResults={Array.from({ length: 100 }, (_, index) => ({
          id: `org-${index}`,
          name: `Organization ${index}`,
          path: `/organization-${index}`,
          parent_id: null,
          children: [],
        }))}
        searchLoading={false}
        searchError={null}
        resultsLimited
        onSearch={jest.fn()}
        onRevealResult={jest.fn()}
        {...handlers}
      />
    );

    await user.type(
      screen.getByRole("combobox", { name: "Search organizations" }),
      "or"
    );
    expect(
      screen.getByText("Showing the first 100 results")
    ).toBeInTheDocument();
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

  it("renames an organization inline when submitting the edit input", async () => {
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

    await user.click(screen.getByRole("button", { name: "Rename Enterprise" }));
    const input = screen.getByDisplayValue("Enterprise");
    expect(input).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "Acme Corp");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(handlers.onUpdateOrg).toHaveBeenCalledWith("root", { name: "Acme Corp" });
  });

  it("cancels inline rename with Escape or Cancel button", async () => {
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

    await user.click(screen.getByRole("button", { name: "Rename Enterprise" }));
    expect(screen.getByDisplayValue("Enterprise")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(handlers.onUpdateOrg).not.toHaveBeenCalled();
    expect(screen.queryByDisplayValue("Enterprise")).not.toBeInTheDocument();
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
  });

  it("renders organization name with title attribute for long name tooltip", () => {
    const longName = "Bilisim Sistemleri ve Bilgi Guvenligi Direktorlugu";
    render(
      <OrganizationTree
        organizations={[
          {
            id: "long-org",
            name: longName,
            path: "/long-org",
            parent_id: null,
            children: [],
          },
        ]}
        {...handlers}
      />
    );

    const nameElement = screen.getByText(longName);
    expect(nameElement).toHaveAttribute("title", longName);
    expect(nameElement).toHaveClass("truncate");
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
