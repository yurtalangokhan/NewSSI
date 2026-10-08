"use client";

import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { SvgFileText } from "@/icons";
import {
  initialDocumentPanelState,
  selectDocumentContext,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import { useAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import Chip from "@/refresh-components/Chip";

const stripExtension = (filename: string) => filename.replace(/\.[^.]+$/, "");

/** The document (and draft) every send carries while the panel is open. */
export function DocumentContextChip() {
  const { t } = useTranslation();
  // `selectDocumentContext` builds a new object each call, so select the
  // primitives and derive the ref from them instead of selecting it directly.
  const { isOpen, documentId, contextEnabled, revisionNo, knownHead } =
    useDocumentPanelStore(
      useShallow((s) => ({
        isOpen: s.isOpen,
        documentId: s.documentId,
        contextEnabled: s.contextEnabled,
        revisionNo: s.revisionNo,
        knownHead: s.knownHead,
      }))
    );
  const removeContext = useDocumentPanelStore((s) => s.removeContext);
  const context = selectDocumentContext({
    ...initialDocumentPanelState,
    isOpen,
    documentId,
    contextEnabled,
    revisionNo,
    knownHead,
  });
  const { data: document } = useAuthoredDocument(context?.document_id ?? null);

  if (!context || !document) return null;
  return (
    <div className="flex px-4 pt-2" data-testid="document-context-chip">
      <Chip icon={SvgFileText} onRemove={removeContext} smallLabel={false}>
        {t("documentPanel.contextChip", {
          title: document.title || stripExtension(document.filename),
          revision: context.revision_no,
        })}
      </Chip>
    </div>
  );
}
