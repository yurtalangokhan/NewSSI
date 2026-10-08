import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";

import {
  fetchStandardAnswerCategories,
  fetchStandardAnswers,
} from "@/lib/api/domains/knowledge/api";
import { StandardAnswerCategory, StandardAnswer } from "@/lib/types";
import useSWR, { mutate } from "swr";

export const useStandardAnswerCategories = () => {
  const url = agentsEndpoints.standardAnswerCategory.browserPath;
  const swrResponse = useSWR<StandardAnswerCategory[]>(
    url,
    fetchStandardAnswerCategories
  );

  return {
    ...swrResponse,
    refreshStandardAnswerCategories: () => mutate(url),
  };
};

export const useStandardAnswers = () => {
  const url = knowledgeEndpoints.listStandardAnswers.browserPath;
  const swrResponse = useSWR<StandardAnswer[]>(url, fetchStandardAnswers);

  return {
    ...swrResponse,
    refreshStandardAnswers: () => mutate(url),
  };
};
