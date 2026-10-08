/**
 * Pure analysis of Mermaid source text: whether a fenced block is complete
 * while a message streams, the diagram type for the block header, and the
 * pending-state summary. No DOM and no Mermaid import, so it is safe for SSR
 * and node tests.
 */

/** Same cap as the server validator (agent-service MERMAID_MAX_SOURCE_CHARS). */
export const MERMAID_MAX_SOURCE_CHARS = 20_000;

/** The blinking-cursor hack MessageTextRenderer appends while streaming. */
const STREAMING_CURSOR = /\s*\[\*\]\(\)\s*$/;
const OPENING_FENCE = /^[ \t>]*(`{3,}|~{3,})/;
const CLOSING_FENCE = /^[ \t>]*(`{3,}|~{3,})[ \t]*$/;

export interface HastTextNode {
  type?: string;
  value?: unknown;
  children?: HastTextNode[];
}

export interface HastPosition {
  start?: { offset?: number | null };
  end?: { offset?: number | null };
}

export interface HastCodeNode extends HastTextNode {
  position?: HastPosition;
}

export interface MermaidBlockInput {
  /** The exact string react-markdown parsed; node offsets index into it. */
  markdown: string;
  /** The hast `code` element handed to the markdown `code` override. */
  node: HastCodeNode | undefined;
  /** True while the message text is still arriving. */
  isStreaming: boolean;
}

export interface MermaidBlock {
  source: string;
  isComplete: boolean;
}

export type MermaidDiagramKind =
  | "flowchart"
  | "sequence"
  | "class"
  | "state"
  | "er"
  | "gantt"
  | "pie"
  | "mindmap"
  | "timeline";

export interface MermaidDiagramType {
  kind: MermaidDiagramKind | null;
  /** The first keyword of the source, shown when the kind is unknown. */
  keyword: string | null;
}

export interface PendingSummary {
  lineCount: number;
  lastLine: string;
}

const KEYWORD_TO_KIND = new Map<string, MermaidDiagramKind>([
  ["flowchart", "flowchart"],
  ["flowchart-elk", "flowchart"],
  ["graph", "flowchart"],
  ["sequenceDiagram", "sequence"],
  ["classDiagram", "class"],
  ["classDiagram-v2", "class"],
  ["stateDiagram", "state"],
  ["stateDiagram-v2", "state"],
  ["erDiagram", "er"],
  ["gantt", "gantt"],
  ["pie", "pie"],
  ["mindmap", "mindmap"],
  ["timeline", "timeline"],
]);

export function hastToText(node: HastTextNode | undefined): string {
  if (!node) return "";
  if (typeof node.value === "string") return node.value;
  return (node.children ?? []).map(hastToText).join("");
}

/**
 * True when the raw fenced block ends with a closing fence made of the same
 * character and at least as long as the opening one. Container prefixes
 * (blockquote `>`, indentation) are tolerated on the closing line. A closing
 * line with anything else on it (e.g. the streaming cursor) does not close
 * the fence, which matches CommonMark and therefore react-markdown.
 */
export function isFenceClosed(raw: string): boolean {
  const lines = raw.replace(/\s+$/, "").split("\n");
  if (lines.length < 2) return false;
  const opening = OPENING_FENCE.exec(lines[0]!);
  const closing = CLOSING_FENCE.exec(lines[lines.length - 1]!);
  if (!opening || !closing) return false;
  const fence = opening[1]!;
  const closer = closing[1]!;
  return closer[0] === fence[0] && closer.length >= fence.length;
}

export function isMermaidClassName(className: unknown): boolean {
  return (
    typeof className === "string" &&
    className.split(/\s+/).includes("language-mermaid")
  );
}

/**
 * Decides whether a `language-mermaid` code node may be rendered. The fence is
 * complete when its source slice ends with a closing fence, or when the
 * message has stopped streaming (the model never closed it).
 */
export function resolveMermaidBlock({
  markdown,
  node,
  isStreaming,
}: MermaidBlockInput): MermaidBlock {
  const start = node?.position?.start?.offset;
  const end = node?.position?.end?.offset;
  const isClosed =
    typeof start === "number" && typeof end === "number"
      ? isFenceClosed(markdown.slice(start, end))
      : !isStreaming;
  const text = hastToText(node).replace(/\n$/, "");
  const source = isClosed ? text : text.replace(STREAMING_CURSOR, "");
  return { source, isComplete: isClosed || !isStreaming };
}

export function summarizePending(source: string): PendingSummary {
  const lines = source.split("\n");
  while (lines.length > 0 && lines[lines.length - 1]!.trim() === "") {
    lines.pop();
  }
  return { lineCount: lines.length, lastLine: lines[lines.length - 1] ?? "" };
}

/** Skips YAML front matter, blank lines and `%%` comments/directives. */
export function detectDiagramType(source: string): MermaidDiagramType {
  const lines = source.split("\n");
  let index = 0;
  if (lines[0]?.trim() === "---") {
    index = 1;
    while (index < lines.length && lines[index]!.trim() !== "---") index += 1;
    index += 1;
  }
  for (; index < lines.length; index += 1) {
    const line = lines[index]!.trim();
    if (line === "" || line.startsWith("%%")) continue;
    const keyword = line.split(/[\s;:]+/)[0] ?? "";
    return {
      kind: KEYWORD_TO_KIND.get(keyword) ?? null,
      keyword: keyword === "" ? null : keyword,
    };
  }
  return { kind: null, keyword: null };
}
