import type { TFunction } from "i18next";
import {
  MermaidRenderError,
  buildMermaidFixRequest,
  describeMermaidDiagnostic,
  isMermaidRenderError,
  toMermaidDiagnostic,
} from "@/components/mermaid/mermaidDiagnostics";

const t = ((key: string, options?: Record<string, unknown>) =>
  options ? `${key} ${JSON.stringify(options)}` : key) as unknown as TFunction;

describe("toMermaidDiagnostic", () => {
  it("reads the line from a jison parse error and keeps the expectation", () => {
    const error = new Error(
      "Parse error on line 3:\n...B -->> C[Finans\n-----^\nExpecting 'SEMI', 'NEWLINE', got 'ARROW'"
    );

    expect(toMermaidDiagnostic(error)).toEqual({
      kind: "parse",
      line: 3,
      message: "Expecting 'SEMI', 'NEWLINE', got 'ARROW'",
    });
  });

  it("reads the line from a langium lexer error", () => {
    const message =
      "Parsing failed: Lexer error on line 2, column 5: unexpected character: ->@<- at offset: 20, skipped 1 characters.";

    expect(toMermaidDiagnostic(new Error(message))).toEqual({
      kind: "parse",
      line: 2,
      message,
    });
  });

  it("maps the line back to the source when front matter and comments precede it", () => {
    const source = "---\ntitle: t\n---\n%% a comment\nflowchart\nA BROKEN B";
    const error = new Error(
      "Parse error on line 2:\nA BROKEN B\n^\nExpecting 'SEMI'"
    );

    expect(toMermaidDiagnostic(error, source)).toEqual({
      kind: "parse",
      line: 6,
      message: "Expecting 'SEMI'",
    });
  });

  it("rewrites the line quoted inside a langium message", () => {
    const source = "%% x\n\npie\nBAD";
    const error = new Error("Lexer error on line 2, column 1: unexpected");

    expect(toMermaidDiagnostic(error, source)).toMatchObject({
      line: 4,
      message: "Lexer error on line 4, column 1: unexpected",
    });
  });

  it("falls back to the jison hash location", () => {
    const error = Object.assign(new Error("Syntax error"), {
      hash: { loc: { first_line: 4 } },
    });

    expect(toMermaidDiagnostic(error)).toEqual({
      kind: "parse",
      line: 4,
      message: "Syntax error",
    });
  });

  it("passes a MermaidRenderError through unchanged", () => {
    const error = new MermaidRenderError({
      kind: "too_large",
      message: "",
      line: null,
    });

    expect(error).toBeInstanceOf(MermaidRenderError);
    expect(isMermaidRenderError(error)).toBe(true);
    expect(toMermaidDiagnostic(error)).toBe(error.diagnostic);
  });

  it("handles non-Error throws and truncates long messages", () => {
    expect(toMermaidDiagnostic("boom")).toEqual({
      kind: "parse",
      line: null,
      message: "boom",
    });
    expect(toMermaidDiagnostic(undefined).message).toBe("");

    const long = toMermaidDiagnostic(new Error("x".repeat(500))).message;
    expect(long).toHaveLength(240);
    expect(long.endsWith("…")).toBe(true);
  });
});

describe("describeMermaidDiagnostic", () => {
  it("picks the message for each diagnostic shape", () => {
    expect(
      describeMermaidDiagnostic(t, {
        kind: "parse",
        message: "Expecting 'SEMI'",
        line: 3,
      })
    ).toBe(`mermaid.errorWithLine {"line":3,"message":"Expecting 'SEMI'"}`);
    expect(
      describeMermaidDiagnostic(t, {
        kind: "render",
        message: "boom",
        line: null,
      })
    ).toBe(`mermaid.error {"message":"boom"}`);
    expect(
      describeMermaidDiagnostic(t, { kind: "parse", message: "", line: null })
    ).toBe("mermaid.errorUnknown");
    expect(
      describeMermaidDiagnostic(t, {
        kind: "too_large",
        message: "",
        line: null,
      })
    ).toBe(`mermaid.tooLarge {"max":20000}`);
  });
});

describe("buildMermaidFixRequest", () => {
  it("embeds the localized error and the source", () => {
    const text = buildMermaidFixRequest(t, "flowchart LR\n  A BROKEN B", {
      kind: "parse",
      message: "Expecting 'SEMI'",
      line: 2,
    });

    expect(text).toBe(
      `mermaid.fixRequest {"error":"mermaid.errorWithLine {\\"line\\":2,\\"message\\":\\"Expecting 'SEMI'\\"}","source":"flowchart LR\\n  A BROKEN B"}`
    );
  });
});
