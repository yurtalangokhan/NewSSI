"use client";

import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import Dropzone from "react-dropzone";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { ThreeDotsLoader } from "@/components/Loading";
import { toast } from "@/hooks/useToast";
import {
  useDocuments,
  useDocumentChunks,
  uploadDocuments,
  deleteDocument,
  type RagDocument,
} from "@/lib/langconnect";
import { getDatasourceDetails, type ChunkInfo } from "@/lib/airbyte";
import {
  SvgFileText,
  SvgTrash,
  SvgChevronDownSmall,
  SvgChevronUpSmall,
  SvgUploadCloud,
} from "@opal/icons";
import { cn } from "@/lib/utils";
import SimpleTabs from "@/refresh-components/SimpleTabs";
import { SvgFiles, SvgGlobe, SvgPencilRuler } from "@opal/icons";
import WebCrawlPanel from "./WebCrawlPanel";
import TextInputPanel from "./TextInputPanel";

const ACCEPTED_TYPES = {
  "application/pdf": [".pdf"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
    ".docx",
  ],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation":
    [".pptx"],
  "text/csv": [".csv"],
  "text/tab-separated-values": [".tsv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
  "application/vnd.ms-excel": [".xls"],
  "text/plain": [".txt"],
  "text/markdown": [".md"],
  "text/html": [".html", ".htm"],
  "application/json": [".json"],
  "application/rtf": [".rtf"],
};

const MAX_SIZE_BYTES = 200 * 1024 * 1024; // 200 MB

// ---------------------------------------------------------------------------
// Chunk Viewer sub-component
// ---------------------------------------------------------------------------

function ChunkViewer({
  collectionId,
  documentId,
}: {
  collectionId: string;
  documentId: string;
}) {
  const { t } = useTranslation();
  const { chunks, stats, isLoading } = useDocumentChunks(
    collectionId,
    documentId
  );

  if (isLoading) {
    return (
      <div className="pt-2 pl-4">
        <ThreeDotsLoader />
      </div>
    );
  }

  return (
    <div className="pt-2 pl-4 flex flex-col gap-3">
      {stats && (
        <div className="flex items-center gap-4">
          <StatBadge
            label={t("admin.documentProcessing.chunkStats.chunks")}
            value={stats.total_chunks}
          />
          <StatBadge
            label={t("admin.documentProcessing.chunkStats.avgChars")}
            value={stats.avg_chars}
          />
          <StatBadge
            label={t("admin.documentProcessing.chunkStats.avgTokens")}
            value={stats.avg_tokens}
          />
        </div>
      )}
      <div className="flex flex-col gap-2 max-h-80 overflow-y-auto pr-1">
        {chunks.map((chunk, idx) => (
          <div
            key={chunk.id}
            className="rounded-08 border border-border-01 bg-background-neutral-01 p-3"
          >
            <div className="flex items-center gap-3 mb-1">
              <Text as="p" mainContentMuted text03 className="font-mono text-[10px]">
                {t("admin.documentProcessing.chunk", {
                  index: idx + 1,
                  defaultValue: "Chunk {{index}}",
                })}
              </Text>
              <Text as="p" mainContentMuted text03 className="font-mono text-[10px] opacity-60" title={chunk.id}>
                {t("admin.documentProcessing.chunkId", {
                  defaultValue: "ID",
                })}
                : {chunk.id}
              </Text>
              {chunk.metadata?.char_count != null && (
                <StatBadge label={t("admin.documentProcessing.chunkStats.chars")} value={chunk.metadata.char_count as number} />
              )}
              {chunk.metadata?.token_count != null && (
                <StatBadge label={t("admin.documentProcessing.chunkStats.tokens")} value={chunk.metadata.token_count as number} />
              )}
            </div>
            <Text
              as="p"
              mainContentBody
              text04
              className="whitespace-pre-wrap break-words text-sm leading-relaxed"
            >
              {chunk.content}
            </Text>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatBadge({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border-01 px-2.5 py-0.5">
      <Text as="span" mainContentMuted text03 className="text-xs">
        {label}
      </Text>
      <Text as="span" mainUiAction text04 className="text-xs font-semibold">
        {value}
      </Text>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Document row
// ---------------------------------------------------------------------------

function DocumentRow({
  doc,
  collectionId,
  onDelete,
  isCollectionMutationLocked,
  readOnly = false,
}: {
  doc: RagDocument;
  collectionId: string;
  onDelete: () => void;
  isCollectionMutationLocked: boolean;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const fileName =
    (doc.metadata?.filename as string) ||
    (doc.metadata?.title as string) ||
    (doc.metadata?.source as string) ||
    doc.id;

  async function handleDelete() {
    if (readOnly) {
      toast.warning(
        t("admin.documentProcessing.datasourceReadOnlyActionsBlocked", {
          defaultValue:
            "Airbyte datasource koleksiyonlarında dosya silme işlemi yapılamaz.",
        })
      );
      return;
    }
    if (isCollectionMutationLocked) {
      toast.warning(
        t("admin.documentProcessing.collectionMutationLocked", {
          defaultValue:
            "Graph RAG build devam ederken bu koleksiyon üzerinde değişiklik yapılamaz.",
        })
      );
      return;
    }

    const confirmed = window.confirm(
      t("admin.documentProcessing.deleteDocumentConfirm", {
        name: fileName,
        defaultValue: 'Delete document "{{name}}"?',
      })
    );
    if (!confirmed) return;
    setIsDeleting(true);
    try {
      await deleteDocument(collectionId, doc.id);
      toast.success(t("admin.documentProcessing.documentDeleted"));
      onDelete();
    } catch (e) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.documentProcessing.deleteDocumentFailed")
      );
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div className="rounded-08 border border-border-01 overflow-hidden">
      <div className="flex items-center gap-3 px-3 py-2.5">
        <SvgFileText className="h-4 w-4 shrink-0 stroke-text-03" aria-hidden />
        <div className="flex-1 min-w-0">
          <Text
            as="p"
            mainUiAction
            text04
            className="truncate text-sm"
          >
            {fileName}
          </Text>
          {doc.created_at && (
            <Text as="p" mainContentMuted text03 className="text-xs mt-0.5">
              {new Date(doc.created_at).toLocaleString()}
            </Text>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            tertiary
            size="md"
            leftIcon={expanded ? SvgChevronUpSmall : SvgChevronDownSmall}
            onClick={() => setExpanded((v) => !v)}
            aria-label={
              expanded
                ? t("admin.documentProcessing.collapseChunks", {
                    defaultValue: "Collapse chunks",
                  })
                : t("admin.documentProcessing.viewChunks", {
                    defaultValue: "View chunks",
                  })
            }
          >
            {t("admin.documentProcessing.chunks")}
          </Button>
          <Button
            danger
            size="md"
            onClick={handleDelete}
            disabled={isDeleting || isCollectionMutationLocked || readOnly}
            aria-label={t("admin.documentProcessing.deleteDocumentAria", {
              defaultValue: "Delete document",
            })}
            className="!px-2"
          >
            <SvgTrash className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border-01 bg-background-neutral-01 px-3 py-3">
          <ChunkViewer collectionId={collectionId} documentId={doc.id} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DocumentsPanel
// ---------------------------------------------------------------------------

interface DocumentsPanelProps {
  collectionId: string | null;
  readOnly?: boolean;
  isCollectionMutationLocked?: boolean;
}

export default function DocumentsPanel({
  collectionId,
  readOnly = false,
  isCollectionMutationLocked = false,
}: DocumentsPanelProps) {
  const { t } = useTranslation();
  // readOnly = Airbyte connector koleksiyonu; chunks agent-service'ten gelir, rag-service'e istek atma
  const { documents, isLoading, mutate } = useDocuments(readOnly ? null : collectionId);
  const [datasourceChunks, setDatasourceChunks] = useState<ChunkInfo[]>([]);
  const [isDatasourceChunksLoading, setIsDatasourceChunksLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadDatasourceChunks() {
      if (!readOnly || !collectionId) {
        setDatasourceChunks([]);
        return;
      }
      setIsDatasourceChunksLoading(true);
      try {
        const details = await getDatasourceDetails(collectionId, 1, 50);
        if (!cancelled) {
          setDatasourceChunks(details.chunks ?? []);
        }
      } catch (e) {
        if (!cancelled) {
          setDatasourceChunks([]);
          toast.error(
            e instanceof Error
              ? e.message
              : t("admin.documentProcessing.loadDatasourceChunksFailed", {
                  defaultValue: "Datasource chunk bilgisi alınamadı.",
                })
          );
        }
      } finally {
        if (!cancelled) {
          setIsDatasourceChunksLoading(false);
        }
      }
    }
    loadDatasourceChunks();
    return () => {
      cancelled = true;
    };
  }, [collectionId, readOnly]);

  const handleDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!collectionId || acceptedFiles.length === 0) return;
      if (isCollectionMutationLocked) {
        toast.warning(
          t("admin.documentProcessing.collectionMutationLocked", {
            defaultValue:
              "Graph RAG build devam ederken bu koleksiyon üzerinde değişiklik yapılamaz.",
          })
        );
        return;
      }

      setIsUploading(true);
      try {
        const metadatas = acceptedFiles.map((f) => ({ filename: f.name }));
        const result = await uploadDocuments(collectionId, acceptedFiles, metadatas);
        await mutate();
        toast.success(
          t("admin.documentProcessing.uploadSuccess", {
            count: acceptedFiles.length,
            defaultValue: `${acceptedFiles.length} dosya başarıyla yüklendi.`,
          })
        );
        if (result.warnings) {
          toast.warning(result.warnings);
        }
      } catch (e) {
        toast.error(
          e instanceof Error ? e.message : t("admin.documentProcessing.uploadFailed")
        );
      } finally {
        setIsUploading(false);
      }
    },
    [collectionId, isCollectionMutationLocked, mutate, t]
  );

  if (!collectionId) {
    return (
      <CardSection>
        <Text as="p" mainContentMuted text03 className="text-center py-6">
          {t("admin.documentProcessing.selectCollectionToManageDocuments")}
        </Text>
      </CardSection>
    );
  }

  function renderDatasourceChunks() {
    if (isDatasourceChunksLoading) return <ThreeDotsLoader />;
    if (datasourceChunks.length === 0) {
      return (
        <Text as="p" mainContentMuted text03 className="text-center py-6">
          {t("admin.documentProcessing.noChunks", {
            defaultValue: "Bu datasource icin görüntülenecek chunk bulunamadı.",
          })}
        </Text>
      );
    }
    return (
      <div className="flex flex-col gap-2">
        {datasourceChunks.map((chunk, idx) => {
          const chunkId = String(chunk.metadata?.chunk_id ?? idx + 1);
          return (
            <div
              key={`${chunkId}-${idx}`}
              className="rounded-08 border border-border-01 bg-background-neutral-01 p-3"
            >
              <div className="mb-1 flex items-center gap-3">
                <Text as="p" mainContentMuted text03 className="font-mono text-[10px]">
                  {t("admin.documentProcessing.chunk", {
                    index: idx + 1,
                    defaultValue: "Chunk {{index}}",
                  })}
                </Text>
                <StatBadge
                  label={t("admin.documentProcessing.chunkStats.chars")}
                  value={chunk.char_count ?? chunk.content.length}
                />
                <StatBadge
                  label={t("admin.documentProcessing.chunkStats.tokens")}
                  value={
                    chunk.token_count ??
                    Math.max(chunk.content.split(/\s+/).length, Math.floor(chunk.content.length / 4))
                  }
                />
              </div>
              <Text
                as="p"
                mainContentBody
                text04
                className="whitespace-pre-wrap break-words text-sm leading-relaxed"
              >
                {chunk.content}
              </Text>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Upload section — Belge / Web tabs (hidden for read-only datasource collections) */}
      {!readOnly && !isCollectionMutationLocked && (
        <SimpleTabs
          tabs={SimpleTabs.generateTabs({
            document: {
              name: t("admin.documentProcessing.tabs.document", {
                defaultValue: "Belge",
              }),
              icon: SvgFiles,
              content: (
                <CardSection className="flex flex-col gap-3">
                  <Text
                    as="p"
                    mainContentBody
                    text04
                    className="leading-relaxed"
                  >
                    {t("admin.documentProcessing.supportedFormats")}
                  </Text>

                  <Dropzone
                    onDrop={handleDrop}
                    onDragEnter={() => setIsDragActive(true)}
                    onDragLeave={() => setIsDragActive(false)}
                    accept={ACCEPTED_TYPES}
                    maxSize={MAX_SIZE_BYTES}
                    multiple
                    disabled={isUploading}
                    onDropRejected={(rejections) => {
                      const reason =
                        rejections[0]?.errors[0]?.message ?? "File rejected";
                      toast.error(reason);
                    }}
                  >
                    {({ getRootProps, getInputProps }) => (
                      <div
                        {...getRootProps()}
                        className={cn(
                          "flex flex-col items-center justify-center gap-3",
                          "rounded-08 border-2 border-dashed",
                          "px-6 py-10 cursor-pointer transition-colors",
                          isDragActive
                            ? "border-action-primary bg-background-neutral-02"
                            : "border-border-01 bg-background-neutral-01 hover:border-action-primary hover:bg-background-neutral-02",
                          isUploading && "opacity-60 cursor-not-allowed"
                        )}
                      >
                        <input {...getInputProps()} />
                        {isUploading ? (
                          <>
                            <ThreeDotsLoader />
                            <Text as="p" mainContentMuted text03>
                              {t(
                                "admin.documentProcessing.uploadingAndProcessing"
                              )}
                            </Text>
                          </>
                        ) : (
                          <>
                            <SvgUploadCloud
                              className={cn(
                                "h-8 w-8 transition-colors",
                                isDragActive
                                  ? "stroke-action-primary"
                                  : "stroke-text-03"
                              )}
                              aria-hidden
                            />
                            <div className="text-center">
                              <Text as="p" mainUiAction text04>
                                {isDragActive
                                  ? t(
                                      "admin.documentProcessing.dropFilesHere"
                                    )
                                  : t(
                                      "admin.documentProcessing.dragDropOrClick"
                                    )}
                              </Text>
                              <Text
                                as="p"
                                mainContentMuted
                                text03
                                className="mt-1 text-xs"
                              >
                                {t(
                                  "admin.documentProcessing.supportedFormatsCompact"
                                )}
                              </Text>
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </Dropzone>
                </CardSection>
              ),
            },
            text: {
              name: t("admin.documentProcessing.tabs.text", {
                defaultValue: "Metin",
              }),
              icon: SvgPencilRuler,
              content: (
                <TextInputPanel
                  collectionId={collectionId}
                  onDocumentAdded={() => mutate()}
                />
              ),
            },
            web: {
              name: t("admin.documentProcessing.tabs.web", {
                defaultValue: "Web",
              }),
              icon: SvgGlobe,
              content: (
                <WebCrawlPanel
                  collectionId={collectionId}
                  onDocumentAdded={() => mutate()}
                />
              ),
            },
          })}
          defaultValue="document"
        />
      )}

      {isCollectionMutationLocked && (
        <CardSection className="flex flex-col gap-2 border border-status-warning-05/30 bg-status-warning-05/5">
          <Text as="p" mainUiAction text04>
            {t("admin.documentProcessing.collectionMutationLocked", {
              defaultValue:
                "Graph RAG build devam ederken bu koleksiyon üzerinde değişiklik yapılamaz.",
            })}
          </Text>
          <Text as="p" mainContentMuted text03>
            {t("admin.documentProcessing.collectionMutationLockedDescription", {
              defaultValue:
                "Build tamamlandıktan sonra belge ekleme/silme ve koleksiyon düzenleme işlemleri tekrar açılacaktır.",
            })}
          </Text>
        </CardSection>
      )}
      {/* Document list */}
      <CardSection className="flex flex-col gap-3">
        <Text as="p" headingH3 text05 className="border-b border-border-01 pb-2">
          {readOnly
            ? t("admin.documentProcessing.chunks", { defaultValue: "Chunks" })
            : t("admin.documentProcessing.documents")}{" "}
          {readOnly ? (
            !isDatasourceChunksLoading && (
              <span className="font-normal text-text-03">({datasourceChunks.length})</span>
            )
          ) : (
            !isLoading && (
              <span className="font-normal text-text-03">({documents.length})</span>
            )
          )}
        </Text>

        {readOnly ? renderDatasourceChunks() : isLoading ? (
          <ThreeDotsLoader />
        ) : documents.length === 0 ? (
          <Text as="p" mainContentMuted text03 className="text-center py-6">
            {t("admin.documentProcessing.noDocuments")}
          </Text>
        ) : (
          <div className="flex flex-col gap-2">
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                collectionId={collectionId}
                onDelete={() => mutate()}
                isCollectionMutationLocked={isCollectionMutationLocked}
                readOnly={readOnly}
              />
            ))}
          </div>
        )}
      </CardSection>
    </div>
  );
}
