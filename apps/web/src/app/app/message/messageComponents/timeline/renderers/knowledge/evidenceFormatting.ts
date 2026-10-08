import type {
  EvidenceChunk,
  EvidenceSource,
} from "@/lib/api/domains/chat/knowledge-evidence-types";

export interface DocumentDisplay {
  name: string | null;
  extension: string | null;
}

export interface SourceGroup {
  name: string;
  extension: string | null;
  count: number;
}

const EXTENSION = /\.([a-z0-9]{2,5})$/i;

/** A chunk's document as a person reads it: a name and its file type. */
export function documentDisplay(source: EvidenceSource): DocumentDisplay {
  const label = source.document ?? source.title;
  if (!label) return { name: null, extension: null };
  const match = source.document ? EXTENSION.exec(source.document) : null;
  if (!match) return { name: label, extension: null };
  return {
    name: label.slice(0, match.index),
    extension: match[1]!.toUpperCase(),
  };
}

/** Documents the chunks came from, with how many chunks each contributed. */
export function groupSources(chunks: readonly EvidenceChunk[]): SourceGroup[] {
  const groups = new Map<string, SourceGroup>();
  for (const chunk of chunks) {
    const { name, extension } = documentDisplay(chunk.source);
    if (!name) continue;
    const key = `${name}\u0000${extension ?? ""}`;
    const group = groups.get(key);
    if (group) group.count += 1;
    else groups.set(key, { name, extension, count: 1 });
  }
  return Array.from(groups.values());
}

/** A similarity score as a 0..1 bar width. */
export function scoreRatio(score: number | null): number {
  if (score === null || !Number.isFinite(score)) return 0;
  return Math.min(1, Math.max(0, score));
}

/** What an entity property with no value reads as. */
export const EMPTY_VALUE = "—";

/** Ranking scores of a matched entity; the details show them as the match score. */
const RANKING_SCORE_KEYS: ReadonlySet<string> = new Set([
  "rrf_score",
  "bm25_score",
]);

/** An entity property as text; an empty one reads as a dash. */
export function formatPropertyValue(
  value: string | number | boolean | null
): string {
  return value === null ? EMPTY_VALUE : String(value);
}

/** An entity's properties worth listing, without its ranking scores. */
export function visibleProperties(
  properties: Readonly<Record<string, string | number | boolean | null>>
): [string, string | number | boolean | null][] {
  return Object.entries(properties).filter(
    ([key]) => !RANKING_SCORE_KEYS.has(key)
  );
}
