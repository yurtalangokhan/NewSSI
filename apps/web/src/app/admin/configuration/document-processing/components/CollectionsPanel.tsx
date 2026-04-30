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
} from "@/lib/langconnect";
import { useAirbyteDatasources } from "@/lib/airbyte";
import { SvgHardDrive, SvgPlus, SvgTrash } from "@opal/icons";

interface CollectionsPanelProps {
  selectedCollectionId: string | null;
  onCollectionSelect: (id: string | null, isDatasource?: boolean) => void;
}

export default function CollectionsPanel({
  selectedCollectionId,
  onCollectionSelect,
}: CollectionsPanelProps) {
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
      toast.success(`Collection "${created.name}" created.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create collection");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!selectedCollectionId || !selectedCollection) return;
    const confirmed = window.confirm(
      `Delete collection "${selectedCollection.name}"? This will remove all documents in it.`
    );
    if (!confirmed) return;
    setIsDeleting(true);
    try {
      await deleteCollection(selectedCollectionId);
      await mutate();
      onCollectionSelect(null);
      toast.success("Collection deleted.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete collection");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <CardSection className="flex flex-col gap-4">
      <div className="flex items-center gap-2 border-b border-border-01 pb-3">
        <SvgHardDrive className="h-4 w-4 stroke-text-03" aria-hidden />
        <Text as="p" headingH3 text05>
          RAG Collections
        </Text>
      </div>

      <Text as="p" mainContentBody text04 className="leading-relaxed">
        Collections store your documents as vector embeddings in PGVector.
        Select an existing collection or create a new one to manage documents
        and run semantic search.
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
                    No collections yet — create one below
                  </Text>
                </div>
              ) : (
                <InputSelect
                  value={selectedCollectionId ?? ""}
                  onValueChange={(v) =>
                    onCollectionSelect(v || null, v ? isDatasourceCollection(v) : undefined)
                  }
                >
                  <InputSelect.Trigger placeholder="Select a collection..." />
                  <InputSelect.Content>
                    {collections.map((c) => (
                      <InputSelect.Item key={c.uuid} value={c.uuid}>
                        {c.name}
                        {isDatasourceCollection(c.uuid) && (
                          <span className="ml-2 text-[10px] font-medium uppercase tracking-wide text-text-03 bg-background-neutral-02 border border-border-01 rounded px-1 py-0.5">
                            Datasource
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
              New Collection
            </Button>

            {selectedCollectionId && (
              <Button
                danger
                leftIcon={SvgTrash}
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? "Deleting…" : "Delete"}
              </Button>
            )}
          </div>

          {isCreating && (
            <div className="flex items-center gap-2 pt-1">
              <div className="flex-1">
                <InputTypeIn
                  placeholder="Collection name"
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
                {isSubmitting ? "Creating…" : "Create"}
              </Button>
              <Button onClick={() => setIsCreating(false)}>Cancel</Button>
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
                  Read-only datasource collection
                </Text>
              )}
            </div>
          )}
        </div>
      )}
    </CardSection>
  );
}
