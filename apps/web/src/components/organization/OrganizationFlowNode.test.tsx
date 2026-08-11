/**
 * @jest-environment jsdom
 */

import { ReactFlow, ReactFlowProvider, type Node } from "@xyflow/react";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { OrganizationFlowNode } from "@/components/organization/OrganizationFlowNode";
import { SvgNetworkGraph } from "@/icons";

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
    expect(screen.getByText("root/product/")).toBeInTheDocument();
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
});
