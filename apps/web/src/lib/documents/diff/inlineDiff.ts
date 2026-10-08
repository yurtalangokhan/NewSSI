import {
  diffArrays,
  diffWordsWithSpace,
  type ArrayChange,
  type Change,
} from "diff";
import type { Code, Table, TableRow } from "mdast";
import { toString } from "mdast-util-to-string";
import type {
  BlockDiffEntry,
  BlockStatus,
} from "@/lib/documents/diff/blockDiff";

export interface InlineSegment {
  value: string;
  kind: "same" | "ins" | "del";
}

/**
 * Cost bounds for one inline diff. blockDiff caps the whole document, but a
 * single huge paragraph or table can still be expensive: jsdiff gives up
 * (returns `undefined`) once the edit distance or the time budget is exceeded.
 * `timeout` is supported by jsdiff 5.2 at runtime but missing from its typings.
 */
export const INLINE_DIFF_MAX_EDIT_LENGTH = 1_000;
export const INLINE_DIFF_TIMEOUT_MS = 200;
const DIFF_BUDGET: { maxEditLength: number } = {
  maxEditLength: INLINE_DIFF_MAX_EDIT_LENGTH,
  ...{ timeout: INLINE_DIFF_TIMEOUT_MS },
};

/** What a bounded diff shows when it gives up: the old text, then the new. */
function replacement(before: string, after: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  if (before !== "") segments.push({ kind: "del", value: before });
  if (after !== "") segments.push({ kind: "ins", value: after });
  return segments;
}

export function inlineDiff(before: string, after: string): InlineSegment[] {
  const parts = diffWordsWithSpace(before, after, DIFF_BUDGET) as
    | Change[]
    | undefined;
  if (!parts) return replacement(before, after);
  return parts.map((part) => ({
    value: part.value,
    kind: part.added ? "ins" : part.removed ? "del" : "same",
  }));
}

export interface TableCellDiff {
  kind: "same" | "changed" | "ins" | "del";
  before: string | null;
  after: string | null;
  segments: InlineSegment[];
}

export interface TableRowDiff {
  status: BlockStatus;
  cells: TableCellDiff[];
}

export interface TableDiff {
  header: TableRowDiff;
  rows: TableRowDiff[];
  changedCells: number;
  addedRows: number;
  removedRows: number;
}

/** A cell's plain text (shown) and its Markdown source (compared). */
interface CellText {
  text: string;
  raw: string;
}

type RowTexts = CellText[];

const rowKey = (row: RowTexts) => row.map((c) => c.raw).join("\u0000");

/** The Markdown source of a node, sliced out of the block it belongs to. */
function sourceOf(
  node: TableRow["children"][number],
  block: { source: string; startOffset: number } | null
): string {
  const text = toString(node);
  const start = node.position?.start.offset;
  const end = node.position?.end.offset;
  if (!block || start === undefined || end === undefined) return text;
  return stripCellPipes(
    block.source.slice(start - block.startOffset, end - block.startOffset)
  );
}

/** GFM cell positions include the delimiting pipes; keep only the content. */
function stripCellPipes(raw: string): string {
  let content = raw.trim();
  if (content.startsWith("|")) content = content.slice(1);
  if (content.endsWith("|") && !content.endsWith("\\|")) {
    content = content.slice(0, -1);
  }
  return content.trim();
}

function compareRows(before: RowTexts, after: RowTexts): TableRowDiff {
  const width = Math.max(before.length, after.length);
  const cells: TableCellDiff[] = [];
  for (let i = 0; i < width; i += 1) {
    const beforeCell = before[i];
    const afterCell = after[i];
    const b = beforeCell?.text ?? null;
    const a = afterCell?.text ?? null;
    if (b !== null && a !== null && beforeCell!.raw !== afterCell!.raw) {
      const segments = inlineDiff(b, a);
      // Same text but different source: a link target or formatting changed.
      const textOnly = segments.every((segment) => segment.kind === "same");
      cells.push({
        kind: "changed",
        before: textOnly ? beforeCell!.raw : b,
        after: textOnly ? afterCell!.raw : a,
        segments: textOnly
          ? inlineDiff(beforeCell!.raw, afterCell!.raw)
          : segments,
      });
    } else if (b === a)
      cells.push({
        kind: "same",
        before: b,
        after: a,
        segments: [{ kind: "same", value: a ?? "" }],
      });
    else if (b === null)
      cells.push({
        kind: "ins",
        before: null,
        after: a,
        segments: [{ kind: "ins", value: a ?? "" }],
      });
    else if (a === null)
      cells.push({
        kind: "del",
        before: b,
        after: null,
        segments: [{ kind: "del", value: b }],
      });
    else
      cells.push({
        kind: "changed",
        before: b,
        after: a,
        segments: inlineDiff(b, a),
      });
  }
  const status: BlockStatus = cells.every((c) => c.kind === "same")
    ? "unchanged"
    : "modified";
  return { status, cells };
}

