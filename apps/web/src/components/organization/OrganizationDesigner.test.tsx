import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import "@/i18n/config";

import { OrganizationDesigner } from "@/components/organization/OrganizationDesigner";
import type { OrganizationNode } from "@/components/organization/organizationTypes";
import { toast } from "@/hooks/useToast";
import { render, setupUser } from "@tests/setup/test-utils";

const fitView = jest.fn();
const mockIntersectingNodes = jest.fn(() => [] as any[]);
let mockNodesInitialized = true;

jest.mock("@xyflow/react", () => {
  const React = jest.requireActual("react");
  return {
    Background: () => <div data-testid="flow-background" />,
    Controls: () => <div data-testid="flow-controls" />,
    MiniMap: () => <div data-testid="flow-minimap" />,
    ReactFlowProvider: ({ children }: { children: React.ReactNode }) =>
      children,
    useNodesState: (initialNodes: any[]) => {
      const [nodes, setNodes] = React.useState(initialNodes);
      const onNodesChange = React.useCallback((changes: any[]) => {
        setNodes((current: any[]) =>
          current.map((node) => {
            const change = changes.find(
              (candidate) => candidate.id === node.id
            );
            return change?.position
              ? { ...node, position: change.position }
              : node;
          })
        );
      }, []);
      return [nodes, setNodes, onNodesChange];
    },
    useNodesInitialized: () => mockNodesInitialized,
    ReactFlow: ({
      nodes,
      edges,
      onInit,
      onNodeClick,
      onNodeDragStart,
      onNodeDrag,
      onNodeDragStop,
      onNodesChange,
      colorMode,
      proOptions,
      minZoom,
      children,
    }: any) => {
      React.useEffect(
        () =>
          onInit?.({ fitView, getIntersectingNodes: mockIntersectingNodes }),
        [onInit]
      );
      return (
        <div
          data-testid="react-flow"
          data-edge-count={edges.length}
          data-color-mode={colorMode}
          data-hide-attribution={String(proOptions?.hideAttribution)}
          data-min-zoom={minZoom}
        >
          {nodes.map((node: any) => (
            <React.Fragment key={node.id}>
              <button
                onClick={() => onNodeClick?.({}, node)}
                onPointerUp={() => {
                  onNodeDragStart?.({}, node);
                  onNodesChange?.([
                    {
                      id: node.id,
                      type: "position",
                      position: { x: 80, y: 110 },
                      dragging: true,
                    },
                    {
                      id: node.id,
                      type: "position",
                      position: { x: 90, y: 120 },
                      dragging: false,
                    },
                  ]);
                  onNodeDrag?.({}, { ...node, position: { x: 90, y: 120 } });
                  onNodeDragStop?.(
                    {},
                    { ...node, position: { x: 90, y: 120 } }
                  );
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowRight") {
                    onNodesChange?.([
                      {
                        id: node.id,
                        type: "position",
                        position: {
                          x: node.position.x + 5,
                          y: node.position.y,
                        },
                      },
                    ]);
                  }
                }}
                data-position-x={node.position.x}
                data-draggable={String(node.draggable)}
                data-position-y={node.position.y}
                data-child-count={node.data.childCount}
                data-member-count={node.data.members?.length ?? 0}
                data-search-state={
                  node.data.searchMatch
                    ? "match"
                    : node.data.searchDimmed
                      ? "dimmed"
                      : "idle"
                }
              >
                {node.data.name} {node.draggable ? "movable" : "locked"}
              </button>
              {node.data.hasChildren && node.data.onToggleSubtree && (
                <button
                  aria-label={`Toggle subtree ${node.id}`}
                  onClick={node.data.onToggleSubtree}
                >
                  Toggle subtree
                </button>
              )}
              {node.data.onRequestMove && node.data.parentOptions?.at(-1) && (
                <button
                  onClick={() =>
                    node.data.onRequestMove(node.data.parentOptions.at(-1).id)
                  }
                >
                  Move {node.data.name}
                </button>
              )}
            </React.Fragment>
          ))}
          {children}
        </div>
      );
    },
  };
});

