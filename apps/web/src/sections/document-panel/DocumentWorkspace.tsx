"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";
import { SvgFileText } from "@/icons";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";
import Modal from "@/refresh-components/Modal";
import { UnsavedEditsGuard } from "@/sections/document-panel/UnsavedEditsGuard";

interface PanelLayout {
  maximized: boolean;
  onToggleMaximize?: () => void;
}

interface DocumentWorkspaceProps {
  children: ReactNode;
  isMobile: boolean;
  renderPanel: (layout: PanelLayout) => ReactNode;
}

export function DocumentWorkspace({
  children,
  isMobile,
  renderPanel,
}: DocumentWorkspaceProps) {
  const { t } = useTranslation();
  const isOpen = useDocumentPanelStore((s) => s.isOpen);
  const requestClose = useDocumentPanelStore((s) => s.requestClose);
  const setHostMounted = useDocumentPanelStore((s) => s.setHostMounted);
  const chatRef = usePanelRef();
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    setHostMounted(true);
    return () => setHostMounted(false);
  }, [setHostMounted]);

  useEffect(() => {
    if (!isOpen) setMaximized(false);
  }, [isOpen]);

  // Dragging the separator can collapse or restore the chat too, so the
  // maximize state follows the chat panel's real size.
  const syncMaximized = useCallback(
    (size: { asPercentage: number }) => setMaximized(size.asPercentage === 0),
    []
  );

  const toggleMaximize = useCallback(() => {
    const chat = chatRef.current;
    if (!chat) return;
    if (chat.isCollapsed()) {
      chat.expand();
      setMaximized(false);
    } else {
      chat.collapse();
      setMaximized(true);
    }
  }, [chatRef]);

  return (
    <>
      {/* The Group and the chat Panel are always rendered so the chat subtree keeps its identity. */}
      <Group orientation="horizontal" className="flex-1 min-w-0 h-full">
        <Panel
          id="chat"
          panelRef={chatRef}
          minSize={360}
          collapsible
          collapsedSize={0}
          onResize={syncMaximized}
        >
          {children}
        </Panel>
        {isOpen && !isMobile && (
          <>
            <Separator className="w-px bg-border-01 hover:bg-border-03 data-[separator-state=drag]:bg-theme-primary-05 transition-colors" />
            <Panel id="document" defaultSize="50" minSize={420}>
              {renderPanel({ maximized, onToggleMaximize: toggleMaximize })}
            </Panel>
          </>
        )}
      </Group>
      {isOpen && isMobile && (
        <Modal
          open
          onOpenChange={(open) => {
            if (!open) requestClose();
          }}
        >
          <Modal.Content
            width="lg"
            height="full"
            preventAccidentalClose={false}
          >
            <Modal.Header
              icon={SvgFileText}
              title={t("documentPanel.sheetTitle")}
            />
            <div className="flex-1 min-h-0">
              {renderPanel({ maximized: true })}
            </div>
          </Modal.Content>
        </Modal>
      )}
      <UnsavedEditsGuard />
    </>
  );
}
