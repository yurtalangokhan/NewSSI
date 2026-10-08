import type { Root, RootContent } from "mdast";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";

export type BlockType =
  | "heading"
  | "paragraph"
  | "list"
  | "table"
  | "code"
  | "mermaid"
  | "blockquote"
  | "thematicBreak"
  | "html"
  | "other";

export interface MarkdownBlock {
  type: BlockType;
  /** Exact source slice of the block. */
  source: string;
  hash: string;
  node: RootContent;
  /** 1-based, inclusive. */
  startLine: number;
  endLine: number;
}

const processor = unified().use(remarkParse).use(remarkGfm);

function blockTypeOf(node: RootContent): BlockType {
  switch (node.type) {
    case "heading":
    case "paragraph":
    case "list":
    case "table":
    case "blockquote":
    case "thematicBreak":
    case "html":
      return node.type;
    case "code":
      return node.lang === "mermaid" ? "mermaid" : "code";
    default:
      return "other";
  }
}

/**
 * The block source with trailing whitespace removed per line, except that a
 * Markdown hard break (two or more trailing spaces before a following line)
 * is kept as two spaces, so adding or removing one still counts as an edit.
 */
export function normalizeBlockSource(source: string): string {
  const lines = source.split("\n");
  const last = lines.length - 1;
  return lines
    .map((line, index) => {
      const trimmed = line.trimEnd();
      const isHardBreak =
        index < last && / {2,}$/.test(line) && trimmed.length > 0;
      return isHardBreak ? `${trimmed}  ` : trimmed;
    })
    .join("\n");
}

/** FNV-1a 32-bit over the normalized block source. A fast pre-filter only. */
export function hashBlock(source: string): string {
  const normalized = normalizeBlockSource(source);
  let hash = 0x811c9dc5;
  for (let i = 0; i < normalized.length; i += 1) {
    hash ^= normalized.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/**
 * Block equality for diffing. The 32-bit hash can collide, so equal hashes
 * are confirmed against the normalized source before blocks count as equal.
 */
export function blocksEqual(a: MarkdownBlock, b: MarkdownBlock): boolean {
  return (
    a.hash === b.hash &&
    normalizeBlockSource(a.source) === normalizeBlockSource(b.source)
  );
}

export function parseBlocks(markdown: string): MarkdownBlock[] {
  if (!markdown.trim()) return [];
  const tree = processor.parse(markdown) as Root;
  const blocks: MarkdownBlock[] = [];
  for (const node of tree.children) {
    const start = node.position?.start;
    const end = node.position?.end;
    if (start?.offset === undefined || end?.offset === undefined) continue;
    const source = markdown.slice(start.offset, end.offset);
    blocks.push({
      type: blockTypeOf(node),
      source,
      hash: hashBlock(source),
      node,
      startLine: start.line,
      endLine: end.line,
    });
  }
  return blocks;
}
