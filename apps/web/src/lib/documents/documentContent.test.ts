import {
  exportFormatsFor,
  fenceCode,
  revisionToMarkdown,
} from "@/lib/documents/documentContent";

describe("revisionToMarkdown", () => {
  it("keeps markdown as-is", () => {
    expect(
      revisionToMarkdown({ source_format: "markdown", content: "# A" })
    ).toBe("# A");
  });

  it("fences pretty JSON", () => {
    expect(
      revisionToMarkdown({ source_format: "json", content: '{"a":1}' })
    ).toBe('```json\n{\n  "a": 1\n}\n```');
  });

  it("turns sheets into one table per sheet with escaped pipes", () => {
    const content = JSON.stringify([
      {
        name: "SLA",
        rows: [
          ["Adım", "Süre"],
          ["A|B", 3],
        ],
      },
    ]);
    expect(revisionToMarkdown({ source_format: "sheets_json", content })).toBe(
      "## SLA\n\n| Adım | Süre |\n| --- | --- |\n| A\\|B | 3 |"
    );
  });

  it("uses object keys as the header for object rows", () => {
    const content = JSON.stringify([{ name: "S", rows: [{ a: 1, b: 2 }] }]);
    expect(revisionToMarkdown({ source_format: "sheets_json", content })).toBe(
      "## S\n\n| a | b |\n| --- | --- |\n| 1 | 2 |"
    );
  });

  it("keeps every cell of rows wider than the header", () => {
    const content = JSON.stringify([
      { name: "S", rows: [["a"], ["1", "2", "3"]] },
    ]);
    expect(revisionToMarkdown({ source_format: "sheets_json", content })).toBe(
      "## S\n\n| a |  |  |\n| --- | --- | --- |\n| 1 | 2 | 3 |"
    );
  });

  it("uses the union of keys across object rows", () => {
    const content = JSON.stringify([
      { name: "S", rows: [{ a: 1 }, { a: 2, b: 3 }, { c: 4 }] },
    ]);
    expect(revisionToMarkdown({ source_format: "sheets_json", content })).toBe(
      "## S\n\n| a | b | c |\n| --- | --- | --- |\n| 1 |  |  |\n| 2 | 3 |  |\n|  |  | 4 |"
    );
  });

  it("cannot be broken out of by backticks inside JSON content", () => {
    const content = JSON.stringify({ text: "```\n```mermaid\nA-->B\n```" });
    const out = revisionToMarkdown({ source_format: "json", content });

    expect(out.startsWith("````json\n")).toBe(true);
    expect(out.endsWith("\n````")).toBe(true);
  });

  it("falls back to a JSON fence for unreadable sheets", () => {
    expect(
      revisionToMarkdown({ source_format: "sheets_json", content: "not json" })
    ).toBe("```json\nnot json\n```");
  });
});

describe("fenceCode", () => {
  it("uses three backticks by default and outgrows the longest run in the body", () => {
    expect(fenceCode("json", "a")).toBe("```json\na\n```");
    expect(fenceCode("", "x ``` y")).toBe("````\nx ``` y\n````");
    expect(fenceCode("", "`````")).toBe("``````\n`````\n``````");
  });
});

describe("exportFormatsFor", () => {
  it("offers formats per kind", () => {
    expect(exportFormatsFor("document", "markdown")).toEqual([
      "docx",
      "pdf",
      "md",
      "txt",
    ]);
    expect(exportFormatsFor("document", "json")).toEqual(["json", "txt"]);
    expect(exportFormatsFor("spreadsheet", "sheets_json")).toEqual([
      "xlsx",
      "csv",
    ]);
  });
});
