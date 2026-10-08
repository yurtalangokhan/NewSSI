"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchChatFile } from "@/lib/api/domains/chat/api";
import { getCodeLanguage, getDataLanguage } from "@/lib/languages";
import { MinimalAtlasDocument } from "@/lib/search/interfaces";
import {
  PreviewContext,
  PreviewVariant,
} from "@/sections/modals/PreviewModal/interfaces";
import { resolveVariant } from "@/sections/modals/PreviewModal/variants";

function getFilenameFromContentDisposition(
  header: string | null
): string | null {
  if (!header) return null;
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const standardMatch = header.match(/filename="?([^";]+)"?/i);
  if (standardMatch && standardMatch[1]) {
    return standardMatch[1].trim();
  }
  return null;
}

function resolveMimeType(mimeType: string, fileName: string): string {
  if (mimeType && mimeType !== "application/octet-stream") return mimeType;
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".md") || lower.endsWith(".markdown"))
    return "text/markdown";
  if (lower.endsWith(".txt")) return "text/plain";
  if (lower.endsWith(".csv")) return "text/csv";
  if (lower.endsWith(".docx") || lower.endsWith(".doc"))
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  return mimeType || "application/octet-stream";
}

export interface PreviewFileState {
  variant: PreviewVariant;
  ctx: PreviewContext;
  isLoading: boolean;
  loadError: string | null;
}

/** Fetch + variant resolution shared by PreviewModal and the panel's legacy mode. */
export function usePreviewFile(
  presentingDocument: MinimalAtlasDocument
): PreviewFileState {
  const { t } = useTranslation();
  const [fileContent, setFileContent] = useState("");
  const [fileBlob, setFileBlob] = useState<Blob | null>(null);
  const [fileUrl, setFileUrl] = useState("");
  const [fileName, setFileName] = useState(
    presentingDocument.semantic_identifier || ""
  );
  const [isLoading, setIsLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [mimeType, setMimeType] = useState(
    presentingDocument.preview_mime_type || "application/octet-stream"
  );
  const [zoom, setZoom] = useState(100);

  const docId = presentingDocument.document_id;
  const docName = presentingDocument.semantic_identifier;
  const docPreviewUrl = presentingDocument.preview_url;
  const docPreviewMimeType = presentingDocument.preview_mime_type;

  const effectiveFileName = fileName || docName || "";

  const variant = useMemo(
    () => resolveVariant(effectiveFileName, mimeType),
    [effectiveFileName, mimeType]
  );

  const language = useMemo(
    () =>
      getCodeLanguage(effectiveFileName) ||
      getDataLanguage(effectiveFileName) ||
      "plaintext",
    [effectiveFileName]
  );

  const lineCount = useMemo(() => {
    if (!fileContent) return 0;
    return fileContent.split("\n").length;
  }, [fileContent]);

  const fileSize = useMemo(() => {
    if (!fileContent) return "";
    const bytes = new TextEncoder().encode(fileContent).length;
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(2)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(2)} MB`;
  }, [fileContent]);

  useEffect(() => {
    let isCancelled = false;

    const runFetch = async () => {
      setIsLoading(true);
      setLoadFailed(false);
      setFileContent("");
      setFileBlob(null);

      // For files not persisted yet (e.g. image chosen in input, not sent yet),
      // render directly from inline data URL and skip backend fetch.
      if (
        docPreviewUrl &&
        (docPreviewUrl.startsWith("data:") || docPreviewUrl.startsWith("blob:"))
      ) {
        if (!isCancelled) {
          setFileUrl(docPreviewUrl);
          setFileName(docName || "document");
          setMimeType(docPreviewMimeType || "application/octet-stream");
          setIsLoading(false);
        }
        return;
      }

      const fileIdLocal = docId.split("__")[1] || docId;

      try {
        const response = await fetchChatFile(fileIdLocal);

        const blob = await response.blob();
        if (isCancelled) return;

        setFileBlob(blob);
        const url = window.URL.createObjectURL(blob);
        if (!isCancelled) {
          setFileUrl((prev) => {
            if (prev && prev.startsWith("blob:"))
              window.URL.revokeObjectURL(prev);
            return url;
          });

          const dispositionFilename = getFilenameFromContentDisposition(
            response.headers.get("Content-Disposition")
          );
          const originalFileName =
            docName && !docName.startsWith("image-")
              ? docName
              : dispositionFilename || docName || "document";
          setFileName(originalFileName);

          const rawContentType =
            response.headers.get("Content-Type") || "application/octet-stream";
          const resolvedMime = resolveMimeType(
            rawContentType,
            originalFileName
          );
          setMimeType(resolvedMime);

          const resolved = resolveVariant(originalFileName, resolvedMime);
          if (resolved.needsTextContent) {
            setFileContent(await blob.text());
          }
        }
      } catch {
        if (!isCancelled) {
          setLoadFailed(true);
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    runFetch();

    return () => {
      isCancelled = true;
    };
  }, [docId, docName, docPreviewUrl, docPreviewMimeType]);

  useEffect(() => {
    return () => {
      if (fileUrl?.startsWith("blob:")) window.URL.revokeObjectURL(fileUrl);
    };
  }, [fileUrl]);

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 25, 200));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 25, 25));

  const ctx: PreviewContext = useMemo(
    () => ({
      fileContent,
      fileBlob,
      fileUrl,
      fileName: effectiveFileName,
      language,
      lineCount,
      fileSize,
      zoom,
      onZoomIn: handleZoomIn,
      onZoomOut: handleZoomOut,
      t,
    }),
    [
      fileContent,
      fileBlob,
      fileUrl,
      effectiveFileName,
      language,
      lineCount,
      fileSize,
      zoom,
      t,
    ]
  );

  // Translated at read time so a language change never refetches the file.
  const loadError = loadFailed ? t("filePreview.failedToLoadDocument") : null;
  return { variant, ctx, isLoading, loadError };
}
