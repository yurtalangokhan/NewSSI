/** Mirrors apps/agent-service/src/schemas/authored_documents.py. */

export type DocumentKind = "document" | "spreadsheet";
export type SourceFormat = "markdown" | "json" | "sheets_json";
export type RevisionOperation =
  | "create"
  | "edit"
  | "rewrite"
  | "user_edit"
  | "restore";
export type AuthorType = "agent" | "user";
export type DiagramCheck = "passed" | "skipped" | "not_applicable";
export type ExportFormat =
  | "pdf"
  | "docx"
  | "md"
  | "txt"
  | "json"
  | "xlsx"
  | "csv";
export type ChangeKind = "added" | "removed" | "modified";

export interface RevisionChange {
  /** Block kind, e.g. "paragraph", "table", "mermaid". */
  kind: string;
  /** Human label, e.g. the heading the block sits under. */
  label: string;
  change: ChangeKind;
}

export interface RevisionStats {
  added: number;
  removed: number;
  changes: RevisionChange[];
}

export interface RevisionSummary {
  revision_no: number;
  operation: RevisionOperation;
  author_type: AuthorType;
  summary: string;
  format: string;
  stats: RevisionStats;
  rendered_file_id: string | null;
  created_at: string;
}

export interface RevisionDetail extends RevisionSummary {
  document_id: string;
  source_format: SourceFormat;
  content: string;
  options: Record<string, unknown>;
  title: string | null;
  filename: string;
}

export interface DocumentSummary {
  document_id: string;
  kind: DocumentKind;
  title: string | null;
  filename: string;
  format: string;
  head_revision_no: number;
  thread_id: string | null;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  revisions: RevisionSummary[];
}

export interface FileDocumentRef {
  document_id: string;
  revision_no: number;
  head_revision_no: number;
}

export interface RenderedFileRef {
  file_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  download_url: string;
}

export interface RevisionMutationResponse {
  document: DocumentSummary;
  revision: RevisionSummary;
  file: RenderedFileRef;
  diagram_check: DiagramCheck;
}

export interface DiagramBlockDiagnostic {
  block_index: number;
  /** 1-based line in the whole document source. */
  document_line: number;
  /** 1-based line inside the Mermaid block, when known. */
  line: number | null;
  message: string;
}

/** The chat request's `document_context` body field. */
export interface DocumentContextRef {
  document_id: string;
  revision_no: number;
}
