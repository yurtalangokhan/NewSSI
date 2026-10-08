import type { RagChunk } from "@/lib/api/domains/knowledge/types";
import type { KnowledgeGraph } from "@/lib/api/domains/knowledge/knowledge-search-types";

/** Index of the hit's passage among loaded chunks, or -1 when not loaded. */
export function findChunkIndex(
  chunks: readonly RagChunk[],
  chunkId: string,
  content: string
): number {
  const byId = chunks.findIndex((chunk) => chunk.id === chunkId);
  if (byId >= 0) return byId;
  return chunks.findIndex((chunk) => chunk.content === content);
}

/** The passages right before and after the one at `index`. */
export function surroundingChunks(
  chunks: readonly RagChunk[],
  index: number
): { previous: RagChunk | null; next: RagChunk | null } {
  if (index < 0) return { previous: null, next: null };
  return {
    previous: chunks[index - 1] ?? null,
    next: chunks[index + 1] ?? null,
  };
}

/** A node with its direct neighbors and the edges among them. */
export function egoGraph(
  graph: KnowledgeGraph,
  nodeId: string
): KnowledgeGraph {
  if (!graph.nodes.some((node) => node.id === nodeId)) {
    return { nodes: [], edges: [] };
  }
  const kept = new Set([nodeId]);
  for (const edge of graph.edges) {
    if (edge.source === nodeId) kept.add(edge.target);
    if (edge.target === nodeId) kept.add(edge.source);
  }
  return {
    nodes: graph.nodes.filter((node) => kept.has(node.id)),
    edges: graph.edges.filter(
      (edge) =>
        (edge.source === nodeId || edge.target === nodeId) &&
        kept.has(edge.source) &&
        kept.has(edge.target)
    ),
  };
}
