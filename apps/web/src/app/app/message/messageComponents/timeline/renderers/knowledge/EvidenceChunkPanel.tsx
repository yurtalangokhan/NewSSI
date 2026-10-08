"use client";

import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Button } from "@opal/components";
import { SvgChevronLeft, SvgChevronRight, SvgX } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import type {
  EvidenceChunk,
  EvidenceCollection,
} from "@/lib/api/domains/chat/knowledge-evidence-types";
import { HighlightedText } from "@/refresh-components/texts/HighlightedText";
import { useScoreFormatter } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/useScoreFormatter";

interface EvidenceChunkPanelProps {
  chunks: readonly EvidenceChunk[];
  /** Index into ``chunks`` of the open chunk, or ``null`` when closed. */
  openIndex: number | null;
  query: string;
  collections: readonly EvidenceCollection[];
  searchMode: string;
  onIndexChange: (index: number | null) => void;
}

interface MetaRowProps {
  label: string;
  value: string;
  mono?: boolean;
}

function MetaRow({ label, value, mono = false }: MetaRowProps) {
  return (
    <>
      <Text as="span" secondaryBody text03>
        {label}
      </Text>
      <Text
        as="span"
        secondaryMono={mono}
        secondaryBody={!mono}
        text04
        className="break-words"
      >
        {value}
      </Text>
    </>
  );
}

/**
 * Side panel with one chunk's full text and provenance. Arrow keys step
 * through the chunks; Escape and the overlay close it (Radix Dialog handles
 * focus trapping and restoring focus to the row that opened it).
 */
export function EvidenceChunkPanel({
  chunks,
  openIndex,
  query,
  collections,
  searchMode,
  onIndexChange,
}: EvidenceChunkPanelProps) {
  const { t } = useTranslation();
  const formatScore = useScoreFormatter();
  const chunk = openIndex !== null ? chunks[openIndex] : undefined;
  const total = chunks.length;

  const step = useCallback(
    (delta: number) => {
      if (openIndex === null || total === 0) return;
      onIndexChange((openIndex + delta + total) % total);
    },
    [openIndex, total, onIndexChange]
  );

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    }
  };

  const collectionName = chunk
    ? collections.find((c) => c.id === chunk.collectionId)?.name ??
      chunk.collectionId
    : null;
  const title = chunk?.source.document ?? chunk?.source.title ?? null;

  return (
    <DialogPrimitive.Root
      open={chunk !== undefined}
      onOpenChange={(open) => !open && onIndexChange(null)}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-modal-overlay bg-mask-03" />
        <DialogPrimitive.Content
          onKeyDown={onKeyDown}
          className="fixed inset-y-0 right-0 z-modal flex w-full max-w-[29rem] flex-col border-l border-border-01 bg-background-neutral-00 shadow-2xl focus:outline-none"
        >
          {chunk && (
            <>
              <div className="flex flex-col gap-2 border-b border-border-01 px-4 py-4">
                <div className="flex items-center justify-between gap-2">
                  <Text as="span" secondaryAction text03>
                    {t("knowledgeCard.chunkPosition", {
                      index: (openIndex ?? 0) + 1,
                      total,
                    })}
                  </Text>
                  <div className="flex items-center gap-1">
                    <Button
                      icon={SvgChevronLeft}
                      prominence="tertiary"
                      size="sm"
                      tooltip={t("knowledgeCard.previousChunk")}
                      aria-label={t("knowledgeCard.previousChunk")}
                      onClick={() => step(-1)}
                    />
                    <Button
                      icon={SvgChevronRight}
                      prominence="tertiary"
                      size="sm"
                      tooltip={t("knowledgeCard.nextChunk")}
                      aria-label={t("knowledgeCard.nextChunk")}
                      onClick={() => step(1)}
                    />
                    <DialogPrimitive.Close asChild>
                      <Button
                        icon={SvgX}
                        prominence="tertiary"
                        size="sm"
                        aria-label={t("knowledgeCard.closePanel")}
                      />
                    </DialogPrimitive.Close>
                  </div>
                </div>
                <DialogPrimitive.Title asChild>
                  <Text as="p" mainUiAction text05 className="break-words">
                    {title ??
                      t("knowledgeCard.chunkPosition", {
                        index: chunk.ref,
                        total,
                      })}
                  </Text>
                </DialogPrimitive.Title>
                <DialogPrimitive.Description asChild>
                  <Text as="p" secondaryBody text03>
                    {[
                      chunk.source.page !== null
                        ? t("knowledgeCard.page", { page: chunk.source.page })
                        : null,
                      chunk.source.section,
                      chunk.score !== null
                        ? t("knowledgeCard.score", {
                            score: formatScore(chunk.score),
                          })
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || t("knowledgeCard.chunkPanelDescription")}
                  </Text>
                </DialogPrimitive.Description>
              </div>

              <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
                <Text
                  as="p"
                  mainContentBody
                  text05
                  className="whitespace-pre-wrap break-words"
                >
                  <HighlightedText text={chunk.content} query={query} />
                </Text>
                <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
                  {chunk.id && (
                    <MetaRow
                      label={t("knowledgeCard.chunkId")}
                      value={chunk.id}
                      mono
                    />
                  )}
                  {collectionName && (
                    <MetaRow
                      label={t("knowledgeCard.collection")}
                      value={collectionName}
                    />
                  )}
                  <MetaRow
                    label={t("knowledgeCard.length")}
                    value={`${t("knowledgeCard.lengthValue", {
                      count: chunk.content.length,
                    })} · ${
                      chunk.truncated
                        ? t("knowledgeCard.truncated")
                        : t("knowledgeCard.notTruncated")
                    }`}
                  />
                  <MetaRow
                    label={t("knowledgeCard.searchMode")}
                    value={searchMode}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 border-t border-border-01 px-4 py-3">
                <CopyIconButton getCopyText={() => chunk.content} />
                <Text as="span" secondaryBody text03>
                  {t("knowledgeCard.copyContent")}
                </Text>
              </div>
            </>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