const wholeRow = (
  texts: RowTexts,
  status: "added" | "removed"
): TableRowDiff => ({
  status,
  cells: texts.map(({ text: value }) => ({
    kind: status === "added" ? "ins" : "del",
    before: status === "removed" ? value : null,
    after: status === "added" ? value : null,
    segments: [{ kind: status === "added" ? "ins" : "del", value }],
  })),
});

/** The block source of each table, so cell edits in links and emphasis show. */
export interface TableSources {
  before: string;
  after: string;
}

function rowsOf(table: Table, source: string | undefined): RowTexts[] {
  const startOffset = table.position?.start.offset;
  const block =
    source !== undefined && startOffset !== undefined
      ? { source, startOffset }
      : null;
  return table.children.map((row) =>
    row.children.map((cell) => ({
      text: toString(cell),
      raw: sourceOf(cell, block),
    }))
  );
}

export function tableDiff(
  before: Table,
  after: Table,
  sources?: TableSources
): TableDiff {
  const [beforeHead, ...beforeBody] = rowsOf(before, sources?.before);
  const [afterHead, ...afterBody] = rowsOf(after, sources?.after);
  const header = compareRows(beforeHead ?? [], afterHead ?? []);

  const rows: TableRowDiff[] = [];
  let bi = 0;
  let ai = 0;
  let removed: RowTexts[] = [];
  let added: RowTexts[] = [];
  const flush = () => {
    // Positional pairing: the n-th removed row was most likely edited into the n-th added row.
    const paired = Math.min(removed.length, added.length);
    for (let i = 0; i < paired; i += 1)
      rows.push(compareRows(removed[i]!, added[i]!));
    for (const row of added.slice(paired)) rows.push(wholeRow(row, "added"));
    for (const row of removed.slice(paired))
      rows.push(wholeRow(row, "removed"));
    removed = [];
    added = [];
  };

  const rowParts = diffArrays(
    beforeBody.map(rowKey),
    afterBody.map(rowKey),
    DIFF_BUDGET
  ) as ArrayChange<string>[] | undefined;
  // Gave up: treat every row as replaced, so cells still pair by position.
  const parts: ArrayChange<string>[] = rowParts ?? [
    {
      value: beforeBody.map(rowKey),
      removed: true,
      count: beforeBody.length,
    },
    { value: afterBody.map(rowKey), added: true, count: afterBody.length },
  ];
  for (const part of parts) {
    const count = part.value.length;
    if (part.removed) {
      removed.push(...beforeBody.slice(bi, bi + count));
      bi += count;
    } else if (part.added) {
      added.push(...afterBody.slice(ai, ai + count));
      ai += count;
    } else {
      flush();
      for (let i = 0; i < count; i += 1)
        rows.push(compareRows(beforeBody[bi + i]!, afterBody[ai + i]!));
      bi += count;
      ai += count;
    }
  }
  flush();

  return {
    header,
    rows,
    changedCells: [header, ...rows]
      .filter((r) => r.status === "modified")
      .reduce((n, r) => n + r.cells.filter((c) => c.kind !== "same").length, 0),
    addedRows: rows.filter((r) => r.status === "added").length,
    removedRows: rows.filter((r) => r.status === "removed").length,
  };
}

export type BlockModification =
  | { kind: "text"; segments: InlineSegment[] }
  | { kind: "table"; table: TableDiff }
  | { kind: "pair"; before: string; after: string };

/** How a `modified` block renders in the Changes view. */
export function describeModification(entry: BlockDiffEntry): BlockModification {
  const before = entry.before!;
  const after = entry.after!;
  if (before.type === "table") {
    return {
      kind: "table",
      table: tableDiff(before.node as Table, after.node as Table, {
        before: before.source,
        after: after.source,
      }),
    };
  }
  if (before.type === "mermaid" || before.type === "code") {
    return {
      kind: "pair",
      before: (before.node as Code).value,
      after: (after.node as Code).value,
    };
  }
  if (["paragraph", "heading", "list", "blockquote"].includes(before.type)) {
    const segments = inlineDiff(toString(before.node), toString(after.node));
    // The text is identical but the source is not (a link target, emphasis):
    // a text diff would show nothing, so show the raw sources side by side.
    if (segments.every((segment) => segment.kind === "same")) {
      return { kind: "pair", before: before.source, after: after.source };
    }
    return { kind: "text", segments };
  }
  return { kind: "pair", before: before.source, after: after.source };
}
