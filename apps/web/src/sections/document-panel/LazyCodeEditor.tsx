"use client";

import dynamic from "next/dynamic";

/**
 * CodeMirror (all `@codemirror/*` packages) is only needed once the user edits
 * or reads a source diff, so it stays out of the chat page's initial bundle.
 */
export const LazyCodeEditor = dynamic(
  () =>
    import("@/sections/document-panel/CodeEditor").then((m) => m.CodeEditor),
  {
    ssr: false,
    loading: () => (
      <div
        className="h-full min-h-[12rem] rounded-12 bg-background-tint-02 animate-pulse"
        data-testid="code-editor-loading"
      />
    ),
  }
);