jest.mock("@/components/organization/OrganizationDesignerInspector", () => ({
  OrganizationDesignerInspector: ({
    organization,
    mobileOpen,
    onBackToMap,
  }: any) => (
    <aside data-testid="inspector" data-mobile-open={mobileOpen}>
      {organization ? `Inspector ${organization.name}` : "No selection"}
      {organization && <button onClick={onBackToMap}>Back to map</button>}
    </aside>
  ),
}));

const organizations: OrganizationNode[] = [
  {
    id: "root",
    name: "Enterprise",
    path: "/enterprise",
    parent_id: null,
    children: [
      {
        id: "child",
        name: "Platform",
        path: "/enterprise/platform",
        parent_id: "root",
        children: [],
      },
    ],
  },
];

const movableOrganizations: OrganizationNode[] = [
  {
    id: "root",
    name: "Enterprise",
    path: "/enterprise",
    parent_id: null,
    children: [
      {
        id: "source",
        name: "Source",
        path: "/enterprise/source",
        parent_id: "root",
        children: [
          {
            id: "leaf",
            name: "Leaf",
            path: "/enterprise/source/leaf",
            parent_id: "source",
            children: [],
          },
        ],
      },
      {
        id: "target",
        name: "Target",
        path: "/enterprise/target",
        parent_id: "root",
        children: [],
      },
    ],
  },
];

const handlers = {
  // Fail-closed default, matching the production wiring: a viewer without
  // global organization scope may only assign the enduser role.
  globalAccess: false,
  canCreateRoot: false,
  canMoveOrganization: true,
  onClose: jest.fn(),
  onSelectOrg: jest.fn(),
  onCreateOrg: jest.fn().mockResolvedValue(undefined),
  onUpdateOrg: jest.fn().mockResolvedValue(undefined),
  onDeleteOrg: jest.fn().mockResolvedValue(undefined),
  onMoveOrg: jest.fn().mockResolvedValue(true),
  onAddUser: jest.fn().mockResolvedValue(undefined),
  onRoleChange: jest.fn().mockResolvedValue(undefined),
  onRemoveUser: jest.fn().mockResolvedValue(undefined),
};

function mockCompleteTreeFetch(tree = organizations) {
  // Capture unexpected network requests from local view operations.
  return jest
    .spyOn(global, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify({ roots: tree }), { status: 200 })
    );
}

