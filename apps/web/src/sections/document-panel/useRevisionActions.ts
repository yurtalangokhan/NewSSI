"use client";

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import { toast } from "@/hooks/useToast";
import {
  DiagramInvalidError,
  DocumentNoChangeError,
  RevisionConflictError,
  restoreRevision,
} from "@/lib/api/domains/documents/api";
import { refreshAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import { FetchError } from "@/lib/api/http/errors";

export function useRevisionActions(documentId: string) {
  const { t } = useTranslation();
  const [restoring, setRestoring] = useState(false);

  const restore = useCallback(
    async (revisionNo: number, headRevisionNo: number) => {
      setRestoring(true);
      try {
        let result;
        try {
          result = await restoreRevision(
            documentId,
            revisionNo,
            headRevisionNo
          );
        } catch (error) {
          if (!(error instanceof RevisionConflictError)) throw error;
          // Restoring is an explicit "make X current" request, so a newer head
          // only changes the base — the intent stays the same.
          result = await restoreRevision(
            documentId,
            revisionNo,
            error.headRevisionNo
          );
        }
        const created = result.revision.revision_no;
        const store = useDocumentPanelStore.getState();
        store.syncHead(documentId, created);
        store.selectRevision(created);
        await refreshAuthoredDocument(documentId);
        toast.success(
          t("documentPanel.restoreDone", { revision: revisionNo, created })
        );
      } catch (error) {
        if (error instanceof DocumentNoChangeError) {
          toast.info(t("documentPanel.restoreNoChange"));
        } else if (error instanceof DiagramInvalidError) {
          toast.error(t("documentPanel.restoreDiagramInvalid"));
        } else if (error instanceof FetchError && error.message) {
          // The server already localizes its domain messages.
          toast.error(error.message);
        } else {
          toast.error(t("documentPanel.restoreFailed"));
        }
      } finally {
        setRestoring(false);
      }
    },
    [documentId, t]
  );

  return { restore, restoring };
}
