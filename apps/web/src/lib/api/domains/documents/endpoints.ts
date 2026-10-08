import type { ExportFormat } from "@/lib/api/domains/documents/types";

// Served by the approved compatibility gateway src/app/api/[...path]/route.ts
// (agentsEndpoints.apiProxy → /api/v1/<segments>); no dedicated route needed.
const seg = (value: string | number) => encodeURIComponent(String(value));

export const documentsEndpoints = {
  getDocument: (documentId: string) =>
    ({
      method: "GET",
      browserPath: `/api/documents/${seg(documentId)}`,
      backend: {
        service: "agent",
        path: `/api/v1/documents/${seg(documentId)}`,
      },
    }) as const,
  getRevision: (documentId: string, revisionNo: number) =>
    ({
      method: "GET",
      browserPath: `/api/documents/${seg(documentId)}/revisions/${seg(
        revisionNo
      )}`,
      backend: {
        service: "agent",
        path: `/api/v1/documents/${seg(documentId)}/revisions/${seg(
          revisionNo
        )}`,
      },
    }) as const,
  getByFile: (fileId: string) =>
    ({
      method: "GET",
      browserPath: `/api/documents/by-file/${seg(fileId)}`,
      backend: {
        service: "agent",
        path: `/api/v1/documents/by-file/${seg(fileId)}`,
      },
    }) as const,
  createRevision: (documentId: string) =>
    ({
      method: "POST",
      browserPath: `/api/documents/${seg(documentId)}/revisions`,
      backend: {
        service: "agent",
        path: `/api/v1/documents/${seg(documentId)}/revisions`,
      },
    }) as const,
  restoreRevision: (documentId: string, revisionNo: number) =>
    ({
      method: "POST",
      browserPath: `/api/documents/${seg(documentId)}/revisions/${seg(
        revisionNo
      )}/restore`,
      backend: {
        service: "agent",
        path: `/api/v1/documents/${seg(documentId)}/revisions/${seg(
          revisionNo
        )}/restore`,
      },
    }) as const,
  exportRevision: (
    documentId: string,
    revisionNo: number,
    format: ExportFormat
  ) => {
    const query = new URLSearchParams({ format }).toString();
    return {
      method: "GET",
      browserPath: `/api/documents/${seg(documentId)}/revisions/${seg(
        revisionNo
      )}/export?${query}`,
      backend: {
        service: "agent",
        path: `/api/v1/documents/${seg(documentId)}/revisions/${seg(
          revisionNo
        )}/export?${query}`,
      },
    } as const;
  },
};
