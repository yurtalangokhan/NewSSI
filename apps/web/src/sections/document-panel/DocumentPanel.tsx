"use client";

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { Button } from "@opal/components";
import { SvgFileText, SvgX } from "@/icons";
import {
  type DocumentPanelTab,
  type LegacyFile,
  selectViewedRevision,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import type { MermaidDiagnostic } from "@/components/mermaid/mermaidDiagnostics";
import {
  useAuthoredDocument,
  useRevision,
} from "@/lib/api/domains/documents/hooks";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { ChangesTab } from "@/sections/document-panel/ChangesTab";
import { CompareTab } from "@/sections/document-panel/CompareTab";
import { DocumentPanelHeader } from "@/sections/document-panel/DocumentPanelHeader";
import { DocumentPanelSkeleton } from "@/sections/document-panel/DocumentPanelSkeleton";
import { DocumentReadingSurface } from "@/sections/document-panel/DocumentPaper";
import { ExportMenu } from "@/sections/document-panel/ExportMenu";
import { EditTab } from "@/sections/document-panel/EditTab";
import { HistoryTab } from "@/sections/document-panel/HistoryTab";
import { LegacyFileBody } from "@/sections/document-panel/LegacyFileBody";
import { NewDraftNotice } from "@/sections/document-panel/NewDraftNotice";
import { OldRevisionBanner } from "@/sections/document-panel/OldRevisionBanner";
import { PreviewTab } from "@/sections/document-panel/PreviewTab";
import { RevisionSwitcher } from "@/sections/document-panel/RevisionSwitcher";
import { useRevisionActions } from "@/sections/document-panel/useRevisionActions";

export interface DocumentPanelProps {
  onRequestMermaidFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
  maximized?: boolean;
  onToggleMaximize?: () => void;
}

const TABS: Exclude<DocumentPanelTab, "edit">[] = [
  "preview",
  "changes",
  "compare",
  "history",
];

export function DocumentPanel(props: DocumentPanelProps) {
  const { documentId, legacyFile, close } = useDocumentPanelStore(
    useShallow((s) => ({
      documentId: s.documentId,
      legacyFile: s.legacyFile,
      close: s.requestClose,
    }))
  );
  if (legacyFile) return <LegacyPanel file={legacyFile} onClose={close} />;
  if (!documentId) return null;
  return <DraftPanel documentId={documentId} {...props} />;
}

interface LegacyPanelProps {
  file: LegacyFile;
  onClose: () => void;
}

function LegacyPanel({ file, onClose }: LegacyPanelProps) {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-col h-full min-h-0 bg-background-tint-00"
      data-testid="document-panel"
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-01">
        <SvgFileText size={16} className="text-text-03" />
        <Text as="p" mainUiAction className="truncate flex-1">
          {file.filename}
        </Text>
        <Button
          icon={SvgX}
          prominence="tertiary"
          size="sm"
          aria-label={t("documentPanel.close")}
          onClick={onClose}
        />
      </div>
      <LegacyFileBody file={file} />
    </div>
  );
}

interface DraftPanelProps extends DocumentPanelProps {
  documentId: string;
}

