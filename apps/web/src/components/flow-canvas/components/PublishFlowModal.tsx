"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import { Button } from "@opal/components";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { SvgGlobe } from "@opal/icons";

export type PublishFlowModalProps = {
  nextVersionNo: number;
  currentVersionNo: number | null;
  isPublishing: boolean;
  onConfirm: (notes: string) => void;
  onClose: () => void;
};

/**
 * Publishing is the one action here that changes what production runs, so
 * it gets a deliberate confirmation rather than a bare button: the author
 * sees which version number they are about to create and can leave a note
 * that shows up in the history panel (agent_flow_versions.notes).
 */
export function PublishFlowModal({
  nextVersionNo,
  currentVersionNo,
  isPublishing,
  onConfirm,
  onClose,
}: PublishFlowModalProps) {
  const { t } = useTranslation();
  const [notes, setNotes] = useState("");

  return (
    <Modal open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgGlobe}
          title={t("flowStudio.publishModalTitle", "Publish flow")}
          onClose={onClose}
        />
        <Modal.Body>
          <Text as="p" data-testid="publish-modal-target">
            {currentVersionNo
              ? t(
                  "flowStudio.publishReplacing",
                  `This will publish version ${nextVersionNo}, replacing v${currentVersionNo}.`,
                  { next: nextVersionNo, current: currentVersionNo }
                )
              : t(
                  "flowStudio.publishFirst",
                  `This will publish version ${nextVersionNo} — the first published version.`,
                  { next: nextVersionNo }
                )}
          </Text>
          <InputTypeIn
            data-testid="publish-modal-notes"
            placeholder={t(
              "flowStudio.publishNotesPlaceholder",
              "What changed? (optional)"
            )}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button prominence="secondary" onClick={onClose}>
            {t("modals.cancel")}
          </Button>
          <Button
            data-testid="publish-modal-confirm"
            disabled={isPublishing}
            onClick={() => onConfirm(notes)}
          >
            {t("flowStudio.publishConfirm", "Publish")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
