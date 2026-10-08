import type { EvidenceGraph } from "@/lib/api/domains/chat/knowledge-evidence-types";
import {
  edgeKey,
  focusedNodeId,
  highlightFor,
  keyedEdges,
  relationCount,
  touchesNode,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/graphSelection";

const graph: EvidenceGraph = {
  nodes: [
    {
      id: "a",
      name: "A",
      label: "Process",
      matched: true,
      score: 0.5,
      properties: {},
    },
    {
      id: "b",
      name: "B",
      label: "Role",
      matched: false,
      score: null,
      properties: {},
    },
    {
      id: "c",
      name: "C",
      label: "Department",
      matched: false,
      score: null,
      properties: {},
    },
  ],
  edges: [
    { id: "e1", source: "a", target: "b", type: "REQUIRES", properties: {} },
    { id: null, source: "a", target: "c", type: "OWNED_BY", properties: {} },
    { id: null, source: "b", target: "c", type: "BELONGS_TO", properties: {} },
  ],
};

describe("edgeKey", () => {
  it("prefers the edge id and falls back to its endpoints and position", () => {
    expect(edgeKey(graph.edges[0]!, 0)).toBe("e1");
    expect(edgeKey(graph.edges[1]!, 1)).toBe("a->c#1");
  });
});

describe("touchesNode", () => {
  it("matches an edge on either end", () => {
    expect(touchesNode(graph.edges[0]!, "a")).toBe(true);
    expect(touchesNode(graph.edges[0]!, "b")).toBe(true);
    expect(touchesNode(graph.edges[0]!, "c")).toBe(false);
  });
});

describe("keyedEdges", () => {
  it("keys every edge by its position in the whole graph", () => {
    expect(keyedEdges(graph).map((row) => row.key)).toEqual([
      "e1",
      "a->c#1",
      "b->c#2",
    ]);
  });

  it("keeps whole-graph keys when narrowing to one entity", () => {
    expect(keyedEdges(graph, "c").map((row) => row.key)).toEqual([
      "a->c#1",
      "b->c#2",
    ]);
  });

  it("treats a null entity as no filter", () => {
    expect(keyedEdges(graph, null)).toHaveLength(3);
  });
});

describe("relationCount", () => {
  it("counts the edges touching an entity", () => {
    expect(relationCount(graph, "a")).toBe(2);
    expect(relationCount(graph, "c")).toBe(2);
    expect(relationCount(graph, "missing")).toBe(0);
  });
});

describe("highlightFor", () => {
  it("is null when nothing is picked", () => {
    expect(highlightFor(graph, null)).toBeNull();
  });

  it("emphasises an entity, its edges, and their other ends", () => {
    const highlight = highlightFor(graph, { kind: "node", id: "b" })!;
    expect(Array.from(highlight.nodes).sort()).toEqual(["a", "b", "c"]);
    expect(Array.from(highlight.edges).sort()).toEqual(["b->c#2", "e1"]);
  });

  it("keeps an isolated picked entity emphasised", () => {
    const highlight = highlightFor(graph, { kind: "node", id: "zzz" })!;
    expect(Array.from(highlight.nodes)).toEqual(["zzz"]);
    expect(highlight.edges.size).toBe(0);
  });

  it("emphasises one relation and its two ends", () => {
    const highlight = highlightFor(graph, { kind: "edge", key: "a->c#1" })!;
    expect(Array.from(highlight.edges)).toEqual(["a->c#1"]);
    expect(Array.from(highlight.nodes).sort()).toEqual(["a", "c"]);
  });
});

describe("focusedNodeId", () => {
  it("is null without a selection", () => {
    expect(focusedNodeId(graph, null)).toBeNull();
  });

  it("is the picked entity", () => {
    expect(focusedNodeId(graph, { kind: "node", id: "c" })).toBe("c");
  });

  it("is the source entity of a picked relation", () => {
    expect(focusedNodeId(graph, { kind: "edge", key: "b->c#2" })).toBe("b");
    expect(focusedNodeId(graph, { kind: "edge", key: "e1" })).toBe("a");
  });

  it("is null when the picked relation no longer exists", () => {
    expect(focusedNodeId(graph, { kind: "edge", key: "gone" })).toBeNull();
  });
});
