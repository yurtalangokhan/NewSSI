import {
  SEARCH_RESULT_LIMITS,
  type KnowledgeDocumentHit,
  type KnowledgeSearchHit,
  type KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

const EXTENSION = /\.[a-z0-9]{1,10}$/i;

export function visibleHits(
  hits: readonly KnowledgeSearchHit[],
  visibleCount: number
): readonly KnowledgeSearchHit[] {
  return hits.slice(0, visibleCount);
}

/** The next larger result limit, or `null` at the largest one. */
export function nextLimit(limit: number): number | null {
  return SEARCH_RESULT_LIMITS.find((candidate) => candidate > limit) ?? null;
}

/**
 * What "show more" does: reveal already loaded hits, or fetch with a larger
 * limit once every loaded hit is visible and the backend reports more.
 */
export function showMoreAction(
  response: KnowledgeSearchResponse,
  visibleCount: number,
  limit: number
): "reveal" | "raiseLimit" | null {
  if (visibleCount < response.hits.length) return "reveal";
  if (response.total > response.hits.length && nextLimit(limit) !== null) {
    return "raiseLimit";
  }
  return null;
}

/** Results beyond the visible ones, for the "show more" label. */
export function remainingCount(
  response: KnowledgeSearchResponse,
  visibleCount: number
): number {
  return Math.max(
    0,
    response.total - Math.min(visibleCount, response.hits.length)
  );
}

/** Collections that returned at least one hit. */
export function hitCollections(
  response: KnowledgeSearchResponse
): readonly KnowledgeSearchResponse["collections"][number][] {
  return response.collections.filter(
    (collection) => collection.documentHits + collection.entityHits > 0
  );
}

/**
 * Unfiltered hit totals across the searched collections. `collections` counts
 * the ones that actually returned hits, so the summary matches the collection
 * list, which hides empty sources.
 */
export function hitCounts(response: KnowledgeSearchResponse): {
  documents: number;
  entities: number;
  collections: number;
} {
  return response.collections.reduce(
    (counts, collection) => ({
      documents: counts.documents + collection.documentHits,
      entities: counts.entities + collection.entityHits,
      collections:
        counts.collections +
        (collection.documentHits + collection.entityHits > 0 ? 1 : 0),
    }),
    { documents: 0, entities: 0, collections: 0 }
  );
}

/** A document as a person reads it: its title, else its file name. */
export function documentTitle(document: KnowledgeDocumentHit): string | null {
  if (document.title) return document.title;
  if (!document.source) return null;
  return document.source.replace(EXTENSION, "") || document.source;
}
