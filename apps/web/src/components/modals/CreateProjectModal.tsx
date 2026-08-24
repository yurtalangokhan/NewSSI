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
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
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
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Reset when prop changes or modal closes/opens
  useEffect(() => {
    setProjectName(initialProjectName ?? "");
    setIsSubmitting(false);
  }, [initialProjectName, modal.isOpen]);

  async function handleSubmit() {
    if (isSubmitting) return;

    const name = projectName.trim();
    if (!name) return;

    setIsSubmitting(true);
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
    } finally {
      setIsSubmitting(false);
    }
  }

  useKeyPress(
    handleSubmit,
    "Enter",
    modal.isOpen && !isSubmitting && projectName.trim().length > 0
  );

  return (
    <>
      <Modal
        open={modal.isOpen}
        onOpenChange={(open) => {
          if (!isSubmitting) {
            modal.toggle(open);
          }
        }}
      >
        <Modal.Content width="sm">
          <Modal.Header
            icon={SvgFolderPlus}
            title={t("modals.createProject.title")}
            description={t("modals.createProject.description")}
            onClose={() => !isSubmitting && modal.toggle(false)}
          />
          <Modal.Body>
            <InputLayouts.Vertical title={t("modals.createProject.nameLabel")}>
              <InputTypeIn
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder={t("modals.createProject.namePlaceholder")}
                showClearButton={!isSubmitting}
                variant={isSubmitting ? "disabled" : "primary"}
                readOnly={isSubmitting}
              />
            </InputLayouts.Vertical>
          </Modal.Body>
          <Modal.Footer>
            <Button
              secondary
              disabled={isSubmitting}
              onClick={() => modal.toggle(false)}
            >
              {t("modals.cancel")}
            </Button>
            <Button
              disabled={isSubmitting || !projectName.trim()}
              leftIcon={isSubmitting ? SimpleLoader : undefined}
              onClick={handleSubmit}
            >
              {isSubmitting
                ? t("modals.createProject.creatingButton", {
                    defaultValue: "Creating...",
                  })
                : t("modals.createProject.createButton")}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </>
  );
}