"use client";

import type { ReactNode } from "react";
import { CodeBlock } from "@/app/app/message/CodeBlock";
import { extractCodeText } from "@/app/app/message/codeUtils";
import { useMarkdownSource } from "@/components/chat/MarkdownSourceContext";
import {
  MermaidDiagram,
  type MermaidVariant,
} from "@/components/mermaid/MermaidDiagram";
import type { MermaidDiagnostic } from "@/components/mermaid/mermaidDiagnostics";
import {
  isMermaidClassName,
  resolveMermaidBlock,
  type HastCodeNode,
} from "@/components/mermaid/mermaidSource";

export interface MarkdownCodeProps {
  node?: HastCodeNode;
  className?: string;
  children?: ReactNode;
  mermaidVariant: MermaidVariant;
  onRequestFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
}

/** react-markdown `code` renderer shared by chat markdown and MinimalMarkdown. */
export function MarkdownCode({
  node,
  className,
  children,
  mermaidVariant,
  onRequestFix,
}: MarkdownCodeProps) {
  const { markdown, isStreaming } = useMarkdownSource();

  if (isMermaidClassName(className)) {
    const block = resolveMermaidBlock({ markdown, node, isStreaming });
    return (
      <MermaidDiagram
        source={block.source}
        isComplete={block.isComplete}
        variant={mermaidVariant}
        onRequestFix={onRequestFix}
      />
    );
  }

  return (
    <CodeBlock
      className={className}
      codeText={extractCodeText(node, markdown, children)}
    >
      {children}
    </CodeBlock>
  );
}
