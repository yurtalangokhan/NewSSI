"use client";

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  type PropsWithChildren,
} from "react";
import { useGraphData, useGraphBuild, useGraphSearch } from "../hooks/use-graph-rag";

// ============================================================================
// Context Type
// ============================================================================

interface GraphRAGContextType {
  /** Currently selected collection for graph operations */
  selectedCollectionId: string | null;
  setSelectedCollectionId: (id: string | null) => void;

  /** Graph data hooks */
  graphDataHook: ReturnType<typeof useGraphData>;
  graphBuildHook: ReturnType<typeof useGraphBuild>;
  graphSearchHook: ReturnType<typeof useGraphSearch>;

  /** Convenience: reload graph data for current collection */
  refreshCurrentGraph: () => Promise<void>;
}

// ============================================================================
// Context
// ============================================================================

const GraphRAGContext = createContext<GraphRAGContextType | null>(null);

// ============================================================================
// Provider
// ============================================================================

export const GraphRAGProvider: React.FC<PropsWithChildren> = ({ children }) => {
  const [selectedCollectionId, setSelectedCollectionId] = useState<
    string | null
  >(null);

  const graphDataHook = useGraphData();
  const graphBuildHook = useGraphBuild();
  const graphSearchHook = useGraphSearch();

  const refreshCurrentGraph = useCallback(async () => {
    if (!selectedCollectionId) return;
    await Promise.all([
      graphDataHook.fetchGraphData(selectedCollectionId),
      graphDataHook.fetchStats(selectedCollectionId),
    ]);
  }, [selectedCollectionId, graphDataHook]);

  return (
    <GraphRAGContext.Provider
      value={{
        selectedCollectionId,
        setSelectedCollectionId,
        graphDataHook,
        graphBuildHook,
        graphSearchHook,
        refreshCurrentGraph,
      }}
    >
      {children}
    </GraphRAGContext.Provider>
  );
};

// ============================================================================
// Hook
// ============================================================================

export const useGraphRAGContext = () => {
  const context = useContext(GraphRAGContext);
  if (context === null) {
    throw new Error(
      "useGraphRAGContext must be used within a GraphRAGProvider",
    );
  }
  return context;
};
