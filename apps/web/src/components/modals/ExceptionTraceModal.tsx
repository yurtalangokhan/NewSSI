import { useState } from "react";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import { SvgAlertTriangle, SvgCheck, SvgCopy } from "@opal/icons";
import { useTranslation } from "react-i18next";

interface ExceptionTraceModalProps {
  onOutsideClick: () => void;
  exceptionTrace: string;
}

export default function ExceptionTraceModal({
  onOutsideClick,
  exceptionTrace,
}: ExceptionTraceModalProps) {
  const { t } = useTranslation("modals");
  const [copyClicked, setCopyClicked] = useState(false);

  return (
    <Modal open onOpenChange={onOutsideClick}>
      <Modal.Content width="lg" height="full">
        <Modal.Header
          icon={SvgAlertTriangle}
          title={t("exceptionTraceTitle")}
          onClose={onOutsideClick}
          height="fit"
        />
        <Modal.Body>
          <div className="mb-6">
            {!copyClicked ? (
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(exceptionTrace!);
                  setCopyClicked(true);
                  setTimeout(() => setCopyClicked(false), 2000);
                }}
                className="flex w-fit items-center hover:bg-accent-background p-2 border-border border rounded"
              >
                <Text>{t("copyTrace")}</Text>
                <SvgCopy className="stroke-text-04 ml-2 h-4 w-4 flex flex-shrink-0" />
              </button>
            ) : (
              <div className="flex w-fit items-center hover:bg-accent-background p-2 border-border border rounded cursor-default">
                <Text>{t("copiedToClipboard")}</Text>
                <SvgCheck className="stroke-text-04 my-auto ml-2 h-4 w-4 flex flex-shrink-0" />
              </div>
            )}
          </div>
          <div className="whitespace-pre-wrap">{exceptionTrace}</div>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}

