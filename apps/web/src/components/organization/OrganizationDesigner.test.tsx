import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import "@/i18n/config";

import { OrganizationDesigner } from "@/components/organization/OrganizationDesigner";
import { useOrganizationLayout } from "@/components/organization/useOrganizationLayout";
import { toast } from "@/hooks/useToast";
import { render, setupUser } from "@tests/setup/test-utils";

const fitView = jest.fn();

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
    ReactFlow: ({
      nodes,
      edges,
      onInit,
      onNodeClick,
      onNodeDragStop,
      onNodesChange,
      proOptions,
      children,
    }: any) => {
      React.useEffect(
        () => onInit?.({ fitView, getIntersectingNodes: () => [] }),
        [onInit]
      );
      return (
        <div
          data-testid="react-flow"
          data-edge-count={edges.length}
          data-hide-attribution={String(proOptions?.hideAttribution)}
        >
          {nodes.map((node: any) => (
            <React.Fragment key={node.id}>
              <button
                onClick={() => onNodeClick?.({}, node)}
                onPointerUp={() => {
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

jest.mock("@/components/organization/useOrganizationLayout", () => ({
  useOrganizationLayout: jest.fn(),
}));

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

const mockedUseOrganizationLayout = jest.mocked(useOrganizationLayout);
const layoutActions = {
  positions: {},
  writableOrganizationIds: new Set(["root"]),
  status: "idle" as const,
  error: undefined,
  isLoading: false,
  hasDirtyPositions: false,
  isWritable: (id: string) => id === "root",
  setPosition: jest.fn(),
  replacePositionsAndSave: jest.fn().mockResolvedValue(true),
  flush: jest.fn().mockResolvedValue(true),
  retry: jest.fn().mockResolvedValue(true),
  discard: jest.fn(),
  refresh: jest.fn(),
};

const organizations = [
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

const movableOrganizations = [
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
  canCreateRoot: false,
  canEditLayout: true,
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

describe("OrganizationDesigner", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedUseOrganizationLayout.mockReturnValue({ ...layoutActions });
  });

  it("renders the operational map and changes coordinates without reparenting", async () => {
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
    expect(layoutActions.refresh).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Platform locked/ }));
    expect(handlers.onSelectOrg).toHaveBeenCalledWith(
      organizations[0]!.children![0]
    );

    layoutActions.setPosition.mockClear();
    fireEvent.pointerUp(
      screen.getByRole("button", { name: /Enterprise movable/ })
    );
    expect(layoutActions.setPosition).toHaveBeenCalledWith("root", {
      x: 90,
      y: 120,
    });
    expect(layoutActions.setPosition).toHaveBeenCalledTimes(1);
    expect(handlers.onMoveOrg).not.toHaveBeenCalled();

    const rootNode = screen.getByRole("button", { name: /Enterprise movable/ });
    rootNode.focus();
    await user.keyboard("{ArrowRight}");
    expect(rootNode).toHaveAttribute("data-position-x", "85");

    await user.click(screen.getByRole("button", { name: "Fit view" }));
    expect(fitView).toHaveBeenCalled();
  });

  it("repositions and saves only the moved subtree after a successful reparent", async () => {
    const user = setupUser();
    mockedUseOrganizationLayout.mockReturnValue({
      ...layoutActions,
      positions: {
        root: { x: 200, y: 0 },
        source: { x: 0, y: 180 },
        leaf: { x: 0, y: 360 },
        target: { x: 400, y: 180 },
      },
    });

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
    await waitFor(() =>
      expect(layoutActions.replacePositionsAndSave).toHaveBeenCalledWith({
        source: { x: 400, y: 360 },
        leaf: { x: 400, y: 540 },
      })
    );
    expect(fitView).toHaveBeenCalledWith(
      expect.objectContaining({
        nodes: [expect.objectContaining({ id: "source" })],
        duration: 300,
      })
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
    expect(layoutActions.replacePositionsAndSave).not.toHaveBeenCalled();
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

  it("keeps the full graph visible and emphasizes inline search matches", async () => {
    const user = setupUser();
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        {...handlers}
      />
    );

    const search = screen.getByRole("textbox", {
      name: "Search organizations",
    });
    await user.type(search, "plat");

    expect(
      screen.getByRole("button", { name: /Platform locked/ })
    ).toHaveAttribute("data-search-state", "match");
    expect(
      screen.getByRole("button", { name: /Enterprise movable/ })
    ).toHaveAttribute("data-search-state", "dimmed");
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Previous result" })
    ).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Next result" }));
    expect(handlers.onSelectOrg).toHaveBeenCalledWith(
      organizations[0]!.children![0]
    );

    handlers.onSelectOrg.mockClear();
    await user.keyboard("{Enter}");
    expect(handlers.onSelectOrg).toHaveBeenCalledWith(
      organizations[0]!.children![0]
    );
    expect(fitView).toHaveBeenCalledWith(
      expect.objectContaining({ duration: 300 })
    );

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

  it("keeps backend-writable nodes locked without coarse org:update permission", () => {
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={organizations[0]!}
        members={[]}
        editable
        capabilityLoading={false}
        {...handlers}
        canEditLayout={false}
      />
    );

    const rootNode = screen.getByRole("button", { name: /Enterprise locked/ });
    fireEvent.pointerUp(rootNode);
    expect(layoutActions.setPosition).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "Reset diagram vertically" })
    ).not.toBeInTheDocument();
  });

  it.each([
    ["Reset diagram vertically", "vertical"],
    ["Reset diagram horizontally", "horizontal"],
  ])(
    "confirms, persists, and fits the %s layout",
    async (buttonName, orientation) => {
      const successToast = jest.spyOn(toast, "success");
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

      await user.click(screen.getByRole("button", { name: buttonName }));
      expect(
        screen.getByRole("dialog", { name: "Reset diagram layout?" })
      ).toBeInTheDocument();
      expect(layoutActions.replacePositionsAndSave).not.toHaveBeenCalled();

      await user.click(screen.getByRole("button", { name: "Reset layout" }));

      await waitFor(() =>
        expect(layoutActions.replacePositionsAndSave).toHaveBeenCalledWith(
          expect.objectContaining({
            root: expect.any(Object),
            child: expect.any(Object),
          })
        )
      );
      const positions =
        layoutActions.replacePositionsAndSave.mock.calls.at(-1)![0];
      if (orientation === "vertical") {
        expect(positions.root.y).toBeLessThan(positions.child.y);
      } else {
        expect(positions.root.x).toBeLessThan(positions.child.x);
      }
      await waitFor(() =>
        expect(fitView).toHaveBeenCalledWith(
          expect.objectContaining({ duration: 300 })
        )
      );
      expect(successToast).toHaveBeenCalledWith(
        "Diagram layout reset and saved"
      );
    }
  );

  it("cancels diagram reset without saving positions", async () => {
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

    await user.click(
      screen.getByRole("button", { name: "Reset diagram vertically" })
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(layoutActions.replacePositionsAndSave).not.toHaveBeenCalled();
  });

  it("keeps the fallback map usable while the saved layout is loading", () => {
    mockedUseOrganizationLayout.mockReturnValueOnce({
      ...layoutActions,
      isLoading: true,
    });

    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        {...handlers}
      />
    );

    expect(screen.getByRole("button", { name: /Enterprise/ })).toBeVisible();
    expect(
      screen.queryByText("Loading organization map…")
    ).not.toBeInTheDocument();
    expect(screen.getByText("Loading layout…")).toBeInTheDocument();
  });

  it("does not force an extra layout revalidation when the designer mounts", () => {
    render(
      <OrganizationDesigner
        organizations={organizations}
        selectedOrg={null}
        members={[]}
        editable={false}
        capabilityLoading={false}
        {...handlers}
      />
    );

    expect(layoutActions.refresh).not.toHaveBeenCalled();
  });

  it("waits for a successful pending-layout flush before closing", async () => {
    let resolveFlush: ((saved: boolean) => void) | undefined;
    const flush = jest.fn(
      () => new Promise<boolean>((resolve) => (resolveFlush = resolve))
    );
    mockedUseOrganizationLayout.mockReturnValue({
      ...layoutActions,
      hasDirtyPositions: true,
      flush,
    });
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

    await user.click(screen.getByRole("button", { name: "Close designer" }));
    expect(handlers.onClose).not.toHaveBeenCalled();
    resolveFlush?.(true);
    await waitFor(() => expect(handlers.onClose).toHaveBeenCalledTimes(1));
  });

  it("keeps a failed close open until retry or explicit discard", async () => {
    mockedUseOrganizationLayout.mockReturnValue({
      ...layoutActions,
      hasDirtyPositions: true,
      status: "error",
      error: new Error("Layout is locked"),
      flush: jest.fn().mockResolvedValue(false),
    });
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

    await user.click(screen.getByRole("button", { name: "Close designer" }));
    expect(handlers.onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Discard and close" })
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Discard and close" }));
    expect(layoutActions.discard).toHaveBeenCalledTimes(1);
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
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
    expect(layoutActions.flush).toHaveBeenCalledTimes(1);
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
