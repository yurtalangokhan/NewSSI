/**
 * Wraps `body` in a code fence that cannot be closed by the body itself: the
 * fence is one backtick longer than the longest backtick run inside it (at
 * least three, as CommonMark requires).
 */
export function fenceCode(body: string, lang: string): string {
  const longestRun = Math.max(
    0,
    ...(body.match(/`+/g) ?? []).map((run) => run.length)
  );
  const fence = "`".repeat(Math.max(3, longestRun + 1));
  return `${fence}${lang}\n${body}\n${fence}`;
}
