"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { LegacyFile } from "@/app/app/stores/useDocumentPanelStore";
import { DocumentPreviewSkeleton } from "@/refresh-components/skeletons";
import Text from "@/refresh-components/texts/Text";
import { usePreviewFile } from "@/sections/modals/PreviewModal/usePreviewFile";

interface LegacyFileBodyProps {
  file: LegacyFile;
}

export function LegacyFileBody({ file }: LegacyFileBodyProps) {
  const { t } = useTranslation();
  const document = useMemo(
    () => ({
      document_id: file.fileId,
      semantic_identifier: file.filename,
      preview_mime_type: file.mimeType,
    }),
    [file.fileId, file.filename, file.mimeType]
  );
  const { variant, ctx, isLoading, loadError } = usePreviewFile(document);

  return (
    <div
      className="flex flex-col h-full min-h-0"
      data-testid="legacy-file-body"
    >
      <div className="px-4 py-2 bg-background-tint-01 border-b border-border-01">
        <Text as="p" secondaryBody text03>
          {t("documentPanel.legacy.notice")}
        </Text>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="p-4">
            {/* Legacy previews render straight on the panel surface, so the
                placeholder keeps the same shape without a paper. */}
            <DocumentPreviewSkeleton paper={false} />
          </div>
        ) : loadError ? (
          <Text as="p" mainUiBody text03 className="p-4">
            {loadError}
          </Text>
        ) : (
          variant.renderContent(ctx)
        )}
      </div>
      {!isLoading && !loadError && (
        <div className="flex justify-end p-2 border-t border-border-01">
          {variant.renderFooterRight(ctx)}
        </div>
      )}
    </div>
  );
}
