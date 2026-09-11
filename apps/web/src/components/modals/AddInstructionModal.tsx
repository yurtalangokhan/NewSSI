"use client";

import { useEffect, useState } from "react";
import Button from "@/refresh-components/buttons/Button";
import { useProjectsContext } from "@/providers/ProjectsContext";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import { useModal } from "@/refresh-components/contexts/ModalContext";
import { SvgAddLines } from "@opal/icons";
import Modal from "@/refresh-components/Modal";
import { useTranslation } from "react-i18next";

export default function AddInstructionModal() {
  const { t } = useTranslation();
  const modal = useModal();
  const { currentProjectDetails, upsertInstructions } = useProjectsContext();
  const [instructionText, setInstructionText] = useState("");

  useEffect(() => {
    if (!modal.isOpen) return;
    const preset = currentProjectDetails?.project?.instructions ?? "";
    setInstructionText(preset);
  }, [modal.isOpen, currentProjectDetails?.project?.instructions]);

  async function handleSubmit() {
    const value = instructionText.trim();
    try {
      await upsertInstructions(value);
    } catch (e) {
      console.error("Failed to save instructions", e);
    }
    modal.toggle(false);
  }

  return (
    <Modal open={modal.isOpen} onOpenChange={modal.toggle}>
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgAddLines}
          title={t("modals.addInstruction.title")}
          description={t("modals.addInstruction.description")}
          onClose={() => modal.toggle(false)}
        />
        <Modal.Body>
          <InputTextArea
            value={instructionText}
            onChange={(event) => setInstructionText(event.target.value)}
            placeholder={t("modals.addInstruction.placeholder")}
          />
        </Modal.Body>
        <Modal.Footer>
          <Button secondary onClick={() => modal.toggle(false)}>
            {t("modals.cancel")}
          </Button>
          <Button onClick={handleSubmit}>
            {t("modals.addInstruction.saveButton")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
