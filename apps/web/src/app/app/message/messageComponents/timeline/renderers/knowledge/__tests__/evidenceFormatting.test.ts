import {
  documentDisplay,
  EMPTY_VALUE,
  formatPropertyValue,
  groupSources,
  scoreRatio,
  visibleProperties,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/evidenceFormatting";
import type { EvidenceChunk } from "@/lib/api/domains/chat/knowledge-evidence-types";

function chunk(
  ref: number,
  document: string | null,
  title: string | null = null
): EvidenceChunk {
  return {
    ref,
    id: null,
    score: 0.8,
    content: "x",
    truncated: false,
    collectionId: null,
    source: { document, title, page: null, section: null, fileId: null },
  };
}

describe("documentDisplay", () => {
  it("splits a file name into a readable name and its type", () => {
    expect(
      documentDisplay(chunk(1, "İzin Yönetmeliği 2026.pdf").source)
    ).toEqual({
      name: "İzin Yönetmeliği 2026",
      extension: "PDF",
    });
  });

  it("falls back to the title, then to nothing", () => {
    expect(documentDisplay(chunk(1, null, "Süreç El Kitabı").source)).toEqual({
      name: "Süreç El Kitabı",
      extension: null,
    });
    expect(documentDisplay(chunk(1, null).source)).toEqual({
      name: null,
      extension: null,
    });
  });
});

describe("groupSources", () => {
  it("counts chunks per document in first-seen order", () => {
    expect(
      groupSources([
        chunk(1, "a.pdf"),
        chunk(2, "b.docx"),
        chunk(3, "a.pdf"),
        chunk(4, null),
      ])
    ).toEqual([
      { name: "a", extension: "PDF", count: 2 },
      { name: "b", extension: "DOCX", count: 1 },
    ]);
  });
});

describe("scoreRatio", () => {
  it("clamps scores into a 0..1 bar width", () => {
    expect(scoreRatio(0.89)).toBe(0.89);
    expect(scoreRatio(1.4)).toBe(1);
    expect(scoreRatio(-0.2)).toBe(0);
    expect(scoreRatio(null)).toBe(0);
  });
});

describe("formatPropertyValue", () => {
  it("shows a dash for an empty property and text for the rest", () => {
    expect(formatPropertyValue(null)).toBe(EMPTY_VALUE);
    expect(formatPropertyValue(false)).toBe("false");
    expect(formatPropertyValue(0)).toBe("0");
    expect(formatPropertyValue("15 Aralık")).toBe("15 Aralık");
  });
});

describe("visibleProperties", () => {
  it("leaves out the ranking scores the details show as the match score", () => {
    expect(
      visibleProperties({ owner: "İK", rrf_score: 0.1, bm25_score: 2 })
    ).toEqual([["owner", "İK"]]);
  });
});
