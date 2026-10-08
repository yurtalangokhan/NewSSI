import {
  GLOW_TOP_RANKS,
  forceNodeRadius,
  glowByRank,
  glowStyle,
  rankedMatches,
  neighborIds,
  toForceGraphData,
} from "@/lib/knowledge-graph/forceGraphModel";
import type { SourceGraph } from "@/lib/knowledge-graph/forceGraphModel";

const searchGraph: SourceGraph = {
  nodes: [
    {
      id: "n1",
      name: "Veri Saklama Politikası",
      label: "Policy",
      matched: true,
      score: 0.03,
    },
    {
      id: "n2",
      name: "Veri Koruma Sorumlusu",
      label: "Role",
      matched: false,
      score: null,
    },
  ],
  edges: [{ id: "e1", source: "n1", target: "n2", type: "SORUMLUSU" }],
};

describe("toForceGraphData", () => {
  it("keeps the source node and sizes nodes by their degree", () => {
    const data = toForceGraphData(searchGraph);

    expect(data.nodes.map((node) => [node.id, node.degree])).toEqual([
      ["n1", 1],
      ["n2", 1],
    ]);
    expect(data.nodes[0]!.node).toBe(searchGraph.nodes[0]);
    expect(data.nodes[0]!.radius).toBe(forceNodeRadius(true, 1));
    expect(data.links).toEqual([
      { id: "e1", source: "n1", target: "n2", type: "SORUMLUSU" },
    ]);
  });

  it("returns fresh objects the simulation may mutate", () => {
    const first = toForceGraphData(searchGraph);
    const second = toForceGraphData(searchGraph);

    expect(first.nodes[0]).not.toBe(second.nodes[0]);
    expect(first.links[0]).not.toBe(second.links[0]);
  });
});

describe("forceNodeRadius", () => {
  it("draws hubs and matched entities larger, with a capped bonus", () => {
    expect(forceNodeRadius(true, 0)).toBeGreaterThan(forceNodeRadius(false, 0));
    expect(forceNodeRadius(false, 9)).toBeGreaterThan(
      forceNodeRadius(false, 1)
    );
    expect(forceNodeRadius(false, 10_000)).toBe(forceNodeRadius(false, 100));
  });
});

describe("neighborIds", () => {
  it("collects both directions and nothing without a selection", () => {
    expect(Array.from(neighborIds(searchGraph, "n2"))).toEqual(["n1"]);
    expect(neighborIds(searchGraph, null).size).toBe(0);
  });
});

describe("glowByRank", () => {
  const node = (id: string, matched: boolean, score: number | null) => ({
    id,
    name: id,
    label: "Agent",
    matched,
    score,
    collectionId: "kg",
    properties: {},
  });

  it("glows the top RRF-ranked matches, brightest first", () => {
    const glow = glowByRank([
      node("third", true, 0.0095),
      node("first", true, 0.0098),
      node("neighbor", false, null),
      node("second", true, 0.0097),
    ]);

    expect(Array.from(glow.keys())).toEqual(["first", "second", "third"]);
    expect(glow.get("first")!).toBeGreaterThan(glow.get("second")!);
    expect(glow.get("second")!).toBeGreaterThan(glow.get("third")!);
    expect(glow.has("neighbor")).toBe(false);
  });

  it("stops after the top ranks", () => {
    const nodes = Array.from({ length: GLOW_TOP_RANKS + 5 }, (_, index) =>
      node(`n${index}`, true, 1 - index / 100)
    );

    expect(glowByRank(nodes).size).toBe(GLOW_TOP_RANKS);
  });
});

describe("rankedMatches", () => {
  it("orders direct matches by RRF score and leaves neighbors out", () => {
    const ranked = rankedMatches([
      { id: "low", name: "low", label: "Agent", matched: true, score: 0.001 },
      { id: "near", name: "near", label: "Agent", matched: false, score: null },
      { id: "top", name: "top", label: "Agent", matched: true, score: 0.0098 },
      { id: "unscored", name: "u", label: "Agent", matched: true, score: null },
    ]);

    expect(ranked.map((node) => node.id)).toEqual(["top", "low", "unscored"]);
  });
});

describe("glowStyle", () => {
  it("grows brighter, wider, and larger with intensity", () => {
    const dim = glowStyle(0);
    const bright = glowStyle(1);

    expect(bright.alpha).toBeGreaterThan(dim.alpha);
    expect(bright.blur).toBeGreaterThan(dim.blur);
    expect(bright.haloExtra).toBeGreaterThan(dim.haloExtra);
  });

  it("keeps the halo translucent at full intensity", () => {
    expect(glowStyle(1).alpha).toBeLessThanOrEqual(1);
    expect(glowStyle(0).alpha).toBeGreaterThan(0);
  });
});
