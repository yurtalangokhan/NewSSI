"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgArrowExchange } from "@/icons";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { useRevisionPair } from "@/lib/api/domains/documents/hooks";
import type { DocumentDetail } from "@/lib/api/domains/documents/types";
import { BlockDiffEntry, blockDiff } from "@/lib/documents/diff/blockDiff";
import { revisionToMarkdown } from "@/lib/documents/documentContent";
import { cn } from "@/lib/utils";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Text from "@/refresh-components/texts/Text";
import { DocumentContentView } from "@/sections/document-panel/DocumentContentView";
import { LoadError } from "@/sections/document-panel/LoadError";
import { useProportionalScrollSync } from "@/sections/document-panel/useProportionalScrollSync";

type CompareStatus = "same" | "added" | "changed" | "removed";

const STATUS_CLASS: Record<CompareStatus, string> = {
  same: "",
  added: "bg-status-success-01 border-l-2 border-status-success-05",
  changed: "bg-status-warning-01 border-l-2 border-status-warning-05",
  removed: "bg-status-error-01 border-l-2 border-status-error-05",
};

function columnBlocks(entries: BlockDiffEntry[], side: "left" | "right") {
  return entries.flatMap((entry, i) => {
    const block = side === "left" ? entry.before : entry.after;
    if (!block) return [];
    const status: CompareStatus =
      entry.status === "unchanged"
        ? "same"
        : entry.status === "modified"
          ? "changed"
          : entry.status === "added"
            ? "added"
            : "removed";
    return [{ key: `${side}-${i}`, source: block.source, status }];
  });
}

interface CompareTabProps {
  document: DocumentDetail;
  viewed: number;
}

export function CompareTab({ document, viewed }: CompareTabProps) {
  const { t } = useTranslation();
  const compare = useDocumentPanelStore((s) => s.compare);
  const setCompare = useDocumentPanelStore((s) => s.setCompare);
  const pairNos = compare ?? { left: Math.max(1, viewed - 1), right: viewed };
  const [sync, setSync] = useState(true);
  // Callback refs into state: the hook re-binds when a column (re)mounts.
  const [leftEl, setLeftEl] = useState<HTMLDivElement | null>(null);
  const [rightEl, setRightEl] = useState<HTMLDivElement | null>(null);
  useProportionalScrollSync(leftEl, rightEl, sync);

  const { left, right, isLoading, error, retry } = useRevisionPair(
    document.document_id,
    pairNos.left,
    pairNos.right
  );
  const diff = useMemo(
    () =>
      left.data && right.data
        ? blockDiff(
            revisionToMarkdown(left.data),
            revisionToMarkdown(right.data)
          )
        : null,
    [left.data, right.data]
  );
  const numbers = document.revisions
    .map((r) => r.revision_no)
    .sort((a, b) => a - b);

  const picker = (side: "left" | "right") => (
    <InputSelect
      value={String(pairNos[side])}
      onValueChange={(value) =>
        side === "left"
          ? setCompare(Number(value), pairNos.right)
          : setCompare(pairNos.left, Number(value))
      }
    >
      <InputSelect.Trigger aria-label={t(`documentPanel.compare.${side}`)} />
      <InputSelect.Content>
        {numbers.map((no) => (
          <InputSelect.Item key={no} value={String(no)}>
            {t("documentPanel.draftLabel", { revision: no })}
          </InputSelect.Item>
        ))}
      </InputSelect.Content>
    </InputSelect>
  );

  const column = (
    side: "left" | "right",
    ref: (el: HTMLDivElement | null) => void
  ) => (
    <div
      ref={ref}
      data-testid={`compare-${side}`}
      className="flex-1 min-w-0 overflow-auto rounded-12 border border-border-01 bg-background-tint-00 p-4"
    >
      {diff && !diff.tooLarge ? (
        columnBlocks(diff.entries, side).map((block) => (
          <div
            key={block.key}
            data-testid="compare-block"
            data-status={block.status}
            className={cn("rounded-04 px-2", STATUS_CLASS[block.status])}
          >
            <MinimalMarkdown content={block.source} />
          </div>
        ))
      ) : (
        <DocumentContentView
          markdown={revisionToMarkdown(
            (side === "left" ? left.data : right.data)!
          )}
          className="border-0 p-0"
        />
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-3 p-4 h-full min-h-0">
      <div className="flex items-center gap-2 flex-wrap">
        {picker("left")}
        <Button
          icon={SvgArrowExchange}
          prominence="tertiary"
          size="sm"
          aria-label={t("documentPanel.compare.swap")}
          onClick={() => setCompare(pairNos.right, pairNos.left)}
        />
        {picker("right")}
        <Button
          size="sm"
          prominence={sync ? "secondary" : "tertiary"}
          onClick={() => setSync((v) => !v)}
        >
          {t("documentPanel.compare.syncScroll")}
        </Button>
        <div className="ml-auto flex items-center gap-2">
          {(["added", "changed", "removed"] as const).map((status) => (
            <span key={status} className="flex items-center gap-1">
              <span
                className={cn(
                  "inline-block w-3 h-3 rounded-04",
                  STATUS_CLASS[status]
                )}
              />
              <Text as="span" secondaryBody text03>
                {t(`documentPanel.compare.legend.${status}`)}
              </Text>
            </span>
          ))}
        </div>
      </div>
      {error ? (
        <LoadError onRetry={() => void retry()} />
      ) : isLoading || !left.data || !right.data ? (
        <div className="h-64 rounded-12 bg-background-tint-02 animate-pulse" />
      ) : (
        <div className="flex gap-3 flex-1 min-h-0">
          {column("left", setLeftEl)}
          {column("right", setRightEl)}
        </div>
      )}
    </div>
  );
}
