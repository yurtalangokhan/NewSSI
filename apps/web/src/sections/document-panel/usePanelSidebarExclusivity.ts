"use client";

import { useEffect, useRef } from "react";
import { useDocumentPanelStore } from "@/app/app/stores/useDocumentPanelStore";

/**
 * The Sources sidebar and the document panel never show together (spec §5.2).
 *
 * Both sides are driven by their rising edge: opening the panel pushes the
 * sources shut, and opening the sources closes the panel. Without the edge
 * check the two would fight whenever either one reports a change.
 */
export function usePanelSidebarExclusivity(
  sidebarVisible: boolean,
  setSidebarVisible: (visible: boolean) => void
) {
  const panelOpen = useDocumentPanelStore((s) => s.isOpen);
  const previous = useRef({ panelOpen, sidebarVisible });

  useEffect(() => {
    const was = previous.current;
    if (panelOpen && !was.panelOpen) {
      setSidebarVisible(false);
    } else if (sidebarVisible && !was.sidebarVisible && panelOpen) {
      // Unsaved edits keep the panel: the user decides, and declining hides
      // the sources again so the two never show together.
      useDocumentPanelStore.getState().guardUnsaved(
        () => useDocumentPanelStore.getState().close(),
        () => setSidebarVisible(false)
      );
    }
    previous.current = { panelOpen, sidebarVisible };
  }, [panelOpen, sidebarVisible, setSidebarVisible]);
}
