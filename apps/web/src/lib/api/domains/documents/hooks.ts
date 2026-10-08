"use client";

import { useCallback } from "react";
import useSWR, { mutate } from "swr";
import {
  fetchAuthoredDocument,
  fetchRevision,
} from "@/lib/api/domains/documents/api";
import { documentsEndpoints } from "@/lib/api/domains/documents/endpoints";
import type {
  DocumentDetail,
  RevisionDetail,
} from "@/lib/api/domains/documents/types";
import type { FetchError } from "@/lib/api/http/errors";

export const documentKeys = {
  document: (documentId: string) =>
    documentsEndpoints.getDocument(documentId).browserPath,
  revision: (documentId: string, revisionNo: number) =>
    documentsEndpoints.getRevision(documentId, revisionNo).browserPath,
};

/** Head + revision list. Revalidated when a new draft is announced. */
export function useAuthoredDocument(documentId: string | null) {
  return useSWR<DocumentDetail, FetchError>(
    documentId ? documentKeys.document(documentId) : null,
    () => fetchAuthoredDocument(documentId!),
    { revalidateOnFocus: false }
  );
}

/** Revisions are append-only and never change, so they are fetched once. */
export function useRevision(
  documentId: string | null,
  revisionNo: number | null
) {
  return useSWR<RevisionDetail, FetchError>(
    documentId && revisionNo
      ? documentKeys.revision(documentId, revisionNo)
      : null,
    () => fetchRevision(documentId!, revisionNo!),
    {
      revalidateIfStale: false,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );
}

export function useRevisionPair(
  documentId: string | null,
  leftNo: number | null,
  rightNo: number | null
) {
  const left = useRevision(documentId, leftNo);
  const right = useRevision(documentId, rightNo);
  const { mutate: mutateLeft } = left;
  const { mutate: mutateRight } = right;
  const retry = useCallback(
    async () => void (await Promise.all([mutateLeft(), mutateRight()])),
    [mutateLeft, mutateRight]
  );
  return {
    left,
    right,
    isLoading: left.isLoading || right.isLoading,
    error: left.error ?? right.error,
    /** Revalidates both sides (a side that has no key is a no-op). */
    retry,
  };
}

export async function refreshAuthoredDocument(
  documentId: string
): Promise<void> {
  await mutate(documentKeys.document(documentId));
}
