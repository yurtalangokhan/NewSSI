"use client";

import { useState, useEffect, useMemo } from "react";
import Button from "@/refresh-components/buttons/Button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { Button as OpalButton } from "@opal/components";
import Modal, { BasicModalFooter } from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import {
  SvgDownloadCloud,
  SvgFileText,
  SvgZoomIn,
  SvgZoomOut,
} from "@opal/icons";
import PreviewImage from "@/refresh-components/PreviewImage";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import ScrollIndicatorDiv from "@/refresh-components/ScrollIndicatorDiv";
import { cn } from "@/lib/utils";
import { Section } from "@/layouts/general-layouts";
import DocxPreview from "@/app/app/components/files/DocxPreview";
import { useTranslation } from "react-i18next";

interface TextViewProps {
  presentingDocument: MinimalOnyxDocument;
  onClose: () => void;
}

const isMarkdownFormat = (fileType: string) => {
  return (
    fileType.startsWith("text/markdown") ||
    fileType.startsWith("text/plain") ||
    fileType.startsWith("text/csv") ||
    fileType.startsWith("application/json")
  );
};

const isJsonFormat = (fileType: string) => {
  return fileType.startsWith("application/json");
};

const isSupportedIframeFormat = (fileType: string) => {
  return fileType.startsWith("application/pdf");
};

const isWordFormat = (fileType: string) =>
  fileType.startsWith(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  );

const isImageFormat = (fileType: string) => fileType.startsWith("image/");
const isJsonFormat = (mimeType: string) =>
  mimeType.startsWith("application/json");

const isPptxFormat = (fileType: string) =>
  fileType.startsWith(
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
  );
const isImageFormat = (mimeType: string) =>
  ["image/png", "image/jpeg", "image/gif", "image/svg+xml"].some((f) =>
    mimeType.startsWith(f)
  );

const isSupportedIframeFormat = (mimeType: string) =>
  [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/svg+xml",
  ].some((f) => mimeType.startsWith(f));

