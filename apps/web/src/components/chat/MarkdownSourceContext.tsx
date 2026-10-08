"use client";

import { createContext, useContext, type ReactNode } from "react";

export interface MarkdownSource {
  /** The exact string handed to react-markdown; node offsets index into it. */
  markdown: string;
  /** True while the text is still streaming in. */
  isStreaming: boolean;
}

const MarkdownSourceContext = createContext<MarkdownSource>({
  markdown: "",
  isStreaming: false,
});

interface MarkdownSourceProviderProps {
  value: MarkdownSource;
  children: ReactNode;
}

/**
 * Lets `code` renderers read the parsed source without being recreated per
 * content change. A new renderer identity would remount every code block (and
 * a Mermaid diagram's state) on each streamed packet.
 */
export function MarkdownSourceProvider({
  value,
  children,
}: MarkdownSourceProviderProps) {
  return (
    <MarkdownSourceContext.Provider value={value}>
      {children}
    </MarkdownSourceContext.Provider>
  );
}

export function useMarkdownSource(): MarkdownSource {
  return useContext(MarkdownSourceContext);
}
