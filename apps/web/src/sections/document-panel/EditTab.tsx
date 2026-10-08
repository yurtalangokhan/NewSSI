"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgAlertTriangle } from "@/icons";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import type { MermaidDiagnostic } from "@/components/mermaid/mermaidDiagnostics";
import { LightSurface } from "@/components/theme/LightSurface";
import { toast } from "@/hooks/useToast";
import {
  DiagramInvalidError,
  DocumentNoChangeError,
  RevisionConflictError,
  saveUserRevision,
} from "@/lib/api/domains/documents/api";
import {
  refreshAuthoredDocument,
  useRevision,
} from "@/lib/api/domains/documents/hooks";
import { FetchError } from "@/lib/api/http/errors";
import type {
  DiagramBlockDiagnostic,
  DocumentDetail,
} from "@/lib/api/domains/documents/types";
import { revisionToMarkdown } from "@/lib/documents/documentContent";
import Text from "@/refresh-components/texts/Text";
import { LazyCodeEditor } from "@/sections/document-panel/LazyCodeEditor";
import { ConflictNotice } from "@/sections/document-panel/ConflictNotice";
import { DocumentContentView } from "@/sections/document-panel/DocumentContentView";
import { useWhitePage } from "@/sections/document-panel/useWhitePage";

const PREVIEW_DEBOUNCE_MS = 300;

interface EditTabProps {
  document: DocumentDetail;
  onRequestMermaidFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
}