function DraftPanel({
  documentId,
  onRequestMermaidFix,
  maximized = false,
  onToggleMaximize,
}: DraftPanelProps) {
  const { t } = useTranslation();
  // Fine-grained selection: the edit text changes on every keystroke and must
  // not re-render the header, switcher and export menu.
  const { tab, viewedNo, pendingHead, editing } = useDocumentPanelStore(
    useShallow((s) => ({
      tab: s.tab,
      viewedNo: selectViewedRevision(s),
      pendingHead: s.pendingHead,
      editing: s.edit?.documentId === documentId && s.tab === "edit",
    }))
  );
  const requestClose = useDocumentPanelStore((s) => s.requestClose);
  const editDraft = useDocumentPanelStore((s) => s.editDraft);
  const selectRevision = useDocumentPanelStore((s) => s.selectRevision);
  const setTab = useDocumentPanelStore((s) => s.setTab);
  const syncHead = useDocumentPanelStore((s) => s.syncHead);
  const { data: document, error, mutate } = useAuthoredDocument(documentId);
  const head = document?.head_revision_no ?? null;
  const viewed = viewedNo ?? head;
  const { data: viewedRevision } = useRevision(documentId, viewed);
  const { restore, restoring } = useRevisionActions(documentId);

  useEffect(() => {
    if (head !== null) syncHead(documentId, head);
  }, [documentId, head, syncHead]);

  if (error) {
    return (
      <div
        className="flex flex-col items-center gap-2 p-8"
        data-testid="document-panel"
      >
        <Text as="p" mainUiBody text03>
          {t("documentPanel.loadError")}
        </Text>
        <Button prominence="secondary" size="sm" onClick={() => void mutate()}>
          {t("documentPanel.retry")}
        </Button>
      </div>
    );
  }
  // The announced head can arrive before the refetched revision list; wait for
  // it instead of labelling the header with another draft.
  const summary =
    document && viewed !== null
      ? document.revisions.find((r) => r.revision_no === viewed)
      : undefined;
  if (!document || viewed === null || !summary) {
    return (
      <div
        className="flex flex-col h-full min-h-0 bg-background-tint-00"
        data-testid="document-panel"
      >
        <DocumentPanelSkeleton />
      </div>
    );
  }

  return (
    <div
      className="flex flex-col h-full min-h-0 bg-background-tint-00"
      data-testid="document-panel"
    >
      <DocumentPanelHeader
        document={document}
        revision={summary}
        maximized={maximized}
        onToggleMaximize={onToggleMaximize}
        onClose={requestClose}
        canEdit={!editing && Boolean(viewedRevision)}
        onEdit={() =>
          viewedRevision && editDraft(viewed, viewedRevision.content)
        }
        actions={
          <ExportMenu
            documentId={documentId}
            revisionNo={viewed}
            kind={document.kind}
            sourceFormat={viewedRevision?.source_format ?? "markdown"}
          />
        }
      >
        <RevisionSwitcher
          revisions={document.revisions}
          selected={viewed}
          onSelect={selectRevision}
        />
      </DocumentPanelHeader>

      {pendingHead !== null && pendingHead > viewed && (
        <NewDraftNotice
          revisionNo={pendingHead}
          onView={() => selectRevision(pendingHead)}
        />
      )}
      {!editing && head !== null && viewed < head && (
        <OldRevisionBanner
          busy={restoring}
          onGoToLatest={() => selectRevision(head)}
          onContinue={() => void restore(viewed, head)}
        />
      )}

      {editing ? (
        // The editor and its preview share the page surface, so writing and
        // reading never straddle two background colours.
        <DocumentReadingSurface className="flex flex-col flex-1 min-h-0">
          <EditTab
            document={document}
            onRequestMermaidFix={onRequestMermaidFix}
          />
        </DocumentReadingSurface>
      ) : (
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as DocumentPanelTab)}
        >
          <Tabs.List variant="underline">
            {TABS.map((tab) => (
              <Tabs.Trigger key={tab} value={tab}>
                {t(`documentPanel.tabs.${tab}`)}
                {tab === "history" && ` ${document.revisions.length}`}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          <div className="flex-1 min-h-0 overflow-auto">
            {/* The preview tab is the document page: the whole viewport takes
                the page colour, so nothing sits on a second surface. The diff
                and history tools keep the app surface. */}
            <DocumentReadingSurface
              enabled={tab === "preview"}
              className="min-h-full"
            >
              <Tabs.Content value="preview">
                <PreviewTab
                  documentId={documentId}
                  revisionNo={viewed}
                  onRequestMermaidFix={onRequestMermaidFix}
                />
              </Tabs.Content>
              <Tabs.Content value="changes">
                <ChangesTab document={document} revisionNo={viewed} />
              </Tabs.Content>
              <Tabs.Content value="compare">
                <CompareTab document={document} viewed={viewed} />
              </Tabs.Content>
              <Tabs.Content value="history">
                <HistoryTab document={document} viewed={viewed} />
              </Tabs.Content>
            </DocumentReadingSurface>
          </div>
        </Tabs>
      )}
    </div>
  );
}
