"use client";
import { fetchKnowledgeSelector } from "@/lib/api/domains/datasources/api";
import { errorMessageFromUnknown } from "@/lib/api/http/errors";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
  error: string | null;
} {
  const { i18n } = useTranslation();
  const [collections, setCollections] = useState<KnowledgeCollections | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    fetchKnowledgeSelector<KnowledgeCollections>(Date.now())
      .then((data: KnowledgeCollections) => {
        if (!cancelled) setCollections(data);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(errorMessageFromUnknown(caught));
          setCollections({ document_processing: [], knowledge_graph: [] });
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, i18n.language]);

  return { collections, isLoading, error };
}
