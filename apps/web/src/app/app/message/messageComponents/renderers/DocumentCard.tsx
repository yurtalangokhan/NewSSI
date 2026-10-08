"use client";

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgMaximize2 } from "@/icons";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import { keyedChanges } from "@/app/app/message/messageComponents/renderers/documentGenerationState";
import { FileIcon } from "@/components/icons/icons";
import type { GeneratedFile } from "@/lib/api/domains/chat/streaming-types";
import { refreshAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import { cn, formatBytes } from "@/lib/utils";
import Chip from "@/refresh-components/Chip";
import Text from "@/refresh-components/texts/Text";
import { openGeneratedFile } from "@/sections/document-panel/openGeneratedFile";

const MAX_CHIPS = 3;
const DIFF_OPERATIONS = new Set(["edit", "rewrite", "user_edit", "restore"]);

interface DocumentCardProps {
  file: GeneratedFile;
  /** True when this card replaced a live progress card (not restored from history). */
  isLive: boolean;
  onFallbackOpen: () => void;
}

function formatBadge(file: GeneratedFile) {
  const ext = file.filename.split(".").pop();
  return (ext && ext !== file.filename ? ext : "file").toUpperCase();
}

export function DocumentCard({
  file,
  isLive,
  onFallbackOpen,
}: DocumentCardProps) {
  const { t } = useTranslation();
  const isDraft = Boolean(file.document_id && file.revision_no);
  const revisionNo = file.revision_no ?? 1;
  const operation = file.operation ?? "create";
  const showDiff = isDraft && DIFF_OPERATIONS.has(operation) && revisionNo > 1;
  const changes = file.stats?.changes ?? [];

  useEffect(() => {
    if (!isLive || !file.document_id || !file.revision_no) return;
    useDocumentPanelStore
      .getState()
      .revisionPublished(file.document_id, file.revision_no);
    void refreshAuthoredDocument(file.document_id);
  }, [isLive, file.document_id, file.revision_no]);

  const open = async () => {
    if ((await openGeneratedFile(file, showDiff)) === "fallback")
      onFallbackOpen();
  };

  const actionLabel = t(
    showDiff ? "documentCard.seeChanges" : "documentCard.open"
  );

  if (!isDraft) {
    return (
      <div
        data-testid="document-card"
        className={cn(
          "flex items-center border bg-background-tint-00 rounded-12 p-1 gap-1 my-1 w-fit",
          isLive && "animate-fade-in-scale"
        )}
      >
        <div className="p-2 bg-background-tint-01 rounded-08">
          <FileIcon size={20} />
        </div>
        <div className="flex flex-col px-2">
          <Text as="p" secondaryAction>
            {file.filename}
          </Text>
          <Text as="p" secondaryBody text03>
            {formatBytes(file.size_bytes)}
          </Text>
        </div>
        <Button
          aria-label={actionLabel}
          onClick={() => void open()}
          icon={SvgMaximize2}
          prominence="tertiary"
          size="sm"
        />
      </div>
    );
  }

  return (
    <div
      data-testid="document-card"
      className={cn(
        "flex flex-col gap-1 my-1 w-full max-w-[26rem]",
        isLive && "animate-fade-in-scale"
      )}
    >
      <div className="flex items-center gap-2 px-1">
        <Text as="p" secondaryAction>
          {t(`documentCard.operation.${operation}`)}
        </Text>
        {operation !== "create" && changes.length > 0 && (
          <Text as="p" secondaryBody text03>
            {t("documentCard.changesApplied", { count: changes.length })}
          </Text>
        )}
      </div>
      <div className="flex flex-col gap-2 border bg-background-tint-00 rounded-12 p-2">
        <div className="flex items-center gap-2">
          <div className="px-1.5 py-1 bg-background-tint-02 rounded-08">
            <Text as="span" figureSmallLabel text04>
              {formatBadge(file)}
            </Text>
          </div>
          <div className="flex flex-col min-w-0 flex-1">
            <Text as="p" secondaryAction className="truncate">
              {file.filename}
            </Text>
            <div className="flex items-center gap-2">
              <Text as="span" figureSmallLabel text03>
                {t("documentCard.draft", { revision: revisionNo })}
              </Text>
              {revisionNo > 1 && file.stats && (
                <>
                  <Text as="span" secondaryMono text03>
                    {`+${file.stats.added} −${file.stats.removed}`}
                  </Text>
                  <Text as="span" secondaryBody text03>
                    {t("documentCard.fromPrevious")}
                  </Text>
                </>
              )}
            </div>
          </div>
          <Button prominence="secondary" size="sm" onClick={() => void open()}>
            {actionLabel}
          </Button>
        </div>
        {operation !== "create" && changes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {keyedChanges(changes.slice(0, MAX_CHIPS)).map(
              ({ change, key }) => (
                <Chip key={key}>
                  {t(`documentCard.change.${change.change}`, {
                    label: change.label,
                  })}
                </Chip>
              )
            )}
            {changes.length > MAX_CHIPS && (
              <Chip>{`+${changes.length - MAX_CHIPS}`}</Chip>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
