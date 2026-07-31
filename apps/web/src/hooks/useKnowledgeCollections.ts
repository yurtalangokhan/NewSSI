"use client";

import { useEffect, useState } from "react";

export interface KnowledgeCollection {
  id: string;
  name: string;
  connector_type: string;
  sync_status: string;
}

export interface KnowledgeCollections {
  document_processing: KnowledgeCollection[];
  knowledge_graph: KnowledgeCollection[];
}

export function useKnowledgeCollections(enabled: boolean): {
  collections: KnowledgeCollections | null;
  isLoading: boolean;
} {
  const [collections, setCollections] = useState<KnowledgeCollections | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    setIsLoading(true);

    fetch(`/api/datasources/knowledge-selector?ts=${Date.now()}`, {
      cache: "no-store",
    })
      .then((r) => r.json())
      .then((data: KnowledgeCollections) => {
        if (!cancelled) setCollections(data);
      })
      .catch(() => {
        if (!cancelled) setCollections({ document_processing: [], knowledge_graph: [] });
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { collections, isLoading };
}
