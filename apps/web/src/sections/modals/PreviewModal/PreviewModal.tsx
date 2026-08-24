"use client";

import { useState, useEffect, useMemo } from "react";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import { cn } from "@/lib/utils";
import { Section } from "@/layouts/general-layouts";
import { getCodeLanguage, getDataLanguage } from "@/lib/languages";
import { fetchChatFile } from "@/lib/chat/svc";
import { PreviewContext } from "@/sections/modals/PreviewModal/interfaces";
import { resolveVariant } from "@/sections/modals/PreviewModal/variants";
import { useTranslation } from "react-i18next";

function getFilenameFromContentDisposition(header: string | null): string | null {
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

interface PreviewModalProps {
  presentingDocument: MinimalOnyxDocument;
  onClose: () => void;
}

export default function PreviewModal({
  presentingDocument,
  onClose,
}: PreviewModalProps) {
  const { t } = useTranslation();
  const [fileContent, setFileContent] = useState("");
  const [fileBlob, setFileBlob] = useState<Blob | null>(null);
  const [fileUrl, setFileUrl] = useState("");
  const [fileName, setFileName] = useState(
    presentingDocument.semantic_identifier || ""
  );
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
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
      setLoadError(null);
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
            if (prev && prev.startsWith("blob:")) window.URL.revokeObjectURL(prev);
            return url;
          });

          const dispositionFilename = getFilenameFromContentDisposition(
            response.headers.get("Content-Disposition")
          );
          const originalFileName =
            (docName && !docName.startsWith("image-"))
              ? docName
              : dispositionFilename ||
                docName ||
                "document";
          setFileName(originalFileName);

          const rawContentType =
            response.headers.get("Content-Type") || "application/octet-stream";
          const resolvedMime = resolveMimeType(rawContentType, originalFileName);
          setMimeType(resolvedMime);

          const resolved = resolveVariant(originalFileName, resolvedMime);
          if (resolved.needsTextContent) {
            setFileContent(await blob.text());
          }
        }
      } catch {
        if (!isCancelled) {
          setLoadError("Failed to load document.");
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

  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal.Content
        width={variant.width}
        height={variant.height}
        preventAccidentalClose={false}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <Modal.Header
          title={effectiveFileName || "Document"}
          description={variant.headerDescription(ctx)}
          onClose={onClose}
        />

        {/* Body + floating footer wrapper */}
        <Modal.Body padding={0} gap={0}>
          <Section padding={0} gap={0}>
            {isLoading ? (
              <Section>
                <SimpleLoader className="h-8 w-8" />
              </Section>
            ) : loadError ? (
              <Section padding={1}>
                <Text text03 mainUiBody>
                  {loadError}
                </Text>
              </Section>
            ) : (
              variant.renderContent(ctx)
            )}
          </Section>
        </Modal.Body>

        {/* Floating footer */}
        {!isLoading && !loadError && (
          <div
            className={cn(
              "absolute bottom-0 left-0 right-0",
              "flex items-center justify-between",
              "p-4 pointer-events-none w-full"
            )}
            style={{
              background:
                "linear-gradient(to top, var(--background-tint-01) 40%, transparent)",
            }}
          >
            {/* Left slot */}
            <div className="pointer-events-auto">
              {variant.renderFooterLeft(ctx)}
            </div>

            {/* Right slot */}
            <div className="pointer-events-auto rounded-12 bg-background-tint-00 p-1 shadow-lg">
              {variant.renderFooterRight(ctx)}
            </div>
          </div>
        )}
      </Modal.Content>
    </Modal>
  );
}
