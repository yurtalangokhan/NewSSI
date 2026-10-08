import {
  MERMAID_MAX_SOURCE_CHARS,
  detectDiagramType,
  hastToText,
  isFenceClosed,
  isMermaidClassName,
  resolveMermaidBlock,
  summarizePending,
  type HastCodeNode,
} from "@/components/mermaid/mermaidSource";

/** A hast `code` element as react-markdown hands it to the `code` override. */
function codeNode(
  markdown: string,
  body: string,
  closed: boolean
): HastCodeNode {
  const start = markdown.indexOf("```mermaid");
  const end = closed
    ? markdown.indexOf("\n```", start + 3) + 4
    : markdown.length;
  return {
    type: "element",
    children: [{ type: "text", value: `${body}\n` }],
    position: { start: { offset: start }, end: { offset: end } },
  };
}

describe("isFenceClosed", () => {
  it.each([
    ["closed backtick fence", "```mermaid\nflowchart LR\n```", true],
    [
      "closed fence with trailing spaces",
      "```mermaid\nflowchart LR\n```   \n",
      true,
    ],
    ["open fence", "```mermaid\nflowchart LR\n  A --> B", false],
    ["only the opening line", "```mermaid", false],
    ["half-typed closing fence", "```mermaid\nflowchart LR\n``", false],
    [
      "streaming cursor on the closing line",
      "```mermaid\nflowchart LR\n``` [*]()",
      false,
    ],
    ["tilde fence closed by tildes", "~~~mermaid\npie\n~~~", true],
    ["backtick fence is not closed by tildes", "```mermaid\npie\n~~~", false],
    [
      "a longer opening needs an equally long closing",
      "````mermaid\npie\n```",
      false,
    ],
    ["blockquote closing fence", "```mermaid\n> pie\n> ```", true],
  ])("%s", (_name, raw, expected) => {
    expect(isFenceClosed(raw)).toBe(expected);
  });
});

describe("resolveMermaidBlock", () => {
  it("keeps an open fence pending while streaming and strips the cursor", () => {
    const markdown = "Intro\n\n```mermaid\nflowchart LR\n  A --> B [*]() ";
    const node = codeNode(markdown, "flowchart LR\n  A --> B [*]() ", false);

    expect(resolveMermaidBlock({ markdown, node, isStreaming: true })).toEqual({
      source: "flowchart LR\n  A --> B",
      isComplete: false,
    });
  });

  it("is complete as soon as the fence closes, even mid-stream", () => {
    const markdown = "```mermaid\nflowchart LR\n  A --> B\n```\n\nMore [*]() ";
    const node = codeNode(markdown, "flowchart LR\n  A --> B", true);

    expect(resolveMermaidBlock({ markdown, node, isStreaming: true })).toEqual({
      source: "flowchart LR\n  A --> B",
      isComplete: true,
    });
  });

  it("treats an unclosed fence as complete once the message has stopped", () => {
    const markdown = "```mermaid\nflowchart LR\n  A --> B";
    const node = codeNode(markdown, "flowchart LR\n  A --> B", false);

    expect(resolveMermaidBlock({ markdown, node, isStreaming: false })).toEqual(
      {
        source: "flowchart LR\n  A --> B",
        isComplete: true,
      }
    );
  });

  it("stays pending without source positions while streaming", () => {
    const node: HastCodeNode = {
      children: [{ type: "text", value: "pie\n" }],
    };

    expect(
      resolveMermaidBlock({ markdown: "", node, isStreaming: true })
    ).toEqual({ source: "pie", isComplete: false });
  });
});

describe("hastToText", () => {
  it("joins nested text nodes", () => {
    expect(
      hastToText({ children: [{ value: "a" }, { children: [{ value: "b" }] }] })
    ).toBe("ab");
    expect(hastToText(undefined)).toBe("");
  });
});

describe("isMermaidClassName", () => {
  it("matches the language class even after rehype-highlight prefixes hljs", () => {
    expect(isMermaidClassName("language-mermaid")).toBe(true);
    expect(isMermaidClassName("hljs language-mermaid")).toBe(true);
    expect(isMermaidClassName("language-mermaidx")).toBe(false);
    expect(isMermaidClassName(undefined)).toBe(false);
  });
});

describe("summarizePending", () => {
  it("counts non-trailing-blank lines and returns the last one", () => {
    expect(summarizePending("flowchart LR\n  A --> B\n\n")).toEqual({
      lineCount: 2,
      lastLine: "  A --> B",
    });
    expect(summarizePending("")).toEqual({ lineCount: 0, lastLine: "" });
  });
});

describe("detectDiagramType", () => {
  it.each([
    ["flowchart LR\n  A --> B", { kind: "flowchart", keyword: "flowchart" }],
    ["graph TD;\n  A-->B", { kind: "flowchart", keyword: "graph" }],
    [
      '%%{init: {"theme":"neutral"}}%%\nsequenceDiagram',
      { kind: "sequence", keyword: "sequenceDiagram" },
    ],
    [
      "---\ntitle: Orders\n---\nerDiagram",
      { kind: "er", keyword: "erDiagram" },
    ],
    [
      "stateDiagram-v2\n  [*] --> A",
      { kind: "state", keyword: "stateDiagram-v2" },
    ],
    ["pie title Pets", { kind: "pie", keyword: "pie" }],
    ["gitGraph\n  commit", { kind: null, keyword: "gitGraph" }],
    ["constructor", { kind: null, keyword: "constructor" }],
    ["", { kind: null, keyword: null }],
  ])("%s", (source, expected) => {
    expect(detectDiagramType(source)).toEqual(expected);
  });
});

it("caps sources at the server's MERMAID_MAX_SOURCE_CHARS default", () => {
  expect(MERMAID_MAX_SOURCE_CHARS).toBe(20_000);
});
