import {
  documentTitle,
  hitCollections,
  hitCounts,
  nextLimit,
  remainingCount,
  showMoreAction,
  visibleHits,
} from "@/sections/knowledge-search/model/resultsView";
import type {
  KnowledgeDocumentHit,
  KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

function response(
  hitCount: number,
  total: number,
  collections: KnowledgeSearchResponse["collections"] = []
): KnowledgeSearchResponse {
  return {
    query: "q",
    kind: "hybrid",
    elapsedMs: 5,
    total,
    graphAvailable: true,
    graphUnavailable: false,
    hits: Array.from({ length: hitCount }, (_, index) => ({
      id: `h${index}`,
      kind: "document" as const,
      relevance: 1,
      score: 1,
      collectionId: "c",
      collectionName: "C",
      document: null,
      entity: null,
    })),
    graph: { nodes: [], edges: [] },
    collections,
    facets: { fileTypes: [], entityLabels: [] },
  };
}

describe("visibleHits", () => {
  it("returns the first page of hits", () => {
    expect(visibleHits(response(25, 25).hits, 10)).toHaveLength(10);
    expect(visibleHits(response(4, 4).hits, 10)).toHaveLength(4);
  });
});

describe("nextLimit", () => {
  it("steps through the result limits", () => {
    expect(nextLimit(25)).toBe(50);
    expect(nextLimit(50)).toBe(100);
    expect(nextLimit(100)).toBeNull();
    expect(nextLimit(30)).toBe(50);
  });
});

describe("showMoreAction", () => {
  it("reveals loaded hits first", () => {
    expect(showMoreAction(response(25, 25), 10, 50)).toBe("reveal");
  });

  it("raises the limit when every loaded hit is visible but more exist", () => {
    expect(showMoreAction(response(50, 80), 50, 50)).toBe("raiseLimit");
  });

  it("has nothing more at the largest limit or when all are shown", () => {
    expect(showMoreAction(response(100, 140), 100, 100)).toBeNull();
    expect(showMoreAction(response(8, 8), 10, 50)).toBeNull();
  });
});

describe("remainingCount", () => {
  it("counts results beyond the visible ones", () => {
    expect(remainingCount(response(25, 32), 10)).toBe(22);
    expect(remainingCount(response(5, 5), 10)).toBe(0);
  });
});

describe("hitCounts", () => {
  it("sums unfiltered hits across collections", () => {
    const counts = hitCounts(
      response(0, 0, [
        { id: "a", name: "A", documentHits: 9, entityHits: 0, status: "ok" },
        { id: "b", name: "B", documentHits: 3, entityHits: 12, status: "ok" },
      ])
    );

    expect(counts).toEqual({ documents: 12, entities: 12, collections: 2 });
  });

  it("ignores collections that returned no hits", () => {
    const result = response(0, 0, [
      { id: "a", name: "A", documentHits: 9, entityHits: 0, status: "ok" },
      { id: "b", name: "B", documentHits: 0, entityHits: 0, status: "ok" },
    ]);

    expect(hitCounts(result).collections).toBe(1);
    expect(hitCollections(result).map((collection) => collection.id)).toEqual([
      "a",
    ]);
  });
});

describe("documentTitle", () => {
  const base: KnowledgeDocumentHit = {
    content: "",
    fileId: null,
    source: null,
    title: null,
    page: null,
    section: null,
    fileType: null,
    metadata: {},
  };

  it("prefers the title, then the file name without extension", () => {
    expect(documentTitle({ ...base, title: "Policy", source: "p.pdf" })).toBe(
      "Policy"
    );
    expect(documentTitle({ ...base, source: "Retention Policy v3.docx" })).toBe(
      "Retention Policy v3"
    );
    expect(documentTitle({ ...base, source: "README" })).toBe("README");
    expect(documentTitle(base)).toBeNull();
  });
});
