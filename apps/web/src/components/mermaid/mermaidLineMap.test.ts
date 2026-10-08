import { mapPreprocessedLine } from "@/components/mermaid/mermaidLineMap";

describe("mapPreprocessedLine", () => {
  it("is the identity for a plain diagram", () => {
    expect(mapPreprocessedLine("flowchart\nA-->B\nB-->C", 3)).toBe(3);
  });

  it("skips front matter", () => {
    const source = "---\ntitle: t\nconfig:\n  x: 1\n---\nflowchart\nA-->B";
    expect(mapPreprocessedLine(source, 1)).toBe(6);
    expect(mapPreprocessedLine(source, 2)).toBe(7);
  });

  it("skips leading blank lines and whole-line %% comments", () => {
    const source = "\n\n%% one\nflowchart\n  %% two\nA-->B\n%% three\nC-->D";
    expect(mapPreprocessedLine(source, 1)).toBe(4);
    expect(mapPreprocessedLine(source, 2)).toBe(6);
    expect(mapPreprocessedLine(source, 3)).toBe(8);
  });

  it("skips a multi-line init directive", () => {
    const source = '%%{init: {\n"theme": "dark"\n}}%%\nflowchart\nA-->B';
    expect(mapPreprocessedLine(source, 1)).toBe(4);
    expect(mapPreprocessedLine(source, 2)).toBe(5);
  });

  it("handles CRLF line endings", () => {
    expect(mapPreprocessedLine("%% c\r\nflowchart\r\nA-->B", 2)).toBe(3);
  });

  it("returns a line outside the text unchanged", () => {
    expect(mapPreprocessedLine("flowchart\nA-->B", 9)).toBe(9);
  });
});