export function EditTab({ document, onRequestMermaidFix }: EditTabProps) {
  const { t } = useTranslation();
  const documentId = document.document_id;
  const [mode] = useWhitePage();
  const edit = useDocumentPanelStore((s) => s.edit);
  const knownHead = useDocumentPanelStore((s) => s.knownHead);
  const updateDraft = useDocumentPanelStore((s) => s.updateDraft);
  const [saving, setSaving] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagramBlockDiagnostic[]>([]);
  const draftText = edit?.text ?? "";
  const baseRevisionNo = edit?.baseRevisionNo ?? null;
  const mergeWith = edit?.mergeWith ?? null;
  const [previewText, setPreviewText] = useState(draftText);

  const { data: base } = useRevision(documentId, baseRevisionNo);
  const { data: mergeTarget } = useRevision(documentId, mergeWith);
  const sourceFormat = base?.source_format ?? "markdown";

  useEffect(() => {
    const handle = setTimeout(
      () => setPreviewText(draftText),
      PREVIEW_DEBOUNCE_MS
    );
    return () => clearTimeout(handle);
  }, [draftText]);

  const previewMarkdown = useMemo(
    () =>
      revisionToMarkdown({
        source_format: sourceFormat,
        content: previewText,
      }),
    [sourceFormat, previewText]
  );
  const highlightLines = useMemo(
    () => diagnostics.map((d) => d.document_line),
    [diagnostics]
  );

  const save = useCallback(async () => {
    // Read the latest session: a rebase right before this call must be honoured.
    const session = useDocumentPanelStore.getState().edit;
    if (!session) return;
    setSaving(true);
    setDiagnostics([]);
    try {
      const result = await saveUserRevision(documentId, {
        baseRevisionNo: session.baseRevisionNo,
        content: session.text,
      });
      const created = result.revision.revision_no;
      const store = useDocumentPanelStore.getState();
      store.syncHead(documentId, created);
      store.discardDraft();
      store.selectRevision(created);
      toast.success(t("documentPanel.editor.saved", { revision: created }));
      void refreshAuthoredDocument(documentId);
    } catch (error) {
      if (error instanceof RevisionConflictError) {
        useDocumentPanelStore.getState().markConflict(error.headRevisionNo);
        void refreshAuthoredDocument(documentId);
      } else if (error instanceof DiagramInvalidError) {
        setDiagnostics(error.diagnostics);
      } else if (error instanceof DocumentNoChangeError) {
        toast.info(
          t("documentPanel.editor.noChange", {
            revision: session.baseRevisionNo,
          })
        );
      } else if (error instanceof FetchError && error.message) {
        // e.g. document.invalid_content: the server already localizes it.
        toast.error(error.message);
      } else {
        toast.error(t("documentPanel.editor.saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  }, [documentId, t]);

  const panelStore = useDocumentPanelStore.getState;
  // The panel drops the tab as soon as the session ends; render nothing for
  // that one commit instead of reading a session that is already gone.
  if (!edit) return null;
  const conflictHead = edit.conflictHeadNo;

  return (
    <div
      className="flex flex-col gap-3 p-4 h-full min-h-0"
      data-testid="edit-tab"
    >
      <div className="flex flex-col gap-0.5">
        <Text as="p" mainUiAction>
          {t("documentPanel.editor.title")}
        </Text>
        <Text as="p" secondaryBody text03>
          {t("documentPanel.editor.hint")}
        </Text>
      </div>

      {edit.staleAtStart && conflictHead === null && knownHead !== null && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-12 border border-border-02 bg-status-warning-01 p-3"
        >
          <SvgAlertTriangle size={16} className="text-text-04 mt-0.5" />
          <Text as="p" secondaryBody text05>
            {t("documentPanel.editor.staleStart", {
              base: edit.baseRevisionNo,
              head: knownHead,
            })}
          </Text>
        </div>
      )}
      {conflictHead !== null && (
        <ConflictNotice
          baseRevisionNo={edit.baseRevisionNo}
          headRevisionNo={conflictHead}
          busy={saving}
          staleAtStart={edit.staleAtStart}
          onApplyOnLatest={() =>
            panelStore().rebaseDraft(conflictHead, { review: true })
          }
          onOverwrite={() => {
            panelStore().rebaseDraft(conflictHead, { review: false });
            void save();
          }}
          onShowDiff={() =>
            panelStore().setCompare(edit.baseRevisionNo, conflictHead)
          }
        />
      )}
      {edit.mergeWith !== null && (
        <Text as="p" secondaryBody text03>
          {t("documentPanel.editor.mergeHint", { head: edit.mergeWith })}
        </Text>
      )}
      {diagnostics.length > 0 && (
        <div
          role="alert"
          className="flex flex-col gap-0.5 rounded-08 bg-status-error-01 px-3 py-2"
        >
          <Text as="p" secondaryBody text05>
            {t("documentPanel.editor.diagramInvalid", {
              count: diagnostics.length,
            })}
          </Text>
          {diagnostics.map((d) => (
            <Text
              key={`${d.block_index}-${d.document_line}`}
              as="p"
              secondaryMono
              text04
            >
              {t("documentPanel.editor.diagnosticLine", {
                line: d.document_line,
                message: d.message,
              })}
            </Text>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3 flex-1 min-h-0">
        {/* The editor is where the text is written, so it is part of the paper
            in both white-page modes: CodeMirror paints itself from the CSS
            tokens. */}
        <LightSurface enabled={mode !== "off"} className="flex-1 min-h-[16rem]">
          <LazyCodeEditor
            value={edit.text}
            onChange={updateDraft}
            ariaLabel={t("documentPanel.editor.ariaLabel")}
            highlightLines={highlightLines}
            mergeOriginal={
              edit.mergeWith !== null ? mergeTarget?.content ?? null : null
            }
          />
        </LightSurface>
        <div className="flex-1 min-h-0 overflow-auto">
          <DocumentContentView
            markdown={previewMarkdown}
            onRequestMermaidFix={onRequestMermaidFix}
          />
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <Button
          prominence="tertiary"
          size="sm"
          onClick={() => panelStore().requestDiscardDraft()}
        >
          {t("documentPanel.editor.cancel")}
        </Button>
        <Button
          prominence="primary"
          size="sm"
          disabled={saving || conflictHead !== null}
          onClick={() => void save()}
        >
          {t(
            saving ? "documentPanel.editor.saving" : "documentPanel.editor.save"
          )}
        </Button>
      </div>
    </div>
  );
}
