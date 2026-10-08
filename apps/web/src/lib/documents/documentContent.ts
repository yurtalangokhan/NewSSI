import type {
  DocumentKind,
  ExportFormat,
  RevisionDetail,
  SourceFormat,
} from "@/lib/api/domains/documents/types";

/**
 * A fenced code block whose fence is longer than any backtick run in the
 * body, so content containing ``` can never close the fence early and spill
 * into rendered Markdown (a spilled mermaid fence would execute).
 */
export function fenceCode(lang: string, body: string): string {
  const longestRun = (body.match(/`+/g) ?? []).reduce(
    (longest, run) => Math.max(longest, run.length),
    0
  );
  const marker = "`".repeat(Math.max(3, longestRun + 1));
  return `${marker}${lang}\n${body}\n${marker}`;
}

const cell = (value: unknown) =>
  String(value ?? "")
    .replace(/\|/g, "\\|")
    .replace(/\r?\n/g, " ");

function sheetToTable(rows: unknown[]): string {
  if (!rows.length) return "";
  let header: string[];
  let body: unknown[][];
  if (Array.isArray(rows[0])) {
    // The widest row sets the column count, so no cell is cut off.
    const width = rows.reduce<number>(
      (max, row) => Math.max(max, Array.isArray(row) ? row.length : 0),
      0
    );
    const first = rows[0] as unknown[];
    header = Array.from({ length: width }, (_, i) => cell(first[i]));
    body = rows.slice(1) as unknown[][];
  } else {
    // Every key that appears in any row becomes a column, in first-seen order.
    const keys: string[] = [];
    const seen = new Set<string>();
    for (const row of rows) {
      if (typeof row !== "object" || row === null || Array.isArray(row))
        continue;
      for (const key of Object.keys(row)) {
        if (!seen.has(key)) {
          seen.add(key);
          keys.push(key);
        }
      }
    }
    header = keys.map(cell);
    body = rows.map((row) =>
      keys.map((key) =>
        typeof row === "object" && row !== null
          ? (row as Record<string, unknown>)[key]
          : ""
      )
    );
  }
  const line = (values: string[]) => `| ${values.join(" | ")} |`;
  return [
    line(header),
    line(header.map(() => "---")),
    ...body.map((row) =>
      line(header.map((_, i) => cell(Array.isArray(row) ? row[i] : "")))
    ),
  ].join("\n");
}

/**
 * One Markdown view of any revision, so the preview, the diff engine and the
 * compare view share one pipeline for documents, JSON and spreadsheets.
 */
export function revisionToMarkdown(
  revision: Pick<RevisionDetail, "source_format" | "content">
): string {
  const { source_format, content } = revision;
  if (source_format === "markdown") return content;
  try {
    const parsed: unknown = JSON.parse(content);
    if (source_format === "json")
      return fenceCode("json", JSON.stringify(parsed, null, 2));
    const sheets = parsed as { name: string; rows: unknown[] }[];
    return sheets
      .map((sheet) => `## ${sheet.name}\n\n${sheetToTable(sheet.rows)}`)
      .join("\n\n");
  } catch {
    return fenceCode("json", content);
  }
}

export function exportFormatsFor(
  kind: DocumentKind,
  sourceFormat: SourceFormat
): ExportFormat[] {
  if (kind === "spreadsheet") return ["xlsx", "csv"];
  if (sourceFormat === "json") return ["json", "txt"];
  return ["docx", "pdf", "md", "txt"];
}
