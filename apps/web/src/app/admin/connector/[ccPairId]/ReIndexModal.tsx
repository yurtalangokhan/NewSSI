"use client";

import Button from "@/refresh-components/buttons/Button";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import { triggerIndexing } from "@/app/admin/connector/[ccPairId]/lib";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import Separator from "@/refresh-components/Separator";
import { SvgRefreshCw } from "@opal/icons";
// Hook to handle re-indexing functionality
export function useReIndexModal(
  connectorId: number | null,
  credentialId: number | null,
  ccPairId: number | null
) {
  const { t } = useTranslation("common", { keyPrefix: "admin.reIndexModal" });
  const [reIndexPopupVisible, setReIndexPopupVisible] = useState(false);

  const showReIndexModal = () => {
    if (connectorId == null || credentialId == null || ccPairId == null) {
      return;
    }
    setReIndexPopupVisible(true);
  };

  const hideReIndexModal = () => {
    setReIndexPopupVisible(false);
  };

  const triggerReIndex = async (fromBeginning: boolean) => {
    if (connectorId == null || credentialId == null || ccPairId == null) {
      return;
    }

    try {
      const result = await triggerIndexing(
        fromBeginning,
        connectorId,
        credentialId,
        ccPairId
      );

      // Show appropriate notification based on result
      if (result.success) {
        toast.success(
          fromBeginning
            ? t("completeReindexStarted")
            : t("indexingUpdateStarted")
        );
      } else {
        toast.error(result.message || t("failedToStartIndexing"));
      }
    } catch (error) {
      console.error("Failed to trigger indexing:", error);
      toast.error(t("unexpectedError"));
    }
  };

  const FinalReIndexModal =
    reIndexPopupVisible &&
    connectorId != null &&
    credentialId != null &&
    ccPairId != null ? (
      <ReIndexModal hide={hideReIndexModal} onRunIndex={triggerReIndex} />
    ) : null;

  return {
    showReIndexModal,
    ReIndexModal: FinalReIndexModal,
  };
}

export interface ReIndexModalProps {
  hide: () => void;
  onRunIndex: (fromBeginning: boolean) => Promise<void>;
}

export default function ReIndexModal({ hide, onRunIndex }: ReIndexModalProps) {
  const { t } = useTranslation("common", { keyPrefix: "admin.reIndexModal" });
  const [isProcessing, setIsProcessing] = useState(false);

  const handleRunIndex = async (fromBeginning: boolean) => {
    if (isProcessing) return;

    setIsProcessing(true);
    try {
      // First show immediate feedback with a toast
      toast.info(
        fromBeginning
          ? t("startingCompleteReindex")
          : t("startingIndexingUpdate")
      );

      // Then close the modal
      hide();

      // Then run the indexing operation
      await onRunIndex(fromBeginning);
    } catch (error) {
      console.error("Error starting indexing:", error);
      // Show error in toast if needed
      toast.error(t("failedToStartIndexingProcess"));
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <Modal open onOpenChange={hide}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header icon={SvgRefreshCw} title={t("title")} onClose={hide} />
        <Modal.Body>
          <Text as="p">{t("updateBody")}</Text>
          <Button onClick={() => handleRunIndex(false)} disabled={isProcessing}>
            {t("runUpdateButton")}
          </Button>

          <Separator />

          <Text as="p">{t("completeReindexBody")}</Text>
          <Text as="p">
            <strong>{t("noteLabel")}</strong> {t("noteBody")}
          </Text>

          <Button onClick={() => handleRunIndex(true)} disabled={isProcessing}>
            {t("runCompleteReindexButton")}
          </Button>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
