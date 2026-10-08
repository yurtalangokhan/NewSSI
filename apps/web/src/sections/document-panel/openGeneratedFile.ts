import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import type { GeneratedFile } from "@/lib/api/domains/chat/streaming-types";
import { fetchDocumentByFile } from "@/lib/api/domains/documents/api";

/**
 * Opens a generated file where the UI can show drafts.
 *
 * Returns "fallback" when no document panel host is mounted (a shared chat),
 * so the caller can keep using the legacy modal.
 */
export async function openGeneratedFile(
  file: GeneratedFile,
  preferChanges: boolean
): Promise<"panel" | "fallback"> {
  const store = useDocumentPanelStore.getState();
  if (!store.hostMounted) return "fallback";

  const tabFor = (revisionNo: number) =>
    preferChanges && revisionNo > 1 ? "changes" : "preview";

  if (file.document_id && file.revision_no) {
    store.requestOpenDocument(
      file.document_id,
      file.revision_no,
      tabFor(file.revision_no)
    );
    return "panel";
  }

  // Packets from before drafts existed carry only the file; resolve it.
  const ref = await fetchDocumentByFile(file.file_id).catch(() => null);
  if (ref) {
    store.requestOpenDocument(
      ref.document_id,
      ref.revision_no,
      tabFor(ref.revision_no)
    );
  } else {
    store.requestOpenLegacyFile({
      fileId: file.file_id,
      filename: file.filename,
      mimeType: file.mime_type,
    });
  }
  return "panel";
}
