import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { getServerRequestHeaders } from "@/lib/api/server-context";

import type { BackendTarget } from "@/lib/api/http/types";

async function requestKnowledgeTarget(
  target: BackendTarget
): Promise<Response> {
  return backendRequest({
    ...target,
    credentials: "include",
    cache: "no-store",
    headers: await getServerRequestHeaders(),
  });
}

export function fetchDocumentSetsSS(): Promise<Response> {
  return requestKnowledgeTarget(knowledgeEndpoints.documentSets.backend);
}

export function fetchStandardAnswersSS(): Promise<Response> {
  return requestKnowledgeTarget(knowledgeEndpoints.listStandardAnswers.backend);
}

export function fetchStandardAnswerCategoriesSS(): Promise<Response> {
  return requestKnowledgeTarget(
    knowledgeEndpoints.listStandardAnswerCategories.backend
  );
}
