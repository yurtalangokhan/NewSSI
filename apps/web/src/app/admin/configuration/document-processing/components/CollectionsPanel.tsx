"use client";

import { useState, useMemo, useCallback } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Text from "@/refresh-components/texts/Text";
import { ThreeDotsLoader } from "@/components/Loading";
import { toast } from "@/hooks/useToast";
import {
  useCollections,
  createCollection,
  deleteCollection,
  updateCollection,
} from "@/lib/langconnect";
import { useAirbyteDatasources } from "@/lib/airbyte";
import { SvgHardDrive, SvgPlus, SvgTrash } from "@opal/icons";
import { useTranslation } from "react-i18next";

interface CollectionsPanelProps {
  selectedCollectionId: string | null;
  onCollectionSelect: (id: string | null, isDatasource?: boolean) => void;
  isCollectionMutationLocked: boolean;
}

export default function CollectionsPanel({
  selectedCollectionId,
  onCollectionSelect,
  isCollectionMutationLocked,
}: CollectionsPanelProps) {
  const { t } = useTranslation();
  const { collections: allCollections, isLoading: collectionsLoading, mutate } = useCollections();
  const { datasources, isLoading: dsLoading } = useAirbyteDatasources();
  const isLoading = collectionsLoading || dsLoading;

  const datasourceIds = useMemo(
    () => new Set(datasources.map((ds) => ds.id)),
    [datasources]
  );
  const collections = allCollections;
  const isDatasourceCollection = useCallback(
    (uuid: string) => datasourceIds.has(uuid),
    [datasourceIds]
  );
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameName, setRenameName] = useState("");
  const [isRenameSubmitting, setIsRenameSubmitting] = useState(false);

  const selectedCollection = collections.find(
    (c) => c.uuid === selectedCollectionId
  );
  const selectedIsDatasource = selectedCollectionId
    ? isDatasourceCollection(selectedCollectionId)
    : false;

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    setIsSubmitting(true);
    try {
      const created = await createCollection({ name });
      await mutate();
      onCollectionSelect(created.uuid);
      setNewName("");
      setIsCreating(false);
      toast.success(t("admin.documentProcessing.collectionCreated", { name: created.name }));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create collection");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!selectedCollectionId || !selectedCollection) return;
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
      `Delete collection "${selectedCollection.name}"? This will remove all documents in it.`
    );
    if (!confirmed) return;
    setIsDeleting(true);
    try {
      await deleteCollection(selectedCollectionId);
      await mutate();
      onCollectionSelect(null);
      toast.success(t("admin.documentProcessing.collectionDeleted"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete collection");
    } finally {
      setIsDeleting(false);
    }
  }

  async function handleRename() {
    if (!selectedCollectionId || !selectedCollection) return;
    if (isCollectionMutationLocked) {
      toast.warning(
        t("admin.documentProcessing.collectionMutationLocked", {
          defaultValue:
            "Graph RAG build devam ederken bu koleksiyon üzerinde değişiklik yapılamaz.",
        })
      );
      return;
    }

    const name = renameName.trim();
    if (!name || name === selectedCollection.name) {
      setIsRenaming(false);
      return;
    }

    setIsRenameSubmitting(true);
    try {
      const updated = await updateCollection(selectedCollectionId, { name });
      await mutate();
      onCollectionSelect(updated.uuid, selectedIsDatasource);
      setIsRenaming(false);
      toast.success(
        t("admin.documentProcessing.collectionRenamed", { name: updated.name })
      );
    } catch (e) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.documentProcessing.collectionRenameFailed")
      );
    } finally {
      setIsRenameSubmitting(false);
    }
  }

  return (
    <CardSection className="flex flex-col gap-4">
      <div className="flex items-center gap-2 border-b border-border-01 pb-3">
        <SvgHardDrive className="h-4 w-4 stroke-text-03" aria-hidden />
        <Text as="p" headingH3 text05>
          {t("admin.documentProcessing.ragCollections")}
        </Text>
      </div>

      <Text as="p" mainContentBody text04 className="leading-relaxed">
        {t("admin.documentProcessing.ragCollectionsDescription")}
      </Text>

      {isLoading ? (
        <ThreeDotsLoader />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <div className="flex-1">
              {collections.length === 0 ? (
                <div className="flex items-center h-9 rounded-08 border border-border-01 bg-background-neutral-01 px-3">
                  <Text as="p" mainUiMuted text03>
                    {t("admin.documentProcessing.noCollections")}
                  </Text>
                </div>
              ) : (
                <InputSelect
                  value={selectedCollectionId ?? ""}
                  onValueChange={(v) =>
                    onCollectionSelect(v || null, v ? isDatasourceCollection(v) : undefined)
                  }
                >
                  <InputSelect.Trigger placeholder={t("admin.documentProcessing.selectCollection")} />
                  <InputSelect.Content>
                    {collections.map((c) => (
                      <InputSelect.Item key={c.uuid} value={c.uuid}>
                        {c.name}
                        {isDatasourceCollection(c.uuid) && (
                          <span className="ml-2 text-[10px] font-medium uppercase tracking-wide text-text-03 bg-background-neutral-02 border border-border-01 rounded px-1 py-0.5">
                            {t("admin.documentProcessing.datasource")}
                          </span>
                        )}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Content>
                </InputSelect>
              )}
            </div>

            <Button
              action
              leftIcon={SvgPlus}
              onClick={() => {
                setIsCreating(true);
                setNewName("");
              }}
            >
              {t("admin.documentProcessing.newCollection")}
            </Button>

            {selectedCollectionId && (
              <Button
                action
                onClick={() => {
                  if (!selectedCollection) return;
                  setRenameName(selectedCollection.name);
                  setIsRenaming(true);
                }}
                disabled={selectedIsDatasource || isCollectionMutationLocked}
              >
                {t("admin.documentProcessing.renameCollection")}
              </Button>
            )}

            {selectedCollectionId && (
              <Button
                danger
                leftIcon={SvgTrash}
                onClick={handleDelete}
                disabled={isDeleting || isRenaming || isCollectionMutationLocked}
              >
                {isDeleting ? t("admin.documentProcessing.deleting") : t("modals.delete")}
              </Button>
            )}
          </div>

          {isCreating && (
            <div className="flex items-center gap-2 pt-1">
              <div className="flex-1">
                <InputTypeIn
                  placeholder={t("admin.documentProcessing.collectionName")}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreate();
                    if (e.key === "Escape") setIsCreating(false);
                  }}
                  autoFocus
                />
              </div>
              <Button
                action
                onClick={handleCreate}
                disabled={isSubmitting || !newName.trim()}
              >
                {isSubmitting
                  ? t("admin.documentProcessing.creating")
                  : t("admin.documentProcessing.create")}
              </Button>
            </div>
          )}

          {isRenaming && selectedCollection && (
            <div className="flex items-center gap-2 pt-1">
              <div className="flex-1">
                <InputTypeIn
                  placeholder={t("admin.documentProcessing.collectionName")}
                  value={renameName}
                  onChange={(e) => setRenameName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleRename();
                    if (e.key === "Escape") setIsRenaming(false);
                  }}
                  autoFocus
                />
              </div>
              <Button
                action
                onClick={handleRename}
                disabled={isRenameSubmitting || !renameName.trim()}
              >
                {isRenameSubmitting
                  ? t("admin.documentProcessing.renaming")
                  : t("admin.documentProcessing.rename")}
              </Button>
            </div>
          )}

          {selectedCollection && (
            <div className="flex items-center gap-2 rounded-08 bg-background-neutral-01 border border-border-01 px-3 py-2">
              <SvgHardDrive className="h-3.5 w-3.5 shrink-0 stroke-text-03" aria-hidden />
              <Text as="p" mainContentMuted text03 className="font-mono text-xs">
                {selectedCollection.uuid}
              </Text>
              {selectedIsDatasource && (
                <Text as="span" mainContentMuted text03 className="text-xs italic ml-auto">
                  {t("admin.documentProcessing.readOnlyDatasourceCollection")}
                </Text>
              )}
              {!selectedIsDatasource && isCollectionMutationLocked && (
                <Text as="span" mainContentMuted text03 className="text-xs italic ml-auto">
                  {t("admin.documentProcessing.collectionMutationLocked", {
                    defaultValue:
                      "Graph RAG build devam ederken bu koleksiyon üzerinde değişiklik yapılamaz.",
                  })}
                </Text>
              )}
            </div>
          )}
        </div>
      )}
    </CardSection>
  );
}
