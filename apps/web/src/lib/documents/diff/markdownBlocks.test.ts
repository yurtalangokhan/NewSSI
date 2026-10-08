import {
  blocksEqual,
  hashBlock,
  parseBlocks,
} from "@/lib/documents/diff/markdownBlocks";

const DOC = [
  "# Tedarikçi Onboarding Süreci",
  "",
  "Bu doküman adımları tanımlar.",
  "",
  "```mermaid",
  "flowchart LR",
  "  A --> B",
  "```",
  "",
  "| Adım | Süre |",
  "|---|---|",
  "| Belge | 3 gün |",
  "",
  "- bir",
  "- iki",
].join("\n");

describe("parseBlocks", () => {
  it("splits top-level blocks with types, sources and lines", () => {
    const blocks = parseBlocks(DOC);

    expect(blocks.map((b) => b.type)).toEqual([
      "heading",
      "paragraph",
      "mermaid",
      "table",
      "list",
    ]);
    expect(blocks[2]!.source).toBe("```mermaid\nflowchart LR\n  A --> B\n```");
    expect(blocks[3]).toMatchObject({ startLine: 10, endLine: 12 });
  });

  it("hashes equal blocks equally, ignoring insignificant trailing spaces", () => {
    expect(hashBlock("a \nb")).toBe(hashBlock("a\nb"));
    expect(hashBlock("a\nb  ")).toBe(hashBlock("a\nb"));
    expect(hashBlock("a")).not.toBe(hashBlock("b"));
  });

  it("keeps a Markdown hard break significant", () => {
    expect(hashBlock("a  \nb")).not.toBe(hashBlock("a\nb"));
    expect(hashBlock("a  \nb")).toBe(hashBlock("a    \nb"));
  });

  it("confirms a hash match against the source", () => {
    // Real FNV-1a 32-bit collision: both hash to 594f30f6.
    const [one, two] = ["w673879", "w1180600"].map(
      (text) => parseBlocks(text)[0]!
    );

    expect(one!.hash).toBe(two!.hash);
    expect(blocksEqual(one!, two!)).toBe(false);
    expect(blocksEqual(one!, parseBlocks("w673879  ")[0]!)).toBe(true);
  });

  it("returns no blocks for empty input", () => {
    expect(parseBlocks("")).toEqual([]);
  });
});
