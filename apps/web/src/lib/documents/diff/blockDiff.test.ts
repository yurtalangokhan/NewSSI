import { MAX_DIFF_CHARS, blockDiff } from "@/lib/documents/diff/blockDiff";

const statuses = (before: string, after: string) => {
  const result = blockDiff(before, after);
  if (result.tooLarge) throw new Error("unexpected tooLarge");
  return result.entries.map(
    (e) => `${e.status}:${(e.after ?? e.before)!.type}`
  );
};

describe("blockDiff", () => {
  it("does not hide a change whose hash collides with the old block", () => {
    // Real FNV-1a 32-bit collision (594f30f6): only the source tells them apart.
    expect(statuses("# A\n\nw673879", "# A\n\nw1180600")).toEqual([
      "unchanged:heading",
      "modified:paragraph",
    ]);
  });

  it("sees an added or removed hard break", () => {
    expect(statuses("line one\nline two", "line one  \nline two")).toEqual([
      "modified:paragraph",
    ]);
  });

  it("marks identical documents unchanged", () => {
    expect(statuses("# A\n\ntext", "# A\n\ntext")).toEqual([
      "unchanged:heading",
      "unchanged:paragraph",
    ]);
  });

  it("pairs a changed block of the same type as modified", () => {
    expect(statuses("# A\n\nold text", "# A\n\nnew text")).toEqual([
      "unchanged:heading",
      "modified:paragraph",
    ]);
  });

  it("reports an appended section as added", () => {
    expect(statuses("# A\n\ntext", "# A\n\ntext\n\n## B\n\nmore")).toEqual([
      "unchanged:heading",
      "unchanged:paragraph",
      "added:heading",
      "added:paragraph",
    ]);
  });

  it("does not pair blocks of different types", () => {
    expect(statuses("# A\n\ntext", "# A\n\n- item")).toEqual([
      "unchanged:heading",
      "removed:paragraph",
      "added:list",
    ]);
  });

  it("summarizes the entries", () => {
    const result = blockDiff("# A\n\nx\n\ny", "# A\n\nz\n\ny\n\nw");
    if (result.tooLarge) throw new Error("unexpected");
    expect(result.summary).toEqual({
      added: 1,
      removed: 0,
      modified: 1,
      unchanged: 2,
    });
  });

  it("refuses inputs over the size cap", () => {
    const huge = "x".repeat(MAX_DIFF_CHARS + 1);
    expect(blockDiff(huge, "x")).toEqual({ tooLarge: true });
  });
});
