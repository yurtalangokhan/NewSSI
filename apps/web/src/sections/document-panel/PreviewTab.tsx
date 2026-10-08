"use client";

import { useMemo } from "react";
import type { MermaidDiagnostic } from "@/components/mermaid/mermaidDiagnostics";
import { useRevision } from "@/lib/api/domains/documents/hooks";
import { revisionToMarkdown } from "@/lib/documents/documentContent";
import { DocumentPreviewPlaceholder } from "@/sections/document-panel/DocumentPreviewPlaceholder";
import { LoadError } from "@/sections/document-panel/LoadError";
import { DocumentContentView } from "@/sections/document-panel/DocumentContentView";

interface PreviewTabProps {
  documentId: string;
  revisionNo: number;
  onRequestMermaidFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
}

export function PreviewTab({
  documentId,
  revisionNo,
  onRequestMermaidFix,
}: PreviewTabProps) {
  const { data, error, isLoading, mutate } = useRevision(
    documentId,
    revisionNo
  );
  const markdown = useMemo(
    () => (data ? revisionToMarkdown(data) : ""),
    [data]
  );

  if (error) {
    return <LoadError onRetry={() => void mutate()} />;
  }
  if (isLoading || !data) {
    // Same surface as the loaded revision, so the sheet does not change colour
    // when the text arrives.
    return (
      <DocumentPreviewPlaceholder
        className="p-4"
        data-testid="preview-loading"
      />
    );
  }
  return (
    <div className="p-4">
      <DocumentContentView
        markdown={markdown}
        onRequestMermaidFix={onRequestMermaidFix}
      />
    </div>
  );
}
