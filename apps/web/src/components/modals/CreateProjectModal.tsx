"use client";

import { useState, useEffect } from "react";
import Button from "@/refresh-components/buttons/Button";
import { useProjectsContext } from "@/providers/ProjectsContext";
import { useKeyPress } from "@/hooks/useKeyPress";
import * as InputLayouts from "@/layouts/input-layouts";
import { useAppRouter } from "@/hooks/appNavigation";
import { useModal } from "@/refresh-components/contexts/ModalContext";
import { SvgFolderPlus } from "@opal/icons";
import Modal from "@/refresh-components/Modal";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { toast } from "@/hooks/useToast";
import { useTranslation } from "react-i18next";

interface CreateProjectModalProps {
  initialProjectName?: string;
}

export default function CreateProjectModal({
  initialProjectName,
}: CreateProjectModalProps) {
  const { t } = useTranslation();
  const { createProject } = useProjectsContext();
  const modal = useModal();
  const route = useAppRouter();
  const [projectName, setProjectName] = useState(initialProjectName ?? "");

  // Reset when prop changes (modal reopens with different value)
  useEffect(() => {
    setProjectName(initialProjectName ?? "");
  }, [initialProjectName]);

  async function handleSubmit() {
    const name = projectName.trim();
    if (!name) return;

    try {
      const newProject = await createProject(name);
      route({ projectId: newProject.id });
      modal.toggle(false);
    } catch (e) {
      toast.error(
        t("modals.createProject.toastError", {
          name,
          defaultValue: `Failed to create the project ${name}`,
        })
      );
    }
  }

  useKeyPress(handleSubmit, "Enter");

  return (
    <>
      <Modal open={modal.isOpen} onOpenChange={modal.toggle}>
        <Modal.Content width="sm">
          <Modal.Header
            icon={SvgFolderPlus}
            title={t("modals.createProject.title")}
            description={t("modals.createProject.description")}
            onClose={() => modal.toggle(false)}
          />
          <Modal.Body>
            <InputLayouts.Vertical title={t("modals.createProject.nameLabel")}>
              <InputTypeIn
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder={t("modals.createProject.namePlaceholder")}
                showClearButton
              />
            </InputLayouts.Vertical>
          </Modal.Body>
          <Modal.Footer>
            <Button secondary onClick={() => modal.toggle(false)}>
              {t("modals.cancel")}
            </Button>
            <Button onClick={handleSubmit}>Create Project</Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </>
  );
}
