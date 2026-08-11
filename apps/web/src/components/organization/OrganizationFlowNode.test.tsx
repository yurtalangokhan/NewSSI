/**
 * @jest-environment jsdom
 */

import { ReactFlow, ReactFlowProvider, type Node } from "@xyflow/react";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import "@/i18n/config";

import { OrganizationFlowNode } from "@/components/organization/OrganizationFlowNode";
import { SvgNetworkGraph } from "@/icons";
import { setupUser } from "@tests/setup/test-utils";

function renderFlowNode(node: ReactElement) {
  return render(<ReactFlowProvider>{node}</ReactFlowProvider>);
}

describe("OrganizationFlowNode", () => {
  it("uses the application icon entrypoint for hierarchy metadata", () => {
    expect(SvgNetworkGraph).toBeDefined();
  });

  it("renders organization context, child count, and position-lock state", () => {
    renderFlowNode(
      <OrganizationFlowNode
        id="product"
        data={{
          organizationId: "product",
          name: "Product",
          path: "root/product/",
          childCount: 3,
          readOnly: true,
        }}
        selected={false}
        selectable
        draggable={false}
        deletable={false}
        dragging={false}
        zIndex={0}
        isConnectable={false}
        type="organization"
        positionAbsoluteX={0}
        positionAbsoluteY={0}
      />
    );

    expect(screen.getByText("Product")).toBeInTheDocument();
    expect(screen.queryByText("root/product/")).not.toBeInTheDocument();
    expect(screen.getByText("3 children")).toBeInTheDocument();
    expect(screen.getByText("Position locked")).toBeInTheDocument();
    expect(screen.queryByText("Read-only")).not.toBeInTheDocument();
  });

  it("exposes selected state for the active organization", () => {
    const { getByTestId } = renderFlowNode(
      <OrganizationFlowNode
        id="sales"
        data={{
          organizationId: "sales",
          name: "Sales",
          path: "root/sales/",
          childCount: 1,
          readOnly: false,
        }}
        selected
        selectable
        draggable
        deletable={false}
        dragging={false}
        zIndex={0}
        isConnectable={false}
        type="organization"
        positionAbsoluteX={0}
        positionAbsoluteY={0}
      />
    );

    expect(getByTestId("organization-flow-node-sales")).toHaveAttribute(
      "data-selected",
      "true"
    );
  });

  it("provides source and target anchors when rendered on a React Flow canvas", () => {
    const nodes: Node[] = [
      {
        id: "platform",
        type: "organization",
        position: { x: 0, y: 0 },
        data: {
          organizationId: "platform",
          name: "Platform",
          path: "root/platform/",
          childCount: 0,
          readOnly: false,
        },
      },
    ];

    const { container } = render(
      <ReactFlowProvider>
        <div style={{ height: 400, width: 600 }}>
          <ReactFlow
            fitView
            nodes={nodes}
            edges={[]}
            nodeTypes={{ organization: OrganizationFlowNode }}
          />
        </div>
      </ReactFlowProvider>
    );

    expect(
      container.querySelector(
        '[data-nodeid="platform"][data-handlepos="top"].target'
      )
    ).toBeInTheDocument();
    expect(
      container.querySelector(
        '[data-nodeid="platform"][data-handlepos="bottom"].source'
      )
    ).toBeInTheDocument();
  });

  it("renames an editable organization inside its selected node", async () => {
    const onRename = jest.fn().mockResolvedValue(undefined);
    const user = setupUser();
    renderFlowNode(
      <OrganizationFlowNode
        id="platform"
        data={{
          organizationId: "platform",
          name: "Platform",
          path: "root/platform/",
          childCount: 0,
          readOnly: false,
          actionMode: "rename",
          onRename,
        }}
        selected
        selectable
        draggable
        deletable={false}
        dragging={false}
        zIndex={0}
        isConnectable={false}
        type="organization"
        positionAbsoluteX={0}
        positionAbsoluteY={0}
      />
    );

    const input = screen.getByRole("textbox", {
      name: "Organization name for Platform",
    });
    await user.clear(input);
    await user.type(input, "Platform Engineering");
    await user.keyboard("{Enter}");

    expect(onRename).toHaveBeenCalledWith("Platform Engineering");
  });

  it("confirms deletion inside the selected node", async () => {
    const onDelete = jest.fn().mockResolvedValue(undefined);
    const user = setupUser();
    renderFlowNode(
      <OrganizationFlowNode
        id="platform"
        data={{
          organizationId: "platform",
          name: "Platform",
          path: "root/platform/",
          childCount: 0,
          readOnly: false,
          actionMode: "delete",
          onDelete,
        }}
        selected
        selectable
        draggable
        deletable={false}
        dragging={false}
        zIndex={0}
        isConnectable={false}
        type="organization"
        positionAbsoluteX={0}
        positionAbsoluteY={0}
      />
    );

    expect(screen.getByText("Delete organization?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Platform" }));

    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("groups add, rename, and delete actions with compact spacing", () => {
    renderFlowNode(
      <OrganizationFlowNode
        id="platform"
        data={{
          organizationId: "platform",
          name: "Platform",
          path: "root/platform/",
          childCount: 2,
          readOnly: false,
          canAddChild: true,
          canManage: true,
        }}
        selected
        selectable
        draggable
        deletable={false}
        dragging={false}
        zIndex={0}
        isConnectable={false}
        type="organization"
        positionAbsoluteX={0}
        positionAbsoluteY={0}
      />
    );

    const actions = screen.getByTestId("organization-node-actions");
    expect(actions).toHaveClass("gap-0.5");
    expect(actions).toContainElement(
      screen.getByRole("button", { name: "Add child to Platform" })
    );
    expect(actions).toContainElement(
      screen.getByRole("button", { name: "Rename Platform" })
    );
    expect(actions).toContainElement(
      screen.getByRole("button", { name: "Delete Platform" })
    );
  });
});
