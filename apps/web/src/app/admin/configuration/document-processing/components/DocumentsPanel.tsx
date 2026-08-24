"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import Dropzone from "react-dropzone";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { ThreeDotsLoader } from "@/components/Loading";
import { toast } from "@/hooks/useToast";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import {
  useDocuments,
  useDocumentChunks,
  useUploadStatus,
  startUploadJob,
  fetchUploadStatus,
  deleteDocument,
  type RagDocument,
  type UploadProgress,
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
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [
    ".pptx",
  ],
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
  const { chunks, stats, isLoading, isLoadingMore, hasMore, loadMore } =
    useDocumentChunks(collectionId, documentId);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const loadMoreRef = useRef(loadMore);
  loadMoreRef.current = loadMore;

  useEffect(() => {
    if (!hasMore || isLoadingMore) return;
    const sentinel = sentinelRef.current;
    const root = scrollContainerRef.current;
    if (!sentinel || !root) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          loadMoreRef.current();
        }
      },
      { root, threshold: 0 }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore]);

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
      <div
        ref={scrollContainerRef}
        className="flex flex-col gap-2 max-h-80 overflow-y-auto pr-1"
      >
        {chunks.map((chunk, idx) => (
          <div
            key={chunk.id}
            className="rounded-08 border border-border-01 bg-background-neutral-01 p-3"
          >
            <div className="flex items-center gap-3 mb-1">
              <Text
                as="p"
                mainContentMuted
                text03
                className="font-mono text-[10px]"
              >
                {t("admin.documentProcessing.chunk", {
                  index: idx + 1,
                  defaultValue: "Chunk {{index}}",
                })}
              </Text>
              <Text
                as="p"
                mainContentMuted
                text03
                className="font-mono text-[10px] opacity-60"
                title={chunk.id}
              >
                {t("admin.documentProcessing.chunkId", {
                  defaultValue: "ID",
                })}
                : {chunk.id}
              </Text>
              {chunk.metadata?.char_count != null && (
                <StatBadge
                  label={t("admin.documentProcessing.chunkStats.chars")}
                  value={chunk.metadata.char_count as number}
                />
              )}
              {chunk.metadata?.token_count != null && (
                <StatBadge
                  label={t("admin.documentProcessing.chunkStats.tokens")}
                  value={chunk.metadata.token_count as number}
                />
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
        {hasMore && (
          <div ref={sentinelRef} className="flex justify-center py-2">
            {isLoadingMore && <ThreeDotsLoader />}
          </div>
        )}
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
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const fileName =
    (doc.metadata?.filename as string) ||
    (doc.metadata?.title as string) ||
    (doc.metadata?.source as string) ||
    doc.id;

  function handleDeleteClick() {
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
    setShowDeleteModal(true);
  }

  async function handleDeleteConfirm() {
    setShowDeleteModal(false);
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
          <Text as="p" mainUiAction text04 className="truncate text-sm">
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
            onClick={handleDeleteClick}
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

      {showDeleteModal && (
        <ConfirmEntityModal
          danger
          entityType={t("admin.documentProcessing.documentEntity", {
            defaultValue: "Document",
          })}
          entityName={fileName}
          onClose={() => setShowDeleteModal(false)}
          onSubmit={handleDeleteConfirm}
        />
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
  const { documents, isLoading, mutate } = useDocuments(
    readOnly ? null : collectionId
  );
  const [datasourceChunks, setDatasourceChunks] = useState<ChunkInfo[]>([]);
  const [isDatasourceChunksLoading, setIsDatasourceChunksLoading] =
    useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isStartingUpload, setIsStartingUpload] = useState(false);
  const [pollActive, setPollActive] = useState(false);
  const [lastKnownSnapshot, setLastKnownSnapshot] = useState<{
    collectionId: string;
    progress: UploadProgress;
  } | null>(null);

  const { progress: uploadStatus } = useUploadStatus(
    readOnly ? null : collectionId,
    pollActive
  );

  useEffect(() => {
    if (uploadStatus && collectionId) {
      setLastKnownSnapshot({ collectionId, progress: uploadStatus });
    }
  }, [uploadStatus, collectionId]);

  const effectiveUploadProgress =
    uploadStatus ??
    (lastKnownSnapshot?.collectionId === collectionId
      ? lastKnownSnapshot.progress
      : null);

  const uploadInProgress =
    isStartingUpload ||
    effectiveUploadProgress?.status === "pending" ||
    effectiveUploadProgress?.status === "processing";

  // Auto-resume polling when collection is selected (e.g. after page navigation)
  useEffect(() => {
    if (!collectionId || readOnly) {
      setPollActive(false);
      setLastKnownSnapshot(null);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const data = await fetchUploadStatus(collectionId);
        if (cancelled || !data) return;
        if (data.status === "pending" || data.status === "processing") {
          setLastKnownSnapshot({ collectionId, progress: data });
          setPollActive(true);
        }
      } catch {
        // No upload job to resume — ignore.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [collectionId, readOnly]);

  // Stop polling and surface results once the upload job finishes.
  useEffect(() => {
    if (!uploadStatus) return;
    if (
      uploadStatus.status === "completed" ||
      uploadStatus.status === "failed"
    ) {
      setPollActive(false);
      setIsStartingUpload(false);
      mutate();

      if (uploadStatus.status === "failed") {
        toast.error(
          uploadStatus.error ?? t("admin.documentProcessing.uploadFailed")
        );
        return;
      }

      if (uploadStatus.added_chunk_ids.length > 0) {
        toast.success(
          t("admin.documentProcessing.uploadSuccess", {
            count: uploadStatus.processed_files,
            defaultValue: `${uploadStatus.processed_files} dosya başarıyla yüklendi.`,
          })
        );
      }
      if (uploadStatus.duplicate_files.length > 0) {
        toast.warning(
          t("admin.documentProcessing.uploadDuplicateFiles", {
            files: uploadStatus.duplicate_files.join(", "),
            defaultValue: `Bu dosyalar zaten koleksiyonda mevcut, atlandı: ${uploadStatus.duplicate_files.join(
              ", "
            )}`,
          })
        );
      }
      if (uploadStatus.failed_files.length > 0) {
        toast.warning(
          t("admin.documentProcessing.uploadFailedFiles", {
            files: uploadStatus.failed_files.join(", "),
            defaultValue: `Bu dosyalar işlenemedi: ${uploadStatus.failed_files.join(
              ", "
            )}`,
          })
        );
      }
    }
  }, [uploadStatus, mutate, t]);

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

      setIsStartingUpload(true);
      setLastKnownSnapshot(null);
      try {
        const metadatas = acceptedFiles.map((f) => ({ filename: f.name }));
        await startUploadJob(collectionId, acceptedFiles, metadatas);
        setPollActive(true);
      } catch (e) {
        setIsStartingUpload(false);
        toast.error(
          e instanceof Error
            ? e.message
            : t("admin.documentProcessing.uploadFailed")
        );
      }
    },
    [collectionId, isCollectionMutationLocked, t]
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
                <Text
                  as="p"
                  mainContentMuted
                  text03
                  className="font-mono text-[10px]"
                >
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
                    Math.max(
                      chunk.content.split(/\s+/).length,
                      Math.floor(chunk.content.length / 4)
                    )
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
                    disabled={uploadInProgress}
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
                          uploadInProgress && "opacity-60 cursor-not-allowed"
                        )}
                      >
                        <input {...getInputProps()} />
                        {uploadInProgress ? (
                          <div className="flex w-full max-w-xs flex-col items-center gap-3">
                            <Text as="p" mainContentMuted text03>
                              {effectiveUploadProgress?.current_file
                                ? t("admin.documentProcessing.uploadingFile", {
                                    current:
                                      effectiveUploadProgress.processed_files +
                                      1,
                                    total: effectiveUploadProgress.total_files,
                                    file: effectiveUploadProgress.current_file,
                                    defaultValue: `İşleniyor: ${
                                      effectiveUploadProgress.processed_files +
                                      1
                                    }/${
                                      effectiveUploadProgress.total_files
                                    } — ${
                                      effectiveUploadProgress.current_file
                                    }`,
                                  })
                                : t(
                                    "admin.documentProcessing.uploadingAndProcessing"
                                  )}
                            </Text>
                            <div className="w-full bg-background-neutral-02 rounded-full h-2 border border-border-01 overflow-hidden">
                              <div
                                className="bg-theme-primary-04 h-2 rounded-full transition-all duration-500"
                                style={{
                                  width: `${
                                    effectiveUploadProgress?.progress_percent ??
                                    0
                                  }%`,
                                }}
                              />
                            </div>
                          </div>
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
                                  ? t("admin.documentProcessing.dropFilesHere")
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
        <Text
          as="p"
          headingH3
          text05
          className="border-b border-border-01 pb-2"
        >
          {readOnly
            ? t("admin.documentProcessing.chunks", { defaultValue: "Chunks" })
            : t("admin.documentProcessing.documents")}{" "}
          {readOnly
            ? !isDatasourceChunksLoading && (
                <span className="font-normal text-text-03">
                  ({datasourceChunks.length})
                </span>
              )
            : !isLoading && (
                <span className="font-normal text-text-03">
                  ({documents.length})
                </span>
              )}
        </Text>

        {readOnly ? (
          renderDatasourceChunks()
        ) : isLoading ? (
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