export default function TextViewModal({
  presentingDocument,
  onClose,
}: TextViewProps) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState(100);
  const [fileContent, setFileContent] = useState("");
  const [fileBlob, setFileBlob] = useState<Blob | null>(null);
  const [fileUrl, setFileUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fileType, setFileType] = useState("application/octet-stream");

  const docId = presentingDocument.document_id;
  const docName = presentingDocument.semantic_identifier;
  const docPreviewUrl = presentingDocument.preview_url;
  const docPreviewMimeType = presentingDocument.preview_mime_type;

  const csvData = useMemo(() => {
    if (!fileType.startsWith("text/csv")) return null;
    const lines = fileContent.split(/\r?\n/).filter((l) => l.length > 0);
    const headers = lines.length > 0 ? lines[0]?.split(",") ?? [] : [];
    const rows = lines.slice(1).map((line) => line.split(","));
    return { headers, rows } as { headers: string[]; rows: string[][] };
  }, [fileContent, fileType]);

  const jsonContent = useMemo(() => {
    if (!isJsonFormat(fileType)) return null;
    try {
      return JSON.stringify(JSON.parse(fileContent), null, 2);
    } catch {
      return fileContent;
    }
  }, [fileContent, fileType]);

  useEffect(() => {
    let isCancelled = false;
    const controller = new AbortController();

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
          setFileUrl((prev) => {
            if (prev && prev.startsWith("blob:")) window.URL.revokeObjectURL(prev);
            return docPreviewUrl;
          });
          setFileName(docName || t("filePreview.document"));
          setFileType(docPreviewMimeType || "application/octet-stream");
          setIsLoading(false);
        }
        return;
      }

      const fileIdLocal = docId.split("__")[1] || docId;

      try {
        const response = await fetch(
          `/api/chat/file/${encodeURIComponent(fileIdLocal)}`,
          { method: "GET", signal: controller.signal }
        );

        if (!response.ok) {
          if (!isCancelled) {
            setLoadError(t("filePreview.failedToLoadDocument"));
          }
          return;
        }

        const blob = await response.blob();
        if (isCancelled) return;

        const url = window.URL.createObjectURL(blob);
        if (!isCancelled) {
          setFileUrl((prev) => {
            if (prev && prev.startsWith("blob:")) window.URL.revokeObjectURL(prev);
            return url;
          });

          const originalFileName = docName || t("filePreview.document");
          setFileName(originalFileName);

          let contentType =
            response.headers.get("Content-Type") || "application/octet-stream";

          if (contentType === "application/octet-stream") {
            const lowerName = originalFileName.toLowerCase();
            if (lowerName.endsWith(".md") || lowerName.endsWith(".markdown")) {
              contentType = "text/markdown";
            } else if (lowerName.endsWith(".txt")) {
              contentType = "text/plain";
            } else if (lowerName.endsWith(".csv")) {
              contentType = "text/csv";
            } else if (lowerName.endsWith(".json")) {
              contentType = "application/json";
            } else if (
            lowerName.endsWith(".docx") ||
            lowerName.endsWith(".doc")
          ) {
              contentType =
               
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
            } else if (
            lowerName.endsWith(".pptx") ||
            lowerName.endsWith(".ppt")
          ) {
              contentType =
               
              "application/vnd.openxmlformats-officedocument.presentationml.presentation";
            }
          }
          setFileType(contentType);

          if (isMarkdownFormat(contentType)) {
            setFileContent(await blob.text());
          } else if (isWordFormat(contentType)) {
            // Pass blob directly to DocxPreview for visual rendering
            setFileBlob(blob);
          } else if (isPptxFormat(contentType)) {
            // Extract text slide-by-slide from backend
            const textResponse = await fetch(
              `/api/chat/file/${encodeURIComponent(fileIdLocal)}/text`,
              { method: "GET", signal: controller.signal }
            );
            if (textResponse.ok && !isCancelled) {
              setFileContent(await textResponse.text());
              setFileType("text/plain");
            }
          }
        }
      } catch (error) {
        if (!isCancelled) {
          setLoadError(t("filePreview.failedToLoadDocument"));
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
      controller.abort();
    };
  }, [docId, docName, docPreviewUrl, docPreviewMimeType, t]);

  useEffect(() => {
    return () => {
      if (fileUrl && fileUrl.startsWith("blob:")) {
        window.URL.revokeObjectURL(fileUrl);
      }
    };
  }, [fileUrl]);

  const handleDownload = () => {
    const link = document.createElement("a");
    link.href = fileUrl;
    link.download = fileName || presentingDocument.document_id;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 25, 200));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 25, 100));

  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal.Content
        width="lg"
        height="full"
        preventAccidentalClose={false}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <Modal.Header
          icon={SvgFileText}
          title={fileName || t("filePreview.document")}
          onClose={onClose}
        >
          <Section flexDirection="row" justifyContent="start" gap={0.25}>
            <OpalButton
              prominence="tertiary"
              onClick={handleZoomOut}
              icon={SvgZoomOut}
              tooltip={t("filePreview.zoomOut")}
            />
            <Text mainUiBody>{zoom}%</Text>
            <OpalButton
              prominence="tertiary"
              onClick={handleZoomIn}
              icon={SvgZoomIn}
              tooltip={t("filePreview.zoomIn")}
            />
            <OpalButton
              prominence="tertiary"
              onClick={handleDownload}
              icon={SvgDownloadCloud}
              tooltip={t("filePreview.download")}
            />
          </Section>
        </Modal.Header>

        <Modal.Body>
          <Section>
            {isLoading ? (
              <SimpleLoader className="h-8 w-8" />
            ) : loadError ? (
              <Text text03 mainUiBody>
                {loadError}
              </Text>
            ) : (
              <div
                className="flex flex-col flex-1 min-h-0 min-w-0 w-full transform origin-center transition-transform duration-300 ease-in-out"
                style={{ transform: `scale(${zoom / 100})` }}
              >
                {isWordFormat(fileType) && fileBlob ? (
                  <ScrollIndicatorDiv
                    className="flex-1 min-h-0"
                    variant="shadow"
                  >
                    <DocxPreview blob={fileBlob} className="w-full" />
                  </ScrollIndicatorDiv>
                ) : isImageFormat(fileType) ? (
                  <PreviewImage
                    src={fileUrl}
                    alt={fileName}
                    className="w-full flex-1 min-h-0"
                  />
                ) : isSupportedIframeFormat(fileType) ? (
                  <iframe
                    src={`${fileUrl}#toolbar=0`}
                    className="w-full h-full flex-1 min-h-0 border-none"
                    title={t("filePreview.fileViewer")}
                  />
                ) : isMarkdownFormat(fileType) ? (
                  <ScrollIndicatorDiv
                    className="flex-1 min-h-0 p-4"
                    variant="shadow"
                  >
                    {csvData ? (
                      <Table>
                        <TableHeader className="sticky top-0 z-sticky">
                          <TableRow className="bg-background-tint-02">
                            {csvData.headers.map((h, i) => (
                              <TableHead key={i}>
                                <Text
                                  as="p"
                                  className="line-clamp-2 font-medium"
                                  text03
                                  mainUiBody
                                >
                                  {h}
                                </Text>
                              </TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {csvData.rows.map((row, rIdx) => (
                            <TableRow key={rIdx}>
                              {csvData.headers.map((_, cIdx) => (
                                <TableCell
                                  key={cIdx}
                                  className={cn(
                                    cIdx === 0 &&
                                      "sticky left-0 bg-background-tint-01",
                                    "py-0 px-4 whitespace-normal break-words"
                                  )}
                                >
                                  {row?.[cIdx] ?? ""}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    ) : jsonContent !== null ? (
                      <MinimalMarkdown
                        content={`\`\`\`json\n${jsonContent}\n\`\`\``}
                        className="w-full pb-4 h-full text-lg break-words"
                      />
                    ) : (
                      <MinimalMarkdown
                        content={fileContent}
                        className="w-full pb-4 h-full text-lg break-words"
                      />
                    )}
                  </ScrollIndicatorDiv>
                ) : (
                  <div className="flex flex-col items-center justify-center flex-1 min-h-0 p-6 gap-4">
                    <Text as="p" text03 mainUiBody>
                      {t("filePreview.unsupportedPreview")}
                    </Text>
                    <Button onClick={handleDownload}>
                      {t("filePreview.downloadFile")}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Section>
        </Modal.Body>

        <Modal.Footer>
          <BasicModalFooter
            submit={
              <Button onClick={handleDownload}>
                {t("filePreview.downloadFile")}
              </Button>
            }
          />
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
