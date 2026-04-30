"use client";

import { useRef } from "react";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { SvgUnplug } from "@opal/icons";
import { useTranslation } from "react-i18next";
interface DisconnectEntityModalProps {
  isOpen: boolean;
  onClose: () => void;
  name: string | null;
  onConfirmDisconnect: () => void;
  onConfirmDisconnectAndDelete?: () => void;
  isDisconnecting?: boolean;
  skipOverlay?: boolean;
}

export default function DisconnectEntityModal({
  isOpen,
  onClose,
  name,
  onConfirmDisconnect,
  onConfirmDisconnectAndDelete,
  isDisconnecting = false,
  skipOverlay = false,
}: DisconnectEntityModalProps) {
  const { t } = useTranslation();
  const disconnectButtonRef = useRef<HTMLButtonElement>(null);

  if (!name) return null;

  return (
    <Modal
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <Modal.Content
        width="sm"
        preventAccidentalClose={false}
        skipOverlay={skipOverlay}
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          disconnectButtonRef.current?.focus();
        }}
      >
        <Modal.Header
          icon={({ className }) => (
            <SvgUnplug className={cn(className, "stroke-action-danger-05")} />
          )}
          title={t("admin.mcp.disconnectTitle", { name })}
          onClose={onClose}
        />

        <Modal.Body>
          <Text as="p" text03 mainUiBody>
            {t("admin.mcp.disconnectWarning", { name })}
          </Text>
          <Text as="p" text03 mainUiBody>
            {t("admin.mcp.disconnectConfirm")}
          </Text>
        </Modal.Body>

        <Modal.Footer>
          <Button main secondary onClick={onClose} disabled={isDisconnecting}>
            {t("modals.cancel")}
          </Button>
          {onConfirmDisconnectAndDelete && (
            <Button
              danger
              secondary
              onClick={onConfirmDisconnectAndDelete}
              disabled={isDisconnecting}
            >
              {t("admin.mcp.disconnectAndDelete")}
            </Button>
          )}
          <Button
            danger
            primary
            onClick={onConfirmDisconnect}
            disabled={isDisconnecting}
            ref={disconnectButtonRef}
          >
            {isDisconnecting
              ? t("admin.mcp.disconnecting")
              : t("admin.mcp.disconnect")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
