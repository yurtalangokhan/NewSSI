import type { TFunction } from "i18next";
import { mapPreprocessedLine } from "@/components/mermaid/mermaidLineMap";
import { MERMAID_MAX_SOURCE_CHARS } from "@/components/mermaid/mermaidSource";

export type MermaidDiagnosticKind = "parse" | "too_large" | "render";

export interface MermaidDiagnostic {
  kind: MermaidDiagnosticKind;
  /** Mermaid's own text (English), already reduced to its useful part. */
  message: string;
  /** 1-based line in the diagram source, when Mermaid reported one. */
  line: number | null;
}

export class MermaidRenderError extends Error {
  readonly diagnostic: MermaidDiagnostic;

  constructor(diagnostic: MermaidDiagnostic) {
    super(diagnostic.message);
    this.name = "MermaidRenderError";
    this.diagnostic = diagnostic;
    // Keep `instanceof` working when TypeScript targets ES5.
    Object.setPrototypeOf(this, MermaidRenderError.prototype);
  }
}

export function isMermaidRenderError(
  error: unknown
): error is MermaidRenderError {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "MermaidRenderError" &&
    "diagnostic" in error
  );
}

const LINE_PATTERN = /\bline (\d+)\b/i;
const PARSE_HEADER = /^parse error on line \d+:?$/i;
const POINTER_LINE = /^-*\^$/;
const MAX_MESSAGE_CHARS = 240;

interface JisonHash {
  loc?: { first_line?: number };
}

/** Drops the jison header, the echoed context line and the caret pointer. */
function summarize(raw: string): string {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  const pointer = lines.findIndex((line) => POINTER_LINE.test(line));
  const kept = lines.filter(
    (line, index) =>
      index !== pointer && index !== pointer - 1 && !PARSE_HEADER.test(line)
  );
  const text = (kept.length > 0 ? kept : lines).join(" ");
  return text.length > MAX_MESSAGE_CHARS
    ? `${text.slice(0, MAX_MESSAGE_CHARS - 1)}…`
    : text;
}

/**
 * Maps whatever mermaid.render threw to a line-aware diagnostic. Mermaid
 * counts lines in its preprocessed text, so pass the original `source` to get
 * the line the user sees (front matter, `%%` comments and directives skew it).
 */
export function toMermaidDiagnostic(
  error: unknown,
  source?: string
): MermaidDiagnostic {
  if (isMermaidRenderError(error)) return error.diagnostic;
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";
  const fromMessage = LINE_PATTERN.exec(raw);
  const hashLine = (error as { hash?: JisonHash } | null)?.hash?.loc
    ?.first_line;
  const reported = fromMessage
    ? Number(fromMessage[1])
    : typeof hashLine === "number"
      ? hashLine
      : null;
  const line =
    reported !== null && source !== undefined
      ? mapPreprocessedLine(source, reported)
      : reported;
  const message = summarize(raw);
  return {
    kind: "parse",
    message:
      line !== null && line !== reported
        ? message.replace(LINE_PATTERN, `line ${line}`)
        : message,
    line,
  };
}

/** The follow-up chat message sent by "Ask the agent to fix". */
export function buildMermaidFixRequest(
  t: TFunction,
  source: string,
  diagnostic: MermaidDiagnostic
): string {
  return t("mermaid.fixRequest", {
    error: describeMermaidDiagnostic(t, diagnostic),
    source,
  });
}

export function describeMermaidDiagnostic(
  t: TFunction,
  diagnostic: MermaidDiagnostic
): string {
  if (diagnostic.kind === "too_large") {
    return t("mermaid.tooLarge", { max: MERMAID_MAX_SOURCE_CHARS });
  }
  if (diagnostic.message === "") return t("mermaid.errorUnknown");
  if (diagnostic.line !== null) {
    return t("mermaid.errorWithLine", {
      line: diagnostic.line,
      message: diagnostic.message,
    });
  }
  return t("mermaid.error", { message: diagnostic.message });
}
