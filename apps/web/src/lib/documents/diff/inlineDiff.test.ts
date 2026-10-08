import type { Table } from "mdast";
import { blockDiff } from "@/lib/documents/diff/blockDiff";
import {
  INLINE_DIFF_MAX_EDIT_LENGTH,
  describeModification,
  inlineDiff,
  tableDiff,
} from "@/lib/documents/diff/inlineDiff";
import { parseBlocks } from "@/lib/documents/diff/markdownBlocks";

const table = (md: string) => parseBlocks(md)[0]!.node as Table;

describe("inlineDiff", () => {
  it("marks inserted and deleted words and reconstructs both sides", () => {
    const before = "adımları tanımlar.";
    const after = "adımları ve birimleri tanımlar.";
    const segments = inlineDiff(before, after);

    const side = (skip: "ins" | "del") =>
      segments
        .filter((s) => s.kind !== skip)
        .map((s) => s.value)
        .join("");
    expect(side("del")).toBe(after);
    expect(side("ins")).toBe(before);
    expect(
      segments
        .filter((s) => s.kind === "ins")
        .map((s) => s.value.trim())
        .join(" ")
    ).toBe("ve birimleri");
    expect(segments.some((s) => s.kind === "del")).toBe(false);
  });
});

describe("inlineDiff cost limit", () => {
  it("gives up on a huge unrelated pair and shows old then new", () => {
    const before = "a ".repeat(INLINE_DIFF_MAX_EDIT_LENGTH * 2);
    const after = "b ".repeat(INLINE_DIFF_MAX_EDIT_LENGTH * 2);

    expect(inlineDiff(before, after)).toEqual([
      { kind: "del", value: before },
      { kind: "ins", value: after },
    ]);
  });

  it("falls back to replaced rows for an oversized table diff", () => {
    const rows = (word: string) =>
      Array.from(
        { length: INLINE_DIFF_MAX_EDIT_LENGTH + 10 },
        (_, i) => `| ${word}${i} |`
      ).join("\n");
    const before = table(`| H |\n|---|\n${rows("x")}`);
    const after = table(`| H |\n|---|\n${rows("y")}`);

    const diff = tableDiff(before, after);

    expect(diff.rows).toHaveLength(INLINE_DIFF_MAX_EDIT_LENGTH + 10);
    expect(diff.rows.every((row) => row.status === "modified")).toBe(true);
  });
});

describe("invisible source changes", () => {
  const modification = (before: string, after: string) => {
    const result = blockDiff(before, after);
    if (result.tooLarge) throw new Error("unexpected tooLarge");
    return describeModification(result.entries[0]!);
  };

  it("shows a link-only edit as a raw source pair", () => {
    expect(
      modification(
        "See [docs](https://a.example).",
        "See [docs](https://evil.example)."
      )
    ).toEqual({
      kind: "pair",
      before: "See [docs](https://a.example).",
      after: "See [docs](https://evil.example).",
    });
  });

  it("shows a bold-only edit as a raw source pair", () => {
    expect(modification("plain word", "**plain** word")).toMatchObject({
      kind: "pair",
      after: "**plain** word",
    });
  });

  it("keeps a text diff when words changed", () => {
    expect(modification("old word", "new word").kind).toBe("text");
  });

  it("marks a table cell whose link target changed", () => {
    const beforeMd = "| A |\n|---|\n| [x](https://a) |";
    const afterMd = "| A |\n|---|\n| [x](https://b) |";
    const result = blockDiff(beforeMd, afterMd);
    if (result.tooLarge) throw new Error("unexpected tooLarge");
    const mod = describeModification(result.entries[0]!);
    if (mod.kind !== "table") throw new Error("expected table");

    expect(mod.table.rows[0]!.status).toBe("modified");
    expect(mod.table.rows[0]!.cells[0]).toMatchObject({
      kind: "changed",
      before: "[x](https://a)",
      after: "[x](https://b)",
    });
  });
});

describe("tableDiff", () => {
  it("diffs cells and counts added rows", () => {
    const before = table(
      "| Adım | Süre |\n|---|---|\n| Belge | 3 gün |\n| Finans | 2 gün |"
    );
    const after = table(
      "| Adım | Süre |\n|---|---|\n| Belge | 2 gün |\n| Hukuk | 3 gün |\n| Finans | 2 gün |"
    );

    const diff = tableDiff(before, after);

    expect(diff.header.status).toBe("unchanged");
    expect(diff.rows.map((r) => r.status)).toEqual([
      "modified",
      "added",
      "unchanged",
    ]);
    expect(diff.rows[0]!.cells[1]).toMatchObject({
      kind: "changed",
      before: "3 gün",
      after: "2 gün",
    });
    expect(diff).toMatchObject({
      changedCells: 1,
      addedRows: 1,
      removedRows: 0,
    });
  });
});

describe("describeModification", () => {
  it("gives mermaid and code blocks as before/after pairs", () => {
    const result = blockDiff(
      "```mermaid\nflowchart LR\n  A-->B\n```",
      "```mermaid\nflowchart LR\n  A-->C\n```"
    );
    if (result.tooLarge) throw new Error("unexpected");
    const modification = describeModification(result.entries[0]!);

    expect(modification).toEqual({
      kind: "pair",
      before: "flowchart LR\n  A-->B",
      after: "flowchart LR\n  A-->C",
    });
  });

  it("gives paragraphs as inline text segments", () => {
    const result = blockDiff("old text", "new text");
    if (result.tooLarge) throw new Error("unexpected");
    expect(describeModification(result.entries[0]!).kind).toBe("text");
  });
});
