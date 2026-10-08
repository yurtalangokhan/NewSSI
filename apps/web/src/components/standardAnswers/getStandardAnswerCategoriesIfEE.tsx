import { StandardAnswerCategory } from "@/lib/types";
import { fetchStandardAnswerCategoriesSS } from "@/lib/api/domains/knowledge/server";
import { appSettings } from "@/lib/settings";

export type StandardAnswerCategoryResponse =
  | EEStandardAnswerCategoryResponse
  | NoEEAvailable;

interface NoEEAvailable {
  paidEnterpriseFeaturesEnabled: false;
}

interface EEStandardAnswerCategoryResponse {
  paidEnterpriseFeaturesEnabled: true;
  error?: {
    message: string;
  };
  categories?: StandardAnswerCategory[];
}

export async function getStandardAnswerCategoriesIfEE(): Promise<StandardAnswerCategoryResponse> {
  if (!appSettings.SERVER_SIDE_ONLY__PAID_ENTERPRISE_FEATURES_ENABLED) {
    return {
      paidEnterpriseFeaturesEnabled: false,
    };
  }

  const standardAnswerCategoriesResponse =
    await fetchStandardAnswerCategoriesSS();
  if (!standardAnswerCategoriesResponse.ok) {
    return {
      paidEnterpriseFeaturesEnabled: true,
      error: {
        message: await standardAnswerCategoriesResponse.text(),
      },
    };
  }

  const categories =
    (await standardAnswerCategoriesResponse.json()) as StandardAnswerCategory[];

  return {
    paidEnterpriseFeaturesEnabled: true,
    categories,
  };
}
