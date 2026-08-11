import {
  organizationTreeToFlowGraph,
  type OrganizationTreeNode,
} from "@/components/organization/organizationGraph";

const organizations: OrganizationTreeNode[] = [
  {
    id: "root",
    name: "Root",
    path: "root/",
    parent_id: null,
    children: [
      {
        id: "product",
        name: "Product",
        path: "root/product/",
        parent_id: "root",
        children: [],
      },
      {
        id: "sales",
        name: "Sales",
        path: "root/sales/",
        parent_id: "root",
        children: [],
      },
    ],
  },
];

const unevenOrganizations: OrganizationTreeNode[] = [
  {
    id: "root",
    name: "Root",
    path: "root/",
    parent_id: null,
    children: [
      {
        id: "a",
        name: "A",
        path: "root/a/",
        parent_id: "root",
        children: ["a1", "a2", "a3"].map((id) => ({
          id,
          name: id.toUpperCase(),
          path: `root/a/${id}/`,
          parent_id: "a",
          children: [],
        })),
      },
      {
        id: "b",
        name: "B",
        path: "root/b/",
        parent_id: "root",
        children: [
          {
            id: "b1",
            name: "B1",
            path: "root/b/b1/",
            parent_id: "b",
            children: [
              {
                id: "b1-deep",
                name: "B1 deep",
                path: "root/b/b1/deep/",
                parent_id: "b1",
                children: [],
              },
            ],
          },
        ],
      },
    ],
  },
];

describe("organizationTreeToFlowGraph", () => {
  it("flattens every organization, derives hierarchy edges, and counts direct children", () => {
    const graph = organizationTreeToFlowGraph(organizations);

    expect(graph.nodes.map((node) => node.id)).toEqual([
      "root",
      "product",
      "sales",
    ]);
    expect(graph.nodes[0]?.data.childCount).toBe(2);
    expect(graph.edges).toEqual([
      expect.objectContaining({
        id: "root-product",
        source: "root",
        target: "product",
      }),
      expect.objectContaining({
        id: "root-sales",
        source: "root",
        target: "sales",
      }),
    ]);
  });

  it("uses saved positions before deterministic fallback positions", () => {
    const first = organizationTreeToFlowGraph(organizations, {
      product: { x: 880, y: 440 },
    });
    const second = organizationTreeToFlowGraph(organizations, {
      product: { x: 880, y: 440 },
    });

    expect(first.nodes.find((node) => node.id === "product")?.position).toEqual(
      {
        x: 880,
        y: 440,
      }
    );
    expect(first.nodes.find((node) => node.id === "sales")?.position).toEqual(
      second.nodes.find((node) => node.id === "sales")?.position
    );
    expect(
      first.nodes.find((node) => node.id === "sales")?.position
    ).not.toEqual(first.nodes.find((node) => node.id === "root")?.position);
  });

  it("marks only writable nodes draggable while leaving read-only nodes selectable", () => {
    const graph = organizationTreeToFlowGraph(
      organizations,
      {},
      new Set(["product"]),
      "sales"
    );

    expect(graph.nodes.find((node) => node.id === "product")).toEqual(
      expect.objectContaining({ draggable: true })
    );
    expect(graph.nodes.find((node) => node.id === "sales")).toEqual(
      expect.objectContaining({
        draggable: false,
        selectable: true,
        selected: true,
      })
    );
  });

  it("assigns deterministic unique fallback positions to uneven adjacent subtrees", () => {
    const first = organizationTreeToFlowGraph(unevenOrganizations);
    const second = organizationTreeToFlowGraph(unevenOrganizations);
    const coordinateKeys = first.nodes.map(
      ({ position }) => `${position.x}:${position.y}`
    );

    expect(new Set(coordinateKeys).size).toBe(first.nodes.length);
    expect(first.nodes.map(({ id, position }) => ({ id, position }))).toEqual(
      second.nodes.map(({ id, position }) => ({ id, position }))
    );
    expect(first.nodes.find(({ id }) => id === "a3")?.position).not.toEqual(
      first.nodes.find(({ id }) => id === "b1")?.position
    );
  });
});
