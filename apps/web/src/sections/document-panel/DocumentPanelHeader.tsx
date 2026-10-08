"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import {
  SvgEdit,
  SvgFileText,
  SvgMaximize2,
  SvgMinimize2,
  SvgX,
} from "@/icons";
import type {
  DocumentDetail,
  RevisionSummary,
} from "@/lib/api/domains/documents/types";
import Text from "@/refresh-components/texts/Text";
import {
  authorKey,
  formatRevisionTime,
} from "@/sections/document-panel/revisionMeta";
import {
  useWhitePage,
  cycleWhitePageMode,
} from "@/sections/document-panel/useWhitePage";

interface DocumentPanelHeaderProps {
  document: DocumentDetail;
  revision: RevisionSummary;
  onEdit: () => void;
  onClose: () => void;
  onToggleMaximize?: () => void;
  maximized: boolean;
  canEdit: boolean;
  /** Rendered between the title block and the actions (switcher, export). */
  children?: React.ReactNode;
  /** Right-hand action group, rendered left of the edit button. */
  actions?: React.ReactNode;
}

export function DocumentPanelHeader({
  document,
  revision,
  onEdit,
  onClose,
  onToggleMaximize,
  maximized,
  canEdit,
  children,
  actions,
}: DocumentPanelHeaderProps) {
  const { t, i18n } = useTranslation();
  const [whitePage] = useWhitePage();
  const whitePageLabel = t("documentPanel.whitePageHint", {
    state: t(`documentPanel.whitePageState.${whitePage}`),
  });

  return (
    <div
      className="flex flex-col gap-2 px-3 py-2 border-b border-border-01"
      data-testid="document-panel-header"
    >
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-08 bg-background-tint-01">
          <SvgFileText size={16} className="text-text-03" />
        </div>
        <div className="flex flex-col min-w-0 flex-1">
          <Text as="p" mainUiAction className="truncate">
            {document.filename}
          </Text>
          <Text as="p" secondaryBody text03>
            {t("documentPanel.meta", {
              revision: revision.revision_no,
              author: t(authorKey(revision.author_type)),
              time: formatRevisionTime(revision.created_at, i18n.language),
            })}
          </Text>
        </div>
        {onToggleMaximize && (
          <Button
            icon={maximized ? SvgMinimize2 : SvgMaximize2}
            prominence="tertiary"
            size="sm"
            aria-label={t(
              maximized ? "documentPanel.restoreSize" : "documentPanel.maximize"
            )}
            onClick={onToggleMaximize}
          />
        )}
        <Button
          icon={SvgX}
          prominence="tertiary"
          size="sm"
          aria-label={t("documentPanel.close")}
          onClick={onClose}
        />
      </div>
      <div className="flex items-center gap-2 justify-between flex-wrap">
        {children}
        <div
          className="flex items-center gap-2"
          data-testid="document-panel-header-actions"
        >
          {/* In dark mode the document can read as a white page, like Word.
              The button cycles three states so the sheet and its surroundings
              turn light independently. */}
          <Button
            size="sm"
            variant="select"
            prominence={whitePage === "page" ? "heavy" : "light"}
            selected={whitePage !== "off"}
            aria-pressed={whitePage !== "off"}
            aria-label={whitePageLabel}
            tooltip={whitePageLabel}
            onClick={() => cycleWhitePageMode()}
          >
            {t("documentPanel.whitePage")}
          </Button>
          {actions}
          {canEdit && (
            <Button
              icon={SvgEdit}
              prominence="primary"
              size="sm"
              onClick={onEdit}
            >
              {t("documentPanel.edit")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
