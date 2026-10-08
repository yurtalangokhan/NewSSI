"use client";

import { useEffect, useRef } from "react";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { unifiedMergeView } from "@codemirror/merge";
import {
  Compartment,
  EditorState,
  Extension,
  RangeSetBuilder,
  StateEffect,
  StateField,
} from "@codemirror/state";
import {
  Decoration,
  DecorationSet,
  EditorView,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import { cn } from "@/lib/utils";

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  ariaLabel: string;
  readOnly?: boolean;
  /** 1-based document lines to mark (e.g. Mermaid diagnostics from a 422). */
  highlightLines?: number[];
  /** When set, show a unified merge view of `value` against this text. */
  mergeOriginal?: string | null;
  className?: string;
}

const setHighlightedLines = StateEffect.define<number[]>();
const diagnosticLine = Decoration.line({ class: "cm-diagnostic-line" });

const highlightField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decorations, tr) {
    let next = decorations.map(tr.changes);
    for (const effect of tr.effects) {
      if (!effect.is(setHighlightedLines)) continue;
      const builder = new RangeSetBuilder<Decoration>();
      for (const n of Array.from(new Set(effect.value)).sort((a, b) => a - b)) {
        if (n < 1 || n > tr.state.doc.lines) continue;
        const line = tr.state.doc.line(n);
        builder.add(line.from, line.from, diagnosticLine);
      }
      next = builder.finish();
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});

const tokenTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    backgroundColor: "var(--background-tint-00)",
    color: "var(--text-05)",
    height: "100%",
  },
  ".cm-scroller": {
    fontFamily: "var(--font-mono, ui-monospace, monospace)",
  },
  ".cm-gutters": {
    backgroundColor: "var(--background-tint-01)",
    color: "var(--text-03)",
    border: "none",
  },
  ".cm-activeLine": { backgroundColor: "var(--background-tint-01)" },
  ".cm-diagnostic-line": { backgroundColor: "var(--status-error-01)" },
  ".cm-changedLine": { backgroundColor: "var(--status-success-01)" },
  ".cm-deletedChunk": { backgroundColor: "var(--status-error-01)" },
  ".cm-changedText": { backgroundColor: "var(--status-success-02)" },
  "&.cm-focused": { outline: "none" },
});

function mergeExtension(
  original: string | null | undefined,
  readOnly: boolean
): Extension {
  return original == null
    ? []
    : unifiedMergeView({
        original,
        mergeControls: !readOnly,
        highlightChanges: true,
        gutter: true,
      });
}

const editableExtension = (readOnly: boolean): Extension => [
  EditorState.readOnly.of(readOnly),
  EditorView.editable.of(!readOnly),
];

export function CodeEditor({
  value,
  onChange,
  ariaLabel,
  readOnly = false,
  highlightLines,
  mergeOriginal,
  className,
}: CodeEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const syncingRef = useRef(false);
  const compartments = useRef({
    merge: new Compartment(),
    editable: new Compartment(),
  });
  onChangeRef.current = onChange;

  useEffect(() => {
    const { merge, editable } = compartments.current;
    const view = new EditorView({
      parent: hostRef.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          markdown(),
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({ "aria-label": ariaLabel }),
          highlightField,
          tokenTheme,
          editable.of(editableExtension(readOnly)),
          merge.of(mergeExtension(mergeOriginal, readOnly)),
          EditorView.updateListener.of((update) => {
            if (update.docChanged && !syncingRef.current) {
              onChangeRef.current?.(update.state.doc.toString());
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // The view is created once; the effects below keep it in sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    syncingRef.current = true;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
    });
    syncingRef.current = false;
  }, [value]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: setHighlightedLines.of(highlightLines ?? []),
    });
  }, [highlightLines]);

  useEffect(() => {
    const { merge, editable } = compartments.current;
    viewRef.current?.dispatch({
      effects: [
        merge.reconfigure(mergeExtension(mergeOriginal, readOnly)),
        editable.reconfigure(editableExtension(readOnly)),
      ],
    });
  }, [mergeOriginal, readOnly]);

  return (
    <div
      ref={hostRef}
      data-testid="code-editor"
      className={cn(
        "h-full min-h-0 overflow-hidden rounded-08 border border-border-01",
        className
      )}
    />
  );
}
