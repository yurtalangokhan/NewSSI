"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgSparkle, SvgUser } from "@/icons";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import type { DocumentDetail } from "@/lib/api/domains/documents/types";
import { cn } from "@/lib/utils";
import Chip from "@/refresh-components/Chip";
import Text from "@/refresh-components/texts/Text";
import {
  authorKey,
  formatRevisionTime,
} from "@/sections/document-panel/revisionMeta";
import { useRevisionActions } from "@/sections/document-panel/useRevisionActions";

interface HistoryTabProps {
  document: DocumentDetail;
  viewed: number;
}

export function HistoryTab({ document, viewed }: HistoryTabProps) {
  const { t, i18n } = useTranslation();
  const selectRevision = useDocumentPanelStore((s) => s.selectRevision);
  const setTab = useDocumentPanelStore((s) => s.setTab);
  const setCompare = useDocumentPanelStore((s) => s.setCompare);
  const { restore, restoring } = useRevisionActions(document.document_id);
  const head = document.head_revision_no;
  const ordered = [...document.revisions].sort(
    (a, b) => b.revision_no - a.revision_no
  );

  return (
    <ol className="flex flex-col gap-1 p-4">
      {ordered.map((revision) => {
        const isHead = revision.revision_no === head;
        const Avatar = revision.author_type === "user" ? SvgUser : SvgSparkle;
        const { added, removed } = revision.stats;
        return (
          <li
            key={revision.revision_no}
            data-testid="history-item"
            className={cn(
              "flex gap-3 rounded-12 px-3 py-2",
              revision.revision_no === viewed && "bg-background-tint-01"
            )}
          >
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-background-tint-02">
              <Avatar size={14} className="text-text-03" />
            </div>
            <div className="flex flex-col gap-0.5 min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <Text as="p" mainUiAction>
                  {t("documentPanel.draftLabel", {
                    revision: revision.revision_no,
                  })}
                </Text>
                {isHead && <Chip>{t("documentPanel.history.latest")}</Chip>}
                {(added > 0 || removed > 0) && (
                  <Text as="span" secondaryMono text03 className="ml-auto">
                    {`+${added} −${removed}`}
                  </Text>
                )}
              </div>
              <Text as="p" secondaryBody text04>
                {revision.summary || t("documentPanel.history.fallbackSummary")}
              </Text>
              <Text as="p" secondaryBody text03>
                {[
                  t(authorKey(revision.author_type)),
                  t(`documentPanel.history.operation.${revision.operation}`),
                  formatRevisionTime(revision.created_at, i18n.language),
                ].join(" · ")}
              </Text>
              <div className="flex gap-1 pt-1">
                <Button
                  size="sm"
                  prominence="tertiary"
                  onClick={() => {
                    selectRevision(revision.revision_no);
                    setTab("preview");
                  }}
                >
                  {t("documentPanel.history.view")}
                </Button>
                {!isHead && (
                  <>
                    <Button
                      size="sm"
                      prominence="tertiary"
                      onClick={() => setCompare(revision.revision_no, head)}
                    >
                      {t("documentPanel.history.compareWithLatest")}
                    </Button>
                    <Button
                      size="sm"
                      prominence="secondary"
                      disabled={restoring}
                      onClick={() => void restore(revision.revision_no, head)}
                    >
                      {t("documentPanel.history.restore")}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
