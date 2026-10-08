/**
 * Maps a line Mermaid reports back to the line in the source the user sees.
 *
 * Mermaid parses a preprocessed copy of the diagram (see `preprocessDiagram`
 * in mermaid 11.16): the front matter is sliced off, `%%{...}%%` directives
 * are removed, whole-line `%%` comments are dropped and leading whitespace is
 * trimmed. Every step shifts line numbers, so reported lines are relative to
 * that copy. This mirrors those steps while remembering where each surviving
 * character came from. No DOM and no Mermaid import.
 */

const FRONT_MATTER =
  /^([^\S\n\r]*)-{3}\s*[\n\r]([\s\S]*?)[\n\r]\1-{3}\s*[\n\r]+/;
const directivePattern = () =>
  /%{2}\{\s*(?:(\w+)\s*:|(\w+))\s*(?:(\w+)|((?:(?!}%{2}).|\r?\n)*))?\s*(?:}%{2})?/gi;
const commentLinePattern = () => /^\s*%%(?!\{)[^\n]+\n?/gm;

interface Tracked {
  text: string;
  /** For each character of `text`, its index in the original source. */
  origin: number[];
}

function dropMatches(input: Tracked, pattern: RegExp): Tracked {
  // Each pattern is a fresh global regex (see the factories above), so the
  // exec loop owns its lastIndex and needs an explicit step over empty matches.
  const ranges: RegExpExecArray[] = [];
  for (
    let match = pattern.exec(input.text);
    match !== null;
    match = pattern.exec(input.text)
  ) {
    ranges.push(match);
    if (match[0] === "") pattern.lastIndex += 1;
  }
  if (ranges.length === 0) return input;
  let text = "";
  const origin: number[] = [];
  let cursor = 0;
  const keep = (from: number, to: number) => {
    text += input.text.slice(from, to);
    for (let index = from; index < to; index += 1) {
      origin.push(input.origin[index]!);
    }
  };
  for (const match of ranges) {
    const start = match.index;
    keep(cursor, start);
    cursor = start + match[0].length;
  }
  keep(cursor, input.text.length);
  return { text, origin };
}

function sliceFrom(input: Tracked, start: number): Tracked {
  return {
    text: input.text.slice(start),
    origin: input.origin.slice(start),
  };
}

function preprocess(source: string): Tracked {
  const text = source.replace(/\r\n?/g, "\n");
  let tracked: Tracked = {
    text,
    origin: Array.from({ length: text.length }, (_, index) => index),
  };
  const frontMatter = FRONT_MATTER.exec(tracked.text);
  if (frontMatter) tracked = sliceFrom(tracked, frontMatter[0].length);
  tracked = dropMatches(tracked, directivePattern());
  tracked = dropMatches(tracked, commentLinePattern());
  const leading = tracked.text.length - tracked.text.trimStart().length;
  return sliceFrom(tracked, leading);
}

/**
 * Converts a 1-based line of the preprocessed diagram into a 1-based line of
 * `source`. Returns the input unchanged when it lies outside the text.
 */
export function mapPreprocessedLine(source: string, line: number): number {
  if (!Number.isInteger(line) || line < 1) return line;
  const { text, origin } = preprocess(source);
  let offset = 0;
  for (let current = 1; current < line; current += 1) {
    const next = text.indexOf("\n", offset);
    if (next === -1) return line;
    offset = next + 1;
  }
  const originIndex = origin[offset];
  if (originIndex === undefined) return line;
  const normalized = source.replace(/\r\n?/g, "\n");
  let mapped = 1;
  for (let index = 0; index < originIndex; index += 1) {
    if (normalized[index] === "\n") mapped += 1;
  }
  return mapped;
}
