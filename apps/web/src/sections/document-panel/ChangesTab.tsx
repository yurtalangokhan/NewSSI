"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { useRevisionPair } from "@/lib/api/domains/documents/hooks";
import type { DocumentDetail } from "@/lib/api/domains/documents/types";
import { blockDiff } from "@/lib/documents/diff/blockDiff";
import { revisionToMarkdown } from "@/lib/documents/documentContent";
import Chip from "@/refresh-components/Chip";
import Text from "@/refresh-components/texts/Text";
import { LazyCodeEditor } from "@/sections/document-panel/LazyCodeEditor";
import { LoadError } from "@/sections/document-panel/LoadError";
import { RenderedDiff } from "@/sections/document-panel/RenderedDiff";

interface ChangesTabProps {
  document: DocumentDetail;
  revisionNo: number;
}

export function ChangesTab({ document, revisionNo }: ChangesTabProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"rendered" | "source">("rendered");
  const from = revisionNo - 1;
  const { left, right, isLoading, error, retry } = useRevisionPair(
    document.document_id,
    from >= 1 ? from : null,
    from >= 1 ? revisionNo : null
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

  if (revisionNo <= 1) {
    return (
      <div className="flex flex-col items-center gap-1 p-8 text-center">
        <Text as="p" mainUiAction>
          {t("documentPanel.changes.firstTitle")}
        </Text>
        <Text as="p" secondaryBody text03>
          {t("documentPanel.changes.firstBody")}
        </Text>
      </div>
    );
  }
  if (error) return <LoadError onRetry={() => void retry()} />;
  if (isLoading || !diff || !left.data || !right.data) {
    return (
      <div className="h-64 m-4 rounded-12 bg-background-tint-02 animate-pulse" />
    );
  }

  const sourceOnly = diff.tooLarge;
  const showSource = sourceOnly || mode === "source";

  return (
    <div className="flex flex-col gap-3 p-4 h-full min-h-0">
      <div className="flex items-center gap-2 flex-wrap">
        <Text as="p" mainUiAction>
          {t("documentPanel.changes.range", { from, to: revisionNo })}
        </Text>
        {!diff.tooLarge && (
          <>
            {diff.summary.added > 0 && (
              <Chip>
                {t("documentPanel.changes.summary.added", {
                  count: diff.summary.added,
                })}
              </Chip>
            )}
            {diff.summary.modified > 0 && (
              <Chip>
                {t("documentPanel.changes.summary.modified", {
                  count: diff.summary.modified,
                })}
              </Chip>
            )}
            {diff.summary.removed > 0 && (
              <Chip>
                {t("documentPanel.changes.summary.removed", {
                  count: diff.summary.removed,
                })}
              </Chip>
            )}
          </>
        )}
        {!sourceOnly && (
          <div className="ml-auto flex gap-1">
            {(["rendered", "source"] as const).map((value) => (
              <Button
                key={value}
                size="sm"
                prominence={mode === value ? "secondary" : "tertiary"}
                onClick={() => setMode(value)}
              >
                {t(`documentPanel.changes.${value}`)}
              </Button>
            ))}
          </div>
        )}
      </div>
      {sourceOnly && (
        <Text as="p" secondaryBody text03>
          {t("documentPanel.changes.tooLarge")}
        </Text>
      )}
      {showSource ? (
        <div className="flex-1 min-h-[20rem]">
          <LazyCodeEditor
            value={right.data.content}
            mergeOriginal={left.data.content}
            readOnly
            ariaLabel={t("documentPanel.changes.source")}
          />
        </div>
      ) : (
        !diff.tooLarge && <RenderedDiff entries={diff.entries} />
      )}
    </div>
  );
}
