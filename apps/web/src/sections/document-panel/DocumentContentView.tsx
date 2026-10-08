"use client";

import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import type { MermaidDiagnostic } from "@/components/mermaid/mermaidDiagnostics";
import { documentUrlTransform } from "@/sections/document-panel/attachmentImages";
import { DocumentPaper } from "@/sections/document-panel/DocumentPaper";
import { useWhitePage } from "@/sections/document-panel/useWhitePage";

interface DocumentContentViewProps {
  markdown: string;
  onRequestMermaidFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
  className?: string;
}

/** The "paper" rendering used by Preview, Compare columns and the editor preview. */
export function DocumentContentView({
  markdown,
  onRequestMermaidFix,
  className,
}: DocumentContentViewProps) {
  const [mode] = useWhitePage();

  return (
    <DocumentPaper data-testid="document-content" className={className}>
      <MinimalMarkdown
        content={markdown}
        onRequestMermaidFix={onRequestMermaidFix}
        urlTransform={documentUrlTransform}
        lightProse={mode !== "off"}
      />
    </DocumentPaper>
  );
}
