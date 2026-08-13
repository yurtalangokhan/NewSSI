import {
  inferOrganizationLayoutOrientation,
  repositionOrganizationSubtree,
  organizationTreeToLayoutPositions,
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

const wideOrganizations: OrganizationTreeNode[] = [
  {
    id: "wide-root",
    name: "Wide root",
    path: "wide-root/",
    parent_id: null,
    children: Array.from({ length: 12 }, (_, index) => ({
      id: `wide-child-${index}`,
      name: `Wide child ${index}`,
      path: `wide-root/wide-child-${index}/`,
      parent_id: "wide-root",
      children: [],
    })),
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

describe("organizationTreeToLayoutPositions", () => {
  it("places hierarchy levels top-to-bottom for vertical layout", () => {
    const positions = organizationTreeToLayoutPositions(
      organizations,
      "vertical"
    );

    expect(positions.root!.y).toBeLessThan(positions.product!.y);
    expect(positions.product!.y).toBe(positions.sales!.y);
    expect(positions.product!.x).not.toBe(positions.sales!.x);
  });

  it("places hierarchy levels left-to-right for horizontal layout", () => {
    const positions = organizationTreeToLayoutPositions(
      organizations,
      "horizontal"
    );

    expect(positions.root!.x).toBeLessThan(positions.product!.x);
    expect(positions.product!.x).toBe(positions.sales!.x);
    expect(positions.product!.y).not.toBe(positions.sales!.y);
  });

  it.each(["vertical", "horizontal"] as const)(
    "lays out collapsed nodes in a deterministic, balanced, collision-free %s complete tree",
    (orientation) => {
      const collapsedNodeIds = new Set(["root", "a", "b"]);
      const first = organizationTreeToLayoutPositions(
        unevenOrganizations,
        orientation,
        new Set(),
        collapsedNodeIds,
        true
      );
      const second = organizationTreeToLayoutPositions(
        unevenOrganizations,
        orientation,
        new Set(),
        collapsedNodeIds,
        true
      );
      const crossAxis = orientation === "vertical" ? "x" : "y";
      const depthAxis = orientation === "vertical" ? "y" : "x";

      expect(Object.keys(first).sort()).toEqual(
        ["root", "a", "a1", "a2", "a3", "b", "b1", "b1-deep"].sort()
      );
      expect(first).toEqual(second);
      expect(
        new Set(Object.values(first).map(({ x, y }) => `${x}:${y}`)).size
      ).toBe(Object.keys(first).length);
      expect(first.root![crossAxis]).toBe(
        (first.a![crossAxis] + first.b![crossAxis]) / 2
      );
      expect(first.root![depthAxis]).toBeLessThan(first.a![depthAxis]);
      expect(first.a![depthAxis]).toBeLessThan(first.a1![depthAxis]);
      expect(first.b1![depthAxis]).toBeLessThan(
        first["b1-deep"]![depthAxis]
      );
    }
  );
});

describe("organization connection routing", () => {
  it("routes vertical edges from bottom to top", () => {
    const graph = organizationTreeToFlowGraph(
      organizations,
      organizationTreeToLayoutPositions(organizations, "vertical")
    );

    expect(graph.edges[0]).toEqual(
      expect.objectContaining({ sourceHandle: "bottom", targetHandle: "top" })
    );
    expect(graph.nodes[0]?.data.layoutOrientation).toBe("vertical");
  });

  it("routes horizontal edges from right to left", () => {
    const positions = organizationTreeToLayoutPositions(
      organizations,
      "horizontal"
    );
    const graph = organizationTreeToFlowGraph(
      organizations,
      positions,
      new Set(),
      undefined,
      "horizontal"
    );

    expect(graph.edges[0]).toEqual(
      expect.objectContaining({ sourceHandle: "right", targetHandle: "left" })
    );
    expect(graph.nodes[0]?.data.layoutOrientation).toBe("horizontal");
  });

  it("infers a reopened horizontal layout from saved coordinates", () => {
    const positions = organizationTreeToLayoutPositions(
      organizations,
      "horizontal"
    );

    expect(inferOrganizationLayoutOrientation(organizations, positions)).toBe(
      "horizontal"
    );
  });

  it("does not confuse wide vertical sibling spread with horizontal depth", () => {
    const positions = organizationTreeToLayoutPositions(
      wideOrganizations,
      "vertical"
    );

    expect(
      inferOrganizationLayoutOrientation(wideOrganizations, positions)
    ).toBe("vertical");
  });

  it("does not confuse tall horizontal sibling spread with vertical depth", () => {
    const positions = organizationTreeToLayoutPositions(
      wideOrganizations,
      "horizontal"
    );

    expect(
      inferOrganizationLayoutOrientation(wideOrganizations, positions)
    ).toBe("horizontal");
  });
});

describe("repositionOrganizationSubtree", () => {
  const moveTree: OrganizationTreeNode[] = [
    {
      id: "root",
      name: "Root",
      path: "root/",
      parent_id: null,
      children: [
        {
          id: "moved",
          name: "Moved",
          path: "root/moved/",
          parent_id: "root",
          children: [
            {
              id: "descendant",
              name: "Descendant",
              path: "root/moved/descendant/",
              parent_id: "moved",
              children: [],
            },
          ],
        },
        {
          id: "parent",
          name: "New parent",
          path: "root/parent/",
          parent_id: "root",
          children: [
            {
              id: "occupied",
              name: "Occupied slot",
              path: "root/parent/occupied/",
              parent_id: "parent",
              children: [],
            },
          ],
        },
      ],
    },
  ];
  const movePositions = {
    root: { x: 0, y: 0 },
    moved: { x: -800, y: 180 },
    descendant: { x: -800, y: 360 },
    parent: { x: 400, y: 180 },
    occupied: { x: 400, y: 360 },
  };

  it("places a vertical moved subtree in the nearest free child slot", () => {
    const movedPositions = repositionOrganizationSubtree(
      moveTree,
      movePositions,
      "moved",
      "parent",
      "vertical"
    );

    expect(movedPositions).toEqual({
      moved: { x: 680, y: 360 },
      descendant: { x: 680, y: 540 },
    });
  });

  it("places a horizontal moved subtree in the nearest free child slot", () => {
    const movedPositions = repositionOrganizationSubtree(
      moveTree,
      {
        root: { x: 0, y: 0 },
        moved: { x: 360, y: -500 },
        descendant: { x: 720, y: -500 },
        parent: { x: 360, y: 300 },
        occupied: { x: 720, y: 300 },
      },
      "moved",
      "parent",
      "horizontal"
    );

    expect(movedPositions).toEqual({
      moved: { x: 720, y: 480 },
      descendant: { x: 1080, y: 480 },
    });
  });
});
