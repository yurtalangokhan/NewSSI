import {
  CloudEmbeddingProvider,
  HostedEmbeddingModel,
} from "@/components/embedding/interfaces";

import {
  AdvancedSearchConfiguration,
  SavedSearchSettings,
  SwitchoverType,
} from "@/lib/api/domains/knowledge/search-settings-types";

import { EmbeddingProvider } from "@/lib/api/domains/knowledge/search-settings-types";
import { RerankingDetails } from "@/lib/api/domains/knowledge/search-settings-types";

// We use a spread operation to merge properties from multiple objects into a single object.
// Advanced embedding details may update default values.
// Do NOT modify the order unless you are positive the new hierarchy is correct.
export const combineSearchSettings = (
  selectedProvider: CloudEmbeddingProvider | HostedEmbeddingModel,
  advancedEmbeddingDetails: AdvancedSearchConfiguration,
  rerankingDetails: RerankingDetails,
  provider_type: EmbeddingProvider | null,
  switchover_type?: SwitchoverType
): SavedSearchSettings => {
  return {
    ...selectedProvider,
    ...advancedEmbeddingDetails,
    ...rerankingDetails,
    provider_type: provider_type,
    switchover_type,
  };
};
