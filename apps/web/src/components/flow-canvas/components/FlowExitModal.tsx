"use client";

import { useTranslation } from "react-i18next";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import { Button } from "@opal/components";
import { SvgWorkflow } from "@opal/icons";

export type FlowExitModalProps = {
  /** The version that stays live for everyone chatting with this flow, or
   * null when nothing has ever been published. */
  publishedVersionNo: number | null;
  isDiscarding: boolean;
  onKeep: () => void;
  onDiscard: () => void;
  onCancel: () => void;
};

/**
 * Leaving the studio with an unpublished draft: keep it, or throw it away.
 *
 * Built like its sibling PublishFlowModal — a plain Modal — rather than via
 * ConfirmationModalLayout. That layout takes its prose as the header's
 * `description` and fills Modal.Body from `children`, so a dialog with no
 * children rendered an empty tinted strip under the header; and its footer
 * contributes its own Cancel from `@opal/components` while the caller
 * passed actions built from `refresh-components`' Button, leaving three
 * mismatched buttons in a row. Here all three are the same component, with
 * discard as the one destructive action.
 */
export function FlowExitModal({
  publishedVersionNo,
  isDiscarding,
  onKeep,
  onDiscard,
  onCancel,
}: FlowExitModalProps) {
  const { t } = useTranslation();

  return (
    <Modal open onOpenChange={(isOpen) => !isOpen && onCancel()}>
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgWorkflow}
          title={t("flowStudio.exitTitle", "You have an unpublished draft")}
          onClose={onCancel}
        />
        <Modal.Body data-testid="flow-exit-body">
          <Text as="p" data-testid="flow-exit-explanation">
            {publishedVersionNo
              ? t(
                  "flowStudio.exitKeepsPublished",
                  `v${publishedVersionNo} stays published for everyone chatting with this flow.`,
                  { version: publishedVersionNo }
                )
              : t(
                  "flowStudio.exitNothingPublished",
                  "Discarding leaves this flow with no content at all."
                )}
          </Text>
        </Modal.Body>
        <Modal.Footer>
          <Button
            data-testid="flow-exit-cancel"
            prominence="secondary"
            onClick={onCancel}
          >
            {t("modals.cancel")}
          </Button>
          <Button
            data-testid="flow-exit-discard"
            variant="danger"
            prominence="secondary"
            disabled={isDiscarding}
            onClick={onDiscard}
          >
            {t("flowStudio.exitDiscard", "Discard changes")}
          </Button>
          <Button data-testid="flow-exit-keep" onClick={onKeep}>
            {t("flowStudio.exitKeep", "Keep draft")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
