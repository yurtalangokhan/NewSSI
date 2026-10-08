"use client";

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgAlertTriangle } from "@/icons";
import {
  selectIsDirty,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";

/**
 * Protects the user's unsaved edit: asks before any navigation the store holds
 * back, and warns the browser while a reload or tab close would lose it.
 */
export function UnsavedEditsGuard() {
  const { t } = useTranslation();
  const dirty = useDocumentPanelStore(selectIsDirty);
  const pending = useDocumentPanelStore((s) => s.pendingDiscard !== null);
  const confirmDiscard = useDocumentPanelStore((s) => s.confirmDiscard);
  const keepEditing = useDocumentPanelStore((s) => s.keepEditing);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Legacy browsers only show the prompt when returnValue is set.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (!pending) return null;
  return (
    <ConfirmationModalLayout
      icon={SvgAlertTriangle}
      title={t("documentPanel.unsaved.title")}
      onClose={keepEditing}
      hideCancel
      submit={
        <>
          <Button prominence="secondary" onClick={keepEditing}>
            {t("documentPanel.unsaved.keepEditing")}
          </Button>
          <Button variant="danger" onClick={confirmDiscard}>
            {t("documentPanel.unsaved.discard")}
          </Button>
        </>
      }
    >
      {t("documentPanel.unsaved.body")}
    </ConfirmationModalLayout>
  );
}
