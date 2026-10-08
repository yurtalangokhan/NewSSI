/** A run of text that either matches the query or does not. */
export interface TextSegment {
  text: string;
  match: boolean;
}

const MIN_TERM_LENGTH = 3;
// Built at runtime: the ``u`` flag is unavailable to regex literals under the
// project's ES5 compile target, but every supported browser runs it.
const NON_WORD = new RegExp("[^\\p{L}\\p{N}]+", "u");

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Split ``text`` into plain and matching segments for the query's words.
 * Matching is case-insensitive under Turkish casing rules (İ/i, I/ı).
 */
export function highlightSegments(text: string, query: string): TextSegment[] {
  const terms = query
    .split(NON_WORD)
    .filter((term) => term.length >= MIN_TERM_LENGTH)
    .map((term) => term.toLocaleLowerCase("tr"));
  if (!text || terms.length === 0) return [{ text, match: false }];

  const lowered = text.toLocaleLowerCase("tr");
  const pattern = new RegExp(
    terms
      .map(escapeRegExp)
      .sort((a, b) => b.length - a.length)
      .join("|"),
    "gu"
  );
  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const found of Array.from(lowered.matchAll(pattern))) {
    const start = found.index ?? 0;
    const end = start + found[0].length;
    if (start > cursor)
      segments.push({ text: text.slice(cursor, start), match: false });
    segments.push({ text: text.slice(start, end), match: true });
    cursor = end;
  }
  if (cursor < text.length)
    segments.push({ text: text.slice(cursor), match: false });
  return segments;
}
