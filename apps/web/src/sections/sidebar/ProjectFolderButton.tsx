"use client";

import React, { useState, memo } from "react";
import { Project, useProjectsContext } from "@/providers/ProjectsContext";
import { useDroppable, useDndContext } from "@dnd-kit/core";
import LineItem from "@/refresh-components/buttons/LineItem";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Button from "@/refresh-components/buttons/Button";
import ChatButton from "@/sections/sidebar/ChatButton";
import { useAppRouter } from "@/hooks/appNavigation";
import { cn, noProp } from "@/lib/utils";
import { DRAG_TYPES } from "./constants";
import SidebarTab from "@/refresh-components/buttons/SidebarTab";
import IconButton from "@/refresh-components/buttons/IconButton";
import { Button as OpalButton } from "@opal/components";
import ButtonRenaming from "@/refresh-components/buttons/ButtonRenaming";
import type { IconProps } from "@opal/types";
import useAppFocus from "@/hooks/useAppFocus";
import {
  SvgEdit,
  SvgFolder,
  SvgFolderOpen,
  SvgFolderPartialOpen,
  SvgFolderIn,
  SvgMoreHorizontal,
  SvgTrash,
} from "@opal/icons";
import { useTranslation } from "react-i18next";
import { motion, AnimatePresence } from "motion/react";

export interface ProjectFolderButtonProps {
  project: Project;
}

const ProjectFolderButton = memo(({ project }: ProjectFolderButtonProps) => {
  const route = useAppRouter();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [deleteConfirmationModalOpen, setDeleteConfirmationModalOpen] =
    useState(false);
  const { renameProject, deleteProject, currentProjectId } =
    useProjectsContext();
  const [isEditing, setIsEditing] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [isHoveringIcon, setIsHoveringIcon] = useState(false);
  const [allowHoverEffect, setAllowHoverEffect] = useState(true);
  const activeSidebar = useAppFocus();

  // Make project droppable
  const dropId = `project-${project.id}`;
  const { setNodeRef, isOver } = useDroppable({
    id: dropId,
    data: {
      type: DRAG_TYPES.PROJECT,
      project,
    },
  });

  const dndContext = useDndContext?.() ?? {};
  const active = dndContext.active;
  const isDraggingChat = active?.data?.current?.type === DRAG_TYPES.CHAT;
  const isChatAlreadyInThisProject =
    active?.data?.current?.projectId === project.id;
  const isDropTarget = isOver && isDraggingChat && !isChatAlreadyInThisProject;

  function getFolderIcon(): React.FunctionComponent<IconProps> {
    if (open) {
      return SvgFolderOpen;
    } else {
      return isHoveringIcon && allowHoverEffect
        ? SvgFolderPartialOpen
        : SvgFolder;
    }
  }

  function handleIconClick() {
    setOpen((prev) => !prev);
    setAllowHoverEffect(false);
  }

  function handleIconHover(hovering: boolean) {
    setIsHoveringIcon(hovering);
    // Re-enable hover effects when cursor leaves the icon
    if (!hovering) {
      setAllowHoverEffect(true);
    }
  }

  function handleTextClick() {
    route({ projectId: project.id });
  }

  async function handleRename(newName: string) {
    await renameProject(project.id, newName);
  }

  const popoverItems = [
    <LineItem
      key="rename-project"
      icon={SvgEdit}
      onClick={noProp(() => setIsEditing(true))}
    >
      {t("sidebar.renameProject")}
    </LineItem>,
    null,
    <LineItem
      key="delete-project"
      icon={SvgTrash}
      onClick={noProp(() => setDeleteConfirmationModalOpen(true))}
      danger
    >
      {t("sidebar.deleteProject")}
    </LineItem>,
  ];

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "transition-colors duration-200",
        isOver && "bg-background-tint-03 rounded-08"
      )}
    >
      {/* Confirmation Modal (only for deletion) */}
      {deleteConfirmationModalOpen && (
        <ConfirmationModalLayout
          title={t("sidebar.deleteProjectTitle")}
          icon={SvgTrash}
          onClose={() => setDeleteConfirmationModalOpen(false)}
          submit={
            <Button
              danger
              onClick={() => {
                setDeleteConfirmationModalOpen(false);
                deleteProject(project.id);
              }}
            >
              {t("sidebar.delete")}
            </Button>
          }
        >
          {t("sidebar.deleteProjectConfirmation")}
        </ConfirmationModalLayout>
      )}

      {/* Project Folder */}
      <Popover onOpenChange={setPopoverOpen}>
        <Popover.Anchor>
          <SidebarTab
            leftIcon={() => (
              <OpalButton
                onMouseEnter={() => handleIconHover(true)}
                onMouseLeave={() => handleIconHover(false)}
                icon={getFolderIcon()}
                prominence="tertiary"
                size="sm"
                onClick={noProp(handleIconClick)}
              />
            )}
            transient={
              currentProjectId === project.id &&
              (activeSidebar.isProject() || activeSidebar.isChat())
            }
            onClick={noProp(handleTextClick)}
            focused={isEditing}
            rightChildren={
              <>
                <Popover.Trigger asChild onClick={noProp()}>
                  <div>
                    <IconButton
                      icon={SvgMoreHorizontal}
                      className={cn(
                        !popoverOpen && "hidden",
                        !isEditing && "group-hover/SidebarTab:flex"
                      )}
                      transient={popoverOpen}
                      internal
                    />
                  </div>
                </Popover.Trigger>

                <Popover.Content side="right" align="end" width="md">
                  <PopoverMenu>{popoverItems}</PopoverMenu>
                </Popover.Content>
              </>
            }
          >
            {isEditing ? (
              <ButtonRenaming
                initialName={project.name}
                onRename={handleRename}
                onClose={() => setIsEditing(false)}
              />
            ) : (
              project.name
            )}
          </SidebarTab>
        </Popover.Anchor>
      </Popover>

      {/* Drop Target Indicator Box */}
      <AnimatePresence>
        {isDropTarget && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div
              data-testid="project-drop-zone"
              className={cn(
                "my-1 flex items-center justify-center gap-2 rounded-08 px-3 py-2",
                "border border-dashed border-action-link-05",
                "bg-action-link-01/30 text-action-link-05 shadow-sm select-none"
              )}
            >
              <SvgFolderIn className="h-4 w-4 shrink-0 animate-pulse" />
              <span className="text-xs font-medium tracking-tight leading-tight">
                {t("sidebar.dropChatToProject")}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Project Chat-Sessions */}
      {open &&
        project.chat_sessions.map((chatSession) => (
          <ChatButton
            key={chatSession.id}
            chatSession={chatSession}
            project={project}
            draggable
          />
        ))}
    </div>
  );
});
ProjectFolderButton.displayName = "ProjectFolderButton";

export default ProjectFolderButton;
