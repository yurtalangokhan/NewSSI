export enum EmbeddingProvider {
  OPENAI = "openai",
  COHERE = "cohere",
  VOYAGE = "voyage",
  GOOGLE = "google",
  LITELLM = "litellm",
  AZURE = "azure",
}

export interface RerankingDetails {
  rerank_model_name: string | null;
  rerank_provider_type: RerankerProvider | null;
  rerank_api_key: string | null;
  rerank_api_url: string | null;
}

export enum SwitchoverType {
  REINDEX = "reindex",
  ACTIVE_ONLY = "active_only",
  INSTANT = "instant",
}

export enum RerankerProvider {
  COHERE = "cohere",
  LITELLM = "litellm",
  BEDROCK = "bedrock",
}

export enum EmbeddingPrecision {
  FLOAT = "float",
  BFLOAT16 = "bfloat16",
}

export interface AdvancedSearchConfiguration {
  index_name: string | null;
  multipass_indexing: boolean;
  enable_contextual_rag: boolean;
  contextual_rag_llm_name: string | null;
  contextual_rag_llm_provider: string | null;
  multilingual_expansion: string[];
  disable_rerank_for_streaming: boolean;
  api_url: string | null;
  num_rerank: number;
  embedding_precision: EmbeddingPrecision;
  reduced_dimension: number | null;
}

export interface SavedSearchSettings
  extends RerankingDetails,
    AdvancedSearchConfiguration {
  provider_type: EmbeddingProvider | null;
  switchover_type?: SwitchoverType;
}
