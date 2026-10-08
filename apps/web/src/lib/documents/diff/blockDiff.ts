import { diffArrays } from "diff";
import {
  MarkdownBlock,
  blocksEqual,
  parseBlocks,
} from "@/lib/documents/diff/markdownBlocks";

export type BlockStatus = "unchanged" | "added" | "removed" | "modified";

export interface BlockDiffEntry {
  status: BlockStatus;
  before: MarkdownBlock | null;
  after: MarkdownBlock | null;
}

export interface BlockDiffSummary {
  added: number;
  removed: number;
  modified: number;
  unchanged: number;
}

export type BlockDiffResult =
  | { tooLarge: false; entries: BlockDiffEntry[]; summary: BlockDiffSummary }
  | { tooLarge: true };

/** Above these sizes the rendered diff would block the main thread. */
export const MAX_DIFF_CHARS = 200_000;
export const MAX_DIFF_BLOCKS = 3_000;

/**
 * Pair a removed run with an added run: same-type blocks, in order, become
 * `modified`; the rest stay removed/added. Order follows the new document.
 */
function pairRuns(
  removed: MarkdownBlock[],
  added: MarkdownBlock[]
): BlockDiffEntry[] {
  const entries: BlockDiffEntry[] = [];
  let r = 0;
  let a = 0;
  while (r < removed.length || a < added.length) {
    const before = removed[r];
    const after = added[a];
    if (before && after && before.type === after.type) {
      entries.push({ status: "modified", before, after });
      r += 1;
      a += 1;
    } else if (before && !added.slice(a).some((b) => b.type === before.type)) {
      entries.push({ status: "removed", before, after: null });
      r += 1;
    } else if (after) {
      entries.push({ status: "added", before: null, after });
      a += 1;
    } else if (before) {
      entries.push({ status: "removed", before, after: null });
      r += 1;
    }
  }
  return entries;
}

function summarize(entries: BlockDiffEntry[]): BlockDiffSummary {
  const summary: BlockDiffSummary = {
    added: 0,
    removed: 0,
    modified: 0,
    unchanged: 0,
  };
  for (const entry of entries) summary[entry.status] += 1;
  return summary;
}

export function blockDiff(before: string, after: string): BlockDiffResult {
  if (before.length > MAX_DIFF_CHARS || after.length > MAX_DIFF_CHARS)
    return { tooLarge: true };
  const beforeBlocks = parseBlocks(before);
  const afterBlocks = parseBlocks(after);
  if (
    beforeBlocks.length > MAX_DIFF_BLOCKS ||
    afterBlocks.length > MAX_DIFF_BLOCKS
  ) {
    return { tooLarge: true };
  }

  const parts = diffArrays(beforeBlocks, afterBlocks, {
    comparator: blocksEqual,
  });

  const entries: BlockDiffEntry[] = [];
  let bi = 0;
  let ai = 0;
  let removedRun: MarkdownBlock[] = [];
  let addedRun: MarkdownBlock[] = [];
  const flush = () => {
    entries.push(...pairRuns(removedRun, addedRun));
    removedRun = [];
    addedRun = [];
  };

  for (const part of parts) {
    const count = part.value.length;
    if (part.removed) {
      removedRun.push(...beforeBlocks.slice(bi, bi + count));
      bi += count;
    } else if (part.added) {
      addedRun.push(...afterBlocks.slice(ai, ai + count));
      ai += count;
    } else {
      flush();
      for (let i = 0; i < count; i += 1) {
        entries.push({
          status: "unchanged",
          before: beforeBlocks[bi + i]!,
          after: afterBlocks[ai + i]!,
        });
      }
      bi += count;
      ai += count;
    }
  }
  flush();

  return { tooLarge: false, entries, summary: summarize(entries) };
}
