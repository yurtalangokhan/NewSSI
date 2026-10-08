import {
  MAX_EXPANSION_NODES,
  entityLabelCounts,
  entityLabelGraph,
  inducedSubgraph,
  matchedNodesByCollection,
  matchedOnlyGraph,
  mergeKnowledgeGraphs,
  nodeFromEntityHit,
  relationsOf,
} from "@/sections/knowledge-search/model/graphModel";
import {
  documentHit,
  entityHit,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";
import type {
  KnowledgeGraph,
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

function node(
  id: string,
  matched = false,
  label = "Policy"
): KnowledgeGraphNode {
  return {
    id,
    name: id.toUpperCase(),
    label,
    matched,
    score: matched ? 0.02 : null,
    collectionId: "kg",
    properties: {},
  };
}

function edge(
  source: string,
  target: string,
  type = "RELATES",
  id: string | null = `${source}-${target}-${type}`
): KnowledgeGraphEdge {
  return { id, source, target, type, collectionId: "kg", properties: {} };
}

const BASE: KnowledgeGraph = {
  nodes: [node("a", true), node("b"), node("c", true, "Role")],
  edges: [edge("a", "b"), edge("b", "c", "OWNS"), edge("a", "c")],
};

describe("mergeKnowledgeGraphs", () => {
  it("adds new nodes and edges without duplicating existing ones", () => {
    const merged = mergeKnowledgeGraphs(BASE, {
      nodes: [node("b", true), node("d")],
      edges: [edge("a", "b"), edge("b", "d", "HAS"), edge("d", "ghost")],
    });

    expect(merged.nodes.map((item) => item.id)).toEqual(["a", "b", "c", "d"]);
    expect(merged.nodes[1]!.matched).toBe(true);
    expect(merged.edges.map((item) => item.id)).toEqual([
      "a-b-RELATES",
      "b-c-OWNS",
      "a-c-RELATES",
      "b-d-HAS",
    ]);
  });

  it("deduplicates id-less edges by endpoints and type", () => {
    const merged = mergeKnowledgeGraphs(
      { nodes: [node("a"), node("b")], edges: [edge("a", "b", "R", null)] },
      { nodes: [], edges: [edge("a", "b", "R", null)] }
    );

    expect(merged.edges).toHaveLength(1);
  });
});

describe("matchedOnlyGraph", () => {
  it("keeps matched nodes and the edges between them", () => {
    const graph = matchedOnlyGraph(BASE);

    expect(graph.nodes.map((item) => item.id)).toEqual(["a", "c"]);
    expect(graph.edges.map((item) => item.id)).toEqual(["a-c-RELATES"]);
  });
});

describe("entityLabelGraph", () => {
  it("keeps nodes of the chosen labels, case-insensitively, and their edges", () => {
    const graph = entityLabelGraph(BASE, ["policy"]);

    expect(graph.nodes.map((item) => item.id)).toEqual(["a", "b"]);
    expect(graph.edges.map((item) => item.id)).toEqual(["a-b-RELATES"]);
  });

  it("leaves the graph untouched without a label choice", () => {
    expect(entityLabelGraph(BASE, [])).toBe(BASE);
  });
});

describe("relationsOf", () => {
  it("lists a node's relations with the other endpoint and direction", () => {
    const relations = relationsOf(BASE, "b");

    expect(
      relations.map((relation) => [
        relation.type,
        relation.direction,
        relation.other.id,
      ])
    ).toEqual([
      ["RELATES", "in", "a"],
      ["OWNS", "out", "c"],
    ]);
  });
});

describe("entityLabelCounts", () => {
  it("counts node labels, most frequent first", () => {
    expect(entityLabelCounts(BASE)).toEqual([
      { value: "Policy", count: 2 },
      { value: "Role", count: 1 },
    ]);
  });
});

describe("matchedNodesByCollection", () => {
  it("groups matched node ids per collection, capped per group", () => {
    const many = Array.from({ length: MAX_EXPANSION_NODES + 3 }, (_, i) => ({
      ...node(`m${i}`, true),
      collectionId: "big",
    }));
    const graph: KnowledgeGraph = {
      nodes: [...BASE.nodes, ...many],
      edges: [],
    };

    const groups = matchedNodesByCollection(graph);

    expect(groups).toEqual([
      { collectionId: "kg", nodeIds: ["a", "c"] },
      {
        collectionId: "big",
        nodeIds: many.slice(0, MAX_EXPANSION_NODES).map((item) => item.id),
      },
    ]);
  });
});

describe("inducedSubgraph", () => {
  it("keeps the nodes the predicate accepts and only the edges between them", () => {
    const graph = inducedSubgraph(BASE, (item) => item.id !== "b");

    expect(graph.nodes.map((item) => item.id)).toEqual(["a", "c"]);
    expect(graph.edges.map((item) => item.id)).toEqual(["a-c-RELATES"]);
  });

  it("drops every edge when no node is kept", () => {
    expect(inducedSubgraph(BASE, () => false)).toEqual({
      nodes: [],
      edges: [],
    });
  });
});

describe("nodeFromEntityHit", () => {
  it("builds the graph node from the hit's entity", () => {
    expect(nodeFromEntityHit(entityHit)).toEqual({
      id: "n1",
      name: "Veri Saklama Politikası",
      label: "Policy",
      matched: true,
      score: 0.03,
      collectionId: "kg",
      properties: { sürüm: "v3" },
    });
  });

  it("returns nothing for a document hit", () => {
    expect(nodeFromEntityHit(documentHit)).toBeUndefined();
  });
});