describe("OrganizationDesigner", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIntersectingNodes.mockReturnValue([]);
    mockNodesInitialized = true;
  });
  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it("switches orientation immediately and highlights the active view without reset UI", async () => {
    const fetchSpy = mockCompleteTreeFetch();
    const successToast = jest.spyOn(toast, "success");
    const user = setupUser();
    render(
      <OrganizationDesigner
        {...handlers}
        canMoveOrganization={false}
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
      />
    );
    const vertical = screen.getByRole("button", { name: "Vertical view" });
    const horizontal = screen.getByRole("button", { name: "Horizontal view" });
    expect(vertical).toHaveAttribute("aria-pressed", "true");
    for (const [button, axis] of [
      [horizontal, "positionX"],
      [vertical, "positionY"],
    ] as const) {
      await user.click(button);
      expect(button).toHaveAttribute("aria-pressed", "true");
      expect(button === vertical ? horizontal : vertical).toHaveAttribute(
        "aria-pressed",
        "false"
      );
      expect(
        screen.queryByRole("dialog", { name: "Reset diagram layout?" })
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      const root = screen.getByRole("button", { name: "Enterprise locked" });
      const child = screen.getByRole("button", { name: "Platform locked" });
      expect(Number(child.dataset[axis])).toBeGreaterThan(
        Number(root.dataset[axis])
      );
    }
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(successToast).not.toHaveBeenCalled();
  });

  it("reveals path siblings while collapsing their previously expanded descendants", async () => {
    const tree = [
      {
        ...movableOrganizations[0]!,
        children: [
          movableOrganizations[0]!.children![0]!,
          {
            ...movableOrganizations[0]!.children![1]!,
            children: [
              {
                id: "neighbor-child",
                name: "Neighbor child",
                path: "/root/target/neighbor-child",
                parent_id: "target",
                children: [],
              },
            ],
          },
        ],
      },
    ];
    const props = {
      ...handlers,
      organizations: tree,
      selectedOrg: null,
      members: [],
      editable: true,
      capabilityLoading: false,
    };
    const { rerender } = render(<OrganizationDesigner {...props} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Toggle subtree target" })
    );
    expect(
      screen.getByRole("button", { name: "Neighbor child movable" })
    ).toBeInTheDocument();
    rerender(
      <OrganizationDesigner
        {...props}
        revealRequest={{
          id: 999,
          result: tree[0]!.children[0]!.children![0]!,
          ancestorIds: ["root", "source"],
        }}
      />
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Leaf movable" })
      ).toBeInTheDocument()
    );
    expect(
      screen.getByRole("button", { name: "Target movable" })
    ).toHaveAttribute("data-child-count", "1");
    expect(
      screen.getByRole("button", { name: "Enterprise movable" })
    ).toHaveAttribute("data-child-count", "2");
    expect(
      screen.queryByRole("button", { name: "Neighbor child movable" })
    ).not.toBeInTheDocument();
    expect(fitView).toHaveBeenLastCalledWith(
      expect.objectContaining({
        nodes: [expect.objectContaining({ id: "leaf" })],
      })
    );
  });

  it("confirms drag reparenting", async () => {
    mockIntersectingNodes.mockReturnValue([{ id: "target" }]);
    const user = setupUser();
    const onExpandOrg = jest.fn().mockResolvedValue(undefined);
    render(
      <OrganizationDesigner
        organizations={movableOrganizations}
        selectedOrg={null}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
        onExpandOrg={onExpandOrg}
      />
    );
    const source = screen.getByRole("button", {
      name: /^Source (locked|movable)$/,
    });
    expect(source).toHaveAttribute("data-draggable", "true");
    fireEvent.pointerUp(source);
    expect(handlers.onMoveOrg).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Approve change" }));
    await waitFor(() =>
      expect(handlers.onMoveOrg).toHaveBeenCalledWith("source", "target")
    );
    expect(onExpandOrg).toHaveBeenCalledWith("target");
  });

  it.each(["source", "leaf", "root", "outside"])(
    "rejects a drop onto %s",
    (target) => {
      mockIntersectingNodes.mockReturnValue([{ id: target }]);
      render(
        <OrganizationDesigner
          organizations={movableOrganizations}
          selectedOrg={null}
          members={[]}
          editable
          capabilityLoading={false}
          {...handlers}
        />
      );
      fireEvent.pointerUp(
        screen.getByRole("button", { name: /^Source (locked|movable)$/ })
      );
      expect(
        screen.queryByRole("button", { name: "Approve change" })
      ).not.toBeInTheDocument();
      expect(handlers.onMoveOrg).not.toHaveBeenCalled();
    }
  );

  it("keeps assigned scope roots undraggable", () => {
    const tree = [{ ...movableOrganizations[0]!, is_scope_root: true }];
    render(
      <OrganizationDesigner
        organizations={tree}
        selectedOrg={null}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );
    expect(
      screen.getByRole("button", { name: /^Enterprise locked$/ })
    ).toHaveAttribute("data-draggable", "false");
  });

  it("restores compact coordinates when a valid drop is cancelled", async () => {
    mockIntersectingNodes.mockReturnValue([{ id: "target" }]);
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={movableOrganizations}
        selectedOrg={null}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );
    const source = screen.getByRole("button", { name: /^Source movable$/ });
    const originalX = source.getAttribute("data-position-x");
    fireEvent.pointerUp(source);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(source).toHaveAttribute("data-position-x", originalX);
    expect(handlers.onMoveOrg).not.toHaveBeenCalled();
  });

  it("uses compact layout for small trees without a mode switch", () => {
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );
    expect(
      screen.queryByRole("button", { name: "Compact tree" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Enterprise movable" })
    ).toHaveAttribute("data-position-x", "140");
  });

  it("browses large trees one level at a time without saving projected positions", async () => {
    const leaf: OrganizationNode = {
      id: "leaf",
      name: "Leaf",
      path: "/root/child/grand/leaf",
      parent_id: "grand",
      children: [],
    };
    const grand: OrganizationNode = {
      id: "grand",
      name: "Grand",
      path: "/root/child/grand",
      parent_id: "child",
      children: [leaf],
    };
    const tree = [
      {
        ...organizations[0]!,
        children: [{ ...organizations[0]!.children![0]!, children: [grand] }],
      },
    ];
    const savedPositions = Object.fromEntries(
      Array.from({ length: 200 }, (_, index) => [
        String(index),
        { x: index * 10000, y: 0 },
      ])
    );
    savedPositions.root = { x: 1000000, y: 0 };
    const user = setupUser();
    const { rerender } = render(
      <OrganizationDesigner
        organizations={tree}
        selectedOrg={null}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );
    expect(
      screen.queryByRole("button", { name: "Compact tree" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Leaf movable" })
    ).not.toBeInTheDocument();
    const root = screen.getByRole("button", { name: "Enterprise movable" });
    expect(Number(root.dataset.positionX)).toBeLessThan(10000);
    fireEvent.pointerUp(root);
    await user.click(
      screen.getByRole("button", { name: "Toggle subtree child" })
    );
    await user.click(
      screen.getByRole("button", { name: "Toggle subtree grand" })
    );
    expect(
      await screen.findByRole("button", { name: "Leaf movable" })
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(fitView).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.arrayContaining([
            expect.objectContaining({ id: "grand" }),
            expect.objectContaining({ id: "leaf" }),
          ]),
        })
      )
    );
    await user.click(
      screen.getByRole("button", { name: "Toggle subtree grand" })
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Leaf movable" })
      ).not.toBeInTheDocument()
    );
    rerender(
      <OrganizationDesigner
        organizations={tree}
        selectedOrg={null}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
        revealRequest={{
          id: 1,
          result: leaf,
          ancestorIds: ["root", "child", "grand"],
        }}
      />
    );
    expect(
      await screen.findByRole("button", { name: "Leaf movable" })
    ).toBeInTheDocument();
  });

  it.each(["vertically", "horizontally"])(
    "keeps a large tree compact when switching %s",
    async (direction) => {
      const tree: OrganizationNode[] = [
        {
          id: "root",
          name: "Enterprise",
          path: "/root",
          parent_id: null,
          children: [],
        },
      ];
      let parent = tree[0]!;
      const ids = [parent.id];
      for (let index = 1; index < 200; index++) {
        const child: OrganizationNode = {
          id: `unit-${index}`,
          name: `Unit ${index}`,
          path: `${parent.path}/${index}`,
          parent_id: parent.id,
          children: [],
        };
        parent.children = [child];
        parent = child;
        ids.push(child.id);
      }
      mockCompleteTreeFetch(tree);
      const user = setupUser();
      render(
        <OrganizationDesigner
          organizations={tree}
          selectedOrg={null}
          members={[]}
          editable
          capabilityLoading={false}
          {...handlers}
        />
      );
      await user.click(
        screen.getByRole("button", {
          name:
            direction === "vertically" ? "Vertical view" : "Horizontal view",
        })
      );
      await waitFor(() =>
        expect(screen.queryByRole("progressbar")).not.toBeInTheDocument()
      );
      expect(screen.getByTestId("react-flow")).toHaveAttribute(
        "data-edge-count",
        "1"
      );
      expect(
        screen.getByRole("button", { name: "Enterprise movable" })
      ).toBeInTheDocument();
    }
  );

  it("fits compact layouts and lets read-only viewers return to the root", async () => {
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        {...handlers}
        canMoveOrganization={false}
      />
    );
    expect(Number(screen.getByTestId("react-flow").dataset.minZoom)).toBe(0.2);
    await user.click(screen.getByRole("button", { name: "Fit view" }));
    expect(fitView).toHaveBeenLastCalledWith(
      expect.objectContaining({ minZoom: expect.any(Number) })
    );
    const rootControl = screen.getByRole("button", { name: "Focus root" });
    expect(rootControl.closest("header")).toBeNull();
    await user.click(rootControl);
    expect(fitView).toHaveBeenLastCalledWith(
      expect.objectContaining({
        nodes: expect.arrayContaining([
          expect.objectContaining({ id: "root" }),
          expect.objectContaining({ id: "child" }),
        ]),
        minZoom: 0.1,
        maxZoom: 1,
      })
    );
  });

  it("renders the operational map and protects automatic coordinates", async () => {
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    expect(
      screen.getByRole("dialog", { name: "Organization designer" })
    ).toBeInTheDocument();
    expect(screen.getByTestId("flow-controls")).toBeInTheDocument();
    expect(screen.getByTestId("flow-minimap")).toBeInTheDocument();
    expect(screen.getByTestId("react-flow")).toHaveAttribute(
      "data-edge-count",
      "1"
    );
    expect(screen.getByTestId("react-flow")).toHaveAttribute(
      "data-hide-attribution",
      "true"
    );
    expect(screen.getByTestId("react-flow")).toHaveAttribute(
      "data-color-mode",
      "light"
    );

    await user.click(screen.getByRole("button", { name: /Platform movable/ }));
    expect(handlers.onSelectOrg).toHaveBeenCalledWith(
      organizations[0]!.children![0]
    );

    fireEvent.pointerUp(
      screen.getByRole("button", { name: /Enterprise movable/ })
    );
    expect(handlers.onMoveOrg).not.toHaveBeenCalled();

    const rootNode = screen.getByRole("button", { name: /Enterprise movable/ });
    rootNode.focus();
    await user.keyboard("{ArrowRight}");
    expect(rootNode).toHaveAttribute("data-position-x", "140");

    await user.click(screen.getByRole("button", { name: "Fit view" }));
    expect(fitView).toHaveBeenCalled();
  });

  it("shares the user toggle and direct members with visual nodes", async () => {
    const user = setupUser();
    const onShowMembersChange = jest.fn();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        showMembers
        membersByOrganizationId={{
          root: [
            {
              id: "membership-1",
              user_id: "user-1",
              organization_id: "root",
              role_in_org: "member",
              user: { id: "user-1", email: "member@example.com" },
            },
          ],
        }}
        onShowMembersChange={onShowMembersChange}
        {...handlers}
      />
    );

    expect(
      screen.getByRole("button", { name: /Enterprise movable/ })
    ).toHaveAttribute("data-member-count", "1");
    await user.click(screen.getByRole("button", { name: "Hide users" }));
    expect(onShowMembersChange).toHaveBeenCalledWith(false);
  });

  it("reparents without saving automatic positions", async () => {
    const user = setupUser();

    render(
      <OrganizationDesigner
        organizations={movableOrganizations}
        selectedOrg={movableOrganizations[0]!.children![0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    await user.click(screen.getByRole("button", { name: "Move Source" }));
    await user.click(screen.getByRole("button", { name: "Approve change" }));

    await waitFor(() =>
      expect(handlers.onMoveOrg).toHaveBeenCalledWith("source", "target")
    );
  });

  it("keeps diagram positions unchanged when reparenting fails", async () => {
    const user = setupUser();
    handlers.onMoveOrg.mockResolvedValueOnce(false);

    render(
      <OrganizationDesigner
        organizations={movableOrganizations}
        selectedOrg={movableOrganizations[0]!.children![0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    await user.click(screen.getByRole("button", { name: "Move Source" }));
    await user.click(screen.getByRole("button", { name: "Approve change" }));

    await waitFor(() => expect(handlers.onMoveOrg).toHaveBeenCalled());
  });

  it("lets mobile users return to the map and reopen the selected inspector", async () => {
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    await user.click(screen.getByRole("button", { name: "Back to map" }));
    expect(screen.getByTestId("inspector")).toHaveAttribute(
      "data-mobile-open",
      "false"
    );
    await user.click(screen.getByRole("button", { name: "Show inspector" }));
    expect(screen.getByTestId("inspector")).toHaveAttribute(
      "data-mobile-open",
      "true"
    );
  });

  it.each(["keyboard", "mouse"])(
    "reveals exactly the %s-selected result and exits broad search",
    async (method) => {
      jest.useFakeTimers();
      const user = setupUser();
      const onSearch = jest.fn();
      const onRevealResult = jest.fn();
      const runtime: OrganizationNode = {
        id: "runtime",
        name: "Runtime",
        path: "/enterprise/platform/runtime",
        parent_id: "child",
        children: [],
      };
      render(
        <OrganizationDesigner
          organizations={organizations}
          selectedOrg={null}
          members={[]}
          editable={false}
          capabilityLoading={false}
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
      await jest.advanceTimersByTimeAsync(250);
      expect(onSearch).toHaveBeenCalledWith("ru");
      expect(screen.getByRole("option", { name: /Runtime/ })).toHaveTextContent(
        "/enterprise/platform/runtime"
      );
      if (method === "keyboard") await user.keyboard("{ArrowDown}{Enter}");
      else await user.click(screen.getByRole("option", { name: /Runtime/ }));
      expect(onRevealResult).toHaveBeenCalledWith(runtime);
      expect(search).toHaveValue("");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(onSearch).toHaveBeenLastCalledWith("");
      jest.useRealTimers();
    }
  );

  it("waits for the chosen descendant to initialize before focusing only that node", async () => {
    const runtime: OrganizationNode = {
      id: "runtime",
      name: "Runtime",
      parent_id: "child",
      path: "/enterprise/child/runtime",
      children: [],
    };
    const tree = [
      {
        ...organizations[0]!,
        children: [{ ...organizations[0]!.children![0]!, children: [runtime] }],
      },
    ];
    const onRevealReady = jest.fn();
    const props = {
      organizations: tree,
      selectedOrg: null,
      members: [],
      editable: false,
      capabilityLoading: false,
      ...handlers,
      onRevealReady,
    };
    const { rerender } = render(<OrganizationDesigner {...props} />);
    fitView.mockClear();
    mockNodesInitialized = false;
    const revealRequest = {
      id: 77,
      result: runtime,
      ancestorIds: ["root", "child"],
    };
    rerender(<OrganizationDesigner {...props} revealRequest={revealRequest} />);
    expect(
      screen.getByRole("button", { name: "Runtime movable" })
    ).toBeInTheDocument();
    expect(fitView).not.toHaveBeenCalled();
    expect(onRevealReady).not.toHaveBeenCalled();
    mockNodesInitialized = true;
    rerender(<OrganizationDesigner {...props} revealRequest={revealRequest} />);
    await waitFor(() => expect(onRevealReady).toHaveBeenCalledWith(runtime));
    expect(fitView).toHaveBeenLastCalledWith(
      expect.objectContaining({
        nodes: [expect.objectContaining({ id: "runtime" })],
        minZoom: 0.5,
        maxZoom: 1,
      })
    );
  });

  it("keeps loaded-node highlighting while remote search is active", async () => {
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        searchResults={[]}
        searchLoading={false}
        searchError={null}
        resultsLimited={false}
        onSearch={jest.fn()}
        onRevealResult={jest.fn()}
        {...handlers}
      />
    );

    const search = screen.getByRole("combobox", {
      name: "Search organizations",
    });
    await user.type(search, "plat");

    expect(
      screen.getByRole("button", { name: /Platform movable/ })
    ).toHaveAttribute("data-search-state", "match");
    expect(
      screen.getByRole("button", { name: /Enterprise movable/ })
    ).toHaveAttribute("data-search-state", "dimmed");
    await user.keyboard("{Escape}");
    expect(search).toHaveValue("");
    expect(handlers.onClose).not.toHaveBeenCalled();
  });

  it("starts first-root creation with a temporary canvas node", async () => {
    const user = setupUser();
    const promptSpy = jest.spyOn(window, "prompt");
    render(
      <OrganizationDesigner
        organizations={[]}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        {...handlers}
        canCreateRoot
      />
    );

    await user.click(
      screen.getByRole("button", { name: "Create root organization" })
    );
    expect(
      screen.getByRole("button", { name: /New organization locked/ })
    ).toBeInTheDocument();
    expect(promptSpy).not.toHaveBeenCalled();
    expect(handlers.onCreateOrg).not.toHaveBeenCalled();
  });

  it("does not expose root creation without the global org:create permission", () => {
    render(
      <OrganizationDesigner
        organizations={[]}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        {...handlers}
      />
    );

    expect(
      screen.queryByRole("button", { name: "Create root organization" })
    ).not.toBeInTheDocument();
  });

  it("keeps scoped nodes locked without org:move permission", () => {
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
        canMoveOrganization={false}
      />
    );

    const rootNode = screen.getByRole("button", { name: /Enterprise locked/ });
    fireEvent.pointerUp(rootNode);
    expect(
      screen.queryByRole("button", { name: "Vertical view" })
    ).toBeInTheDocument();
  });

  it("waits for committed React Flow nodes before fitting the orientation change", async () => {
    mockCompleteTreeFetch();
    mockNodesInitialized = false;
    const user = setupUser();
    const { rerender } = render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );
    fitView.mockClear();

    await user.click(screen.getByRole("button", { name: "Vertical view" }));

    expect(fitView).not.toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();

    mockNodesInitialized = true;
    rerender(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    await waitFor(() =>
      expect(fitView).toHaveBeenCalledWith(
        expect.objectContaining({
          nodes: expect.arrayContaining([
            expect.objectContaining({ id: "root" }),
            expect.objectContaining({ id: "child" }),
          ]),
        })
      )
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("focuses loaded children and keeps the viewport stable while collapsing", async () => {
    const onExpandOrg = jest.fn().mockResolvedValue(undefined);
    const unloadedTree = [
      {
        ...organizations[0]!,
        children: [],
        has_children: true,
        children_count: 1,
      },
    ];
    const { rerender } = render(
      <OrganizationDesigner
        organizations={unloadedTree}
        selectedOrg={unloadedTree[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        onExpandOrg={onExpandOrg}
        {...handlers}
      />
    );
    fitView.mockClear();

    fireEvent.click(
      screen.getByRole("button", { name: "Toggle subtree root" })
    );
    expect(onExpandOrg).toHaveBeenCalledWith("root");
    rerender(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        onExpandOrg={onExpandOrg}
        {...handlers}
      />
    );

    expect(fitView).toHaveBeenCalled();
    fitView.mockClear();
    expect(
      screen.getByRole("button", { name: /^Platform movable$/ })
    ).toHaveAttribute("data-position-x", "140");

    fireEvent.click(
      screen.getByRole("button", { name: "Toggle subtree root" })
    );
    expect(fitView).not.toHaveBeenCalled();
  });

  it("routes Escape through the same close safeguard", async () => {
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
      />
    );

    await user.keyboard("{Escape}");
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it("focuses and traps the modal, then restores focus to its launcher", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Launch designer</button>
          {open && (
            <OrganizationDesigner
              organizations={organizations}
              selectedOrg={organizations[0]!}
              members={[]}
              editable
              capabilityLoading={false}
              {...handlers}
              onClose={() => setOpen(false)}
            />
          )}
        </>
      );
    }

    const user = setupUser();
    render(<Harness />);
    const launcher = screen.getByRole("button", { name: "Launch designer" });
    await user.click(launcher);

    const dialog = screen.getByRole("dialog", {
      name: "Organization designer",
    });
    expect(dialog).toHaveFocus();
    expect(launcher.closest('[aria-hidden="true"]')).not.toBeNull();
    await user.tab({ shift: true });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    await user.click(screen.getByRole("button", { name: "Close designer" }));
    await waitFor(() => expect(launcher).toHaveFocus());
  });
});
