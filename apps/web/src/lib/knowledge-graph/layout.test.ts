import { computeGraphLayout } from "@/lib/knowledge-graph/layout";
import type { EvidenceGraph } from "@/lib/api/domains/chat/knowledge-evidence-types";

function graph(nodeCount: number): EvidenceGraph {
  const nodes = Array.from({ length: nodeCount }, (_, index) => ({
    id: `n${index}`,
    name: `Entity ${index}`,
    label: "Process",
    matched: index === 0,
    score: null,
    properties: {},
  }));
  return {
    nodes,
    edges: nodes.slice(1).map((node) => ({
      id: null,
      source: "n0",
      target: node.id,
      type: "RELATES_TO",
      properties: {},
    })),
  };
}

const VIEWPORT = { width: 560, height: 330, padding: 48 };

describe("computeGraphLayout", () => {
  it("places every node inside the padded viewport", () => {
    const layout = computeGraphLayout(graph(8), VIEWPORT);

    expect(layout.size).toBe(8);
    for (const point of Array.from(layout.values())) {
      expect(point.x).toBeGreaterThanOrEqual(VIEWPORT.padding);
      expect(point.x).toBeLessThanOrEqual(VIEWPORT.width - VIEWPORT.padding);
      expect(point.y).toBeGreaterThanOrEqual(VIEWPORT.padding);
      expect(point.y).toBeLessThanOrEqual(VIEWPORT.height - VIEWPORT.padding);
    }
  });

  it("is deterministic, so a reload draws the same picture", () => {
    const first = Array.from(computeGraphLayout(graph(6), VIEWPORT).entries());
    const second = Array.from(computeGraphLayout(graph(6), VIEWPORT).entries());

    expect(first).toHaveLength(6);
    expect(first).toEqual(second);
  });

  it("centres a single entity", () => {
    const point = computeGraphLayout(graph(1), VIEWPORT).get("n0");
    expect(point).toEqual({ x: 280, y: 165 });
  });

  it("keeps many disconnected clusters from collapsing into specks", () => {
    // 30 small stars (4 entities each): unrelated components used to repel
    // each other with nothing pulling them back, so fitting that spread into
    // the viewport left neighbors a few units apart.
    const nodes = Array.from({ length: 120 }, (_, index) => ({
      id: `c${index}`,
    }));
    const edges = nodes
      .filter((_, index) => index % 4 !== 0)
      .map((node, index) => ({
        source: `c${Math.floor(Number(node.id.slice(1)) / 4) * 4}`,
        target: node.id,
        key: index,
      }));
    const layout = computeGraphLayout(
      { nodes, edges },
      { width: 720, height: 560, padding: 56 }
    );
    const points = Array.from(layout.values());
    const nearest = points.map((a) =>
      Math.min(
        ...points
          .filter((b) => b !== a)
          .map((b) => Math.hypot(a.x - b.x, a.y - b.y))
      )
    );

    // A matched node is 22 units wide; neighbors must not overlap.
    expect(Math.min(...nearest)).toBeGreaterThan(22);
  });

  it("keeps connected entities apart", () => {
    const layout = computeGraphLayout(graph(2), VIEWPORT);
    const a = layout.get("n0")!;
    const b = layout.get("n1")!;
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(60);
  });
});
