import {
  egoGraph,
  findChunkIndex,
  surroundingChunks,
} from "@/sections/knowledge-search/model/documentChunks";
import type { RagChunk } from "@/lib/api/domains/knowledge/types";
import type { KnowledgeGraph } from "@/lib/api/domains/knowledge/knowledge-search-types";

const CHUNKS: RagChunk[] = [
  { id: "a", content: "first" },
  { id: "b", content: "second" },
  { id: "c", content: "third" },
];

describe("findChunkIndex", () => {
  it("finds the passage by id, then by identical content", () => {
    expect(findChunkIndex(CHUNKS, "c", "whatever")).toBe(2);
    expect(findChunkIndex(CHUNKS, "unknown", "second")).toBe(1);
    expect(findChunkIndex(CHUNKS, "unknown", "missing")).toBe(-1);
  });
});

describe("surroundingChunks", () => {
  it("returns the neighbors of a passage", () => {
    expect(surroundingChunks(CHUNKS, 1)).toEqual({
      previous: CHUNKS[0],
      next: CHUNKS[2],
    });
    expect(surroundingChunks(CHUNKS, 0)).toEqual({
      previous: null,
      next: CHUNKS[1],
    });
    expect(surroundingChunks(CHUNKS, -1)).toEqual({
      previous: null,
      next: null,
    });
  });
});

describe("egoGraph", () => {
  const graph: KnowledgeGraph = {
    nodes: ["a", "b", "c", "d"].map((id) => ({
      id,
      name: id,
      label: "L",
      matched: id === "a",
      score: null,
      collectionId: "kg",
      properties: {},
    })),
    edges: [
      {
        id: "ab",
        source: "a",
        target: "b",
        type: "R",
        collectionId: "kg",
        properties: {},
      },
      {
        id: "bc",
        source: "b",
        target: "c",
        type: "R",
        collectionId: "kg",
        properties: {},
      },
      {
        id: "da",
        source: "d",
        target: "a",
        type: "R",
        collectionId: "kg",
        properties: {},
      },
    ],
  };

  it("keeps the node, its neighbors, and the edges among them", () => {
    const ego = egoGraph(graph, "a");

    expect(ego.nodes.map((node) => node.id)).toEqual(["a", "b", "d"]);
    expect(ego.edges.map((edge) => edge.id)).toEqual(["ab", "da"]);
  });

  it("is empty for an unknown node", () => {
    expect(egoGraph(graph, "zzz")).toEqual({ nodes: [], edges: [] });
  });
});
