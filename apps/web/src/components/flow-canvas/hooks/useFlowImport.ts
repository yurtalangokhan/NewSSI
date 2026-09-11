import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { StoreApi } from "zustand";

import { toast } from "@/hooks/useToast";
import type { FlowStore } from "@/components/flow-canvas/stores/flowStore";
import {
  parseFlowJson,
  type ImportErrorCode,
  type ImportFlowResult,
} from "@/components/flow-canvas/utils/importFlow";

type ImportedGraph = Extract<ImportFlowResult, { success: true }>["graph"];

/** `true` for a file the canvas will try to import as a flow JSON. */
export function isFlowJsonFile(file: File): boolean {
  return file.type === "application/json" || file.name.endsWith(".json");
}

/**
 * Flow-JSON import: parse text / read a dropped file, snapshot, load into the
 * store and toast the outcome. Shared by FlowCanvas (canvas drop), the inline
 * designer (drop + file picker) and the import modal so the parse+snapshot+
 * toast sequence — and its i18n strings — live in exactly one place.
 */
export function useFlowImport(
  store: StoreApi<FlowStore>,
  /** Called after a successful load — e.g. to fit the viewport to the new graph. */
  onGraphLoaded?: () => void
) {
  const { t } = useTranslation();

  const toastImportError = useCallback(
    (code: ImportErrorCode) => {
      const detail = t(`flowCanvas.importErrors.${code}`);
      toast.error(
        t("flowCanvas.importError", "Import failed: {{error}}", {
          error: detail,
        })
      );
    },
    [t]
  );

  const loadGraph = useCallback(
    (graph: ImportedGraph, nodeCount: number, edgeCount: number) => {
      store.getState().takeSnapshot();
      store.getState().loadGraph(graph);
      onGraphLoaded?.();
      toast.success(
        t(
          "flowCanvas.importSuccess",
          "Flow imported successfully ({{nodes}} nodes, {{edges}} edges)",
          { nodes: nodeCount, edges: edgeCount }
        )
      );
    },
    [store, t, onGraphLoaded]
  );

  const importFromJsonText = useCallback(
    (content: string) => {
      const result = parseFlowJson(content);
      if (result.success) {
        loadGraph(result.graph, result.nodeCount, result.edgeCount);
      } else {
        toastImportError(result.errorCode);
      }
    },
    [loadGraph, toastImportError]
  );

  const importFromFile = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const content = event.target?.result;
        if (typeof content === "string") importFromJsonText(content);
      };
      reader.onerror = () => {
        toast.error(t("flowCanvas.fileUnreadable", "File could not be read"));
      };
      reader.readAsText(file);
    },
    [importFromJsonText, t]
  );

  return { importFromJsonText, importFromFile, loadGraph, toastImportError };
}
