import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

import { fetchDocumentSets } from "@/lib/api/domains/knowledge/api";
import { DocumentSetSummary } from "@/lib/types";
import useSWR, { mutate } from "swr";

const DOCUMENT_SETS_URL = knowledgeEndpoints.documentSets.browserPath;
const GET_EDITABLE_DOCUMENT_SETS_URL =
  knowledgeEndpoints.editableDocumentSetsKey.browserPath;

export function refreshDocumentSets() {
  mutate(DOCUMENT_SETS_URL);
}

export function useDocumentSets(getEditable: boolean = false) {
  const url = getEditable ? GET_EDITABLE_DOCUMENT_SETS_URL : DOCUMENT_SETS_URL;

  const swrResponse = useSWR<DocumentSetSummary[]>(url, () =>
    fetchDocumentSets(getEditable)
  );

  return {
    ...swrResponse,
    refreshDocumentSets: refreshDocumentSets,
  };
}
