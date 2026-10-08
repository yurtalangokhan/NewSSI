import { documentsEndpoints } from "@/lib/api/domains/documents/endpoints";
import type {
  DiagramBlockDiagnostic,
  DocumentDetail,
  ExportFormat,
  FileDocumentRef,
  RevisionDetail,
  RevisionMutationResponse,
} from "@/lib/api/domains/documents/types";
import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

export class RevisionConflictError extends Error {
  constructor(readonly headRevisionNo: number) {
    super(`document changed; head is draft ${headRevisionNo}`);
    this.name = "RevisionConflictError";
    // Keep `instanceof` working when TypeScript downlevels the class.
    Object.setPrototypeOf(this, RevisionConflictError.prototype);
  }
}

export class DiagramInvalidError extends Error {
  constructor(readonly diagnostics: DiagramBlockDiagnostic[]) {
    super(`${diagnostics.length} invalid diagram(s)`);
    this.name = "DiagramInvalidError";
    Object.setPrototypeOf(this, DiagramInvalidError.prototype);
  }
}

export class DocumentNoChangeError extends Error {
  constructor() {
    super("no change");
    this.name = "DocumentNoChangeError";
    Object.setPrototypeOf(this, DocumentNoChangeError.prototype);
  }
}

async function toFetchError(response: Response): Promise<FetchError> {
  const parsed = await parseApiErrorResponse(response);
  return new FetchError(
    parsed.userMessage,
    response.status,
    parsed.raw,
    parsed
  );
}

/** Domain rejections become typed errors; anything else stays a FetchError. */
async function toMutationError(response: Response): Promise<Error> {
  const error = await toFetchError(response);
  if (error.code === "document.revision_conflict") {
    return new RevisionConflictError(Number(error.details.head_revision_no));
  }
  if (error.code === "document.diagram_invalid") {
    return new DiagramInvalidError(
      (error.details.diagnostics as DiagramBlockDiagnostic[] | undefined) ?? []
    );
  }
  if (error.code === "document.no_change") return new DocumentNoChangeError();
  return error;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw await toFetchError(response);
  const body = await parseJsonResponse<T>(response);
  if (body === undefined) throw new Error("Unexpected empty response");
  return body;
}

export async function fetchAuthoredDocument(
  documentId: string
): Promise<DocumentDetail> {
  return readJson(
    await apiRequest(documentsEndpoints.getDocument(documentId).browserPath)
  );
}

export async function fetchRevision(
  documentId: string,
  revisionNo: number
): Promise<RevisionDetail> {
  return readJson(
    await apiRequest(
      documentsEndpoints.getRevision(documentId, revisionNo).browserPath
    )
  );
}

/** `null` means the file predates drafts (legacy, read-only). */
export async function fetchDocumentByFile(
  fileId: string
): Promise<FileDocumentRef | null> {
  const response = await apiRequest(
    documentsEndpoints.getByFile(fileId).browserPath
  );
  if (response.status === 404) return null;
  return readJson(response);
}

async function postJson(
  endpoint: { method: "POST"; browserPath: string },
  body: unknown
): Promise<RevisionMutationResponse> {
  const response = await apiRequest(endpoint.browserPath, {
    method: endpoint.method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await toMutationError(response);
  const parsed = await parseJsonResponse<RevisionMutationResponse>(response);
  if (parsed === undefined) throw new Error("Unexpected empty response");
  return parsed;
}

export interface SaveUserRevisionInput {
  baseRevisionNo: number;
  content: string;
  summary?: string;
}

export function saveUserRevision(
  documentId: string,
  { baseRevisionNo, content, summary = "" }: SaveUserRevisionInput
): Promise<RevisionMutationResponse> {
  return postJson(documentsEndpoints.createRevision(documentId), {
    base_revision_no: baseRevisionNo,
    content,
    summary,
  });
}

export function restoreRevision(
  documentId: string,
  revisionNo: number,
  baseRevisionNo: number
): Promise<RevisionMutationResponse> {
  return postJson(documentsEndpoints.restoreRevision(documentId, revisionNo), {
    base_revision_no: baseRevisionNo,
  });
}

export interface ExportedRevision {
  blob: Blob;
  filename: string;
}

function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const extended = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (extended) {
    try {
      return decodeURIComponent(extended[1]!.trim());
    } catch {
      // Fall through to the plain filename.
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1]!.trim() : null;
}

/**
 * Downloads a revision export through the shared transport (session refresh,
 * language header) and keeps the server's Content-Disposition filename.
 */
export async function exportRevision(
  documentId: string,
  revisionNo: number,
  format: ExportFormat
): Promise<ExportedRevision> {
  const response = await apiRequest(
    documentsEndpoints.exportRevision(documentId, revisionNo, format)
      .browserPath
  );
  if (!response.ok) throw await toFetchError(response);
  return {
    blob: await response.blob(),
    filename:
      filenameFromDisposition(response.headers.get("Content-Disposition")) ??
      `${documentId}-draft-${revisionNo}.${format}`,
  };
}
