/**
 * Model capability classification utilities based strictly on capability flags and metadata.
 * No hardcoded model names.
 */

export interface ModelCapabilitySource {
  supports_embedding?: boolean;
  model_type?: string;
  capabilities?: string[] | Record<string, boolean>;
  metadata?: {
    supports_embedding?: boolean;
    model_type?: string;
    capabilities?: string[] | Record<string, boolean>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/**
 * Anything carrying capability hints: the metadata bag above, or a concrete
 * model object (e.g. `ModelConfiguration`) that happens to expose the same
 * optional flags. Kept index-signature-free so plain interfaces without one
 * are still assignable.
 */
export type ModelCapabilityLike = {
  supports_embedding?: boolean;
  model_type?: string;
  capabilities?: string[] | Record<string, boolean>;
  metadata?: Record<string, unknown>;
};

/**
 * Returns true if the given model or metadata declares embedding capabilities via flags.
 */
export function isEmbeddingModel(
  modelOrMetadata?: ModelCapabilitySource | ModelCapabilityLike | null
): boolean {
  if (!modelOrMetadata) return false;

  // 1. Direct supports_embedding boolean flag
  if (modelOrMetadata.supports_embedding === true) {
    return true;
  }
  if (modelOrMetadata.metadata?.supports_embedding === true) {
    return true;
  }

  // 2. model_type field (e.g. "embedding" or "embeddings")
  const mType =
    modelOrMetadata.model_type ?? modelOrMetadata.metadata?.model_type;
  if (
    typeof mType === "string" &&
    (mType.trim().toLowerCase() === "embedding" ||
      mType.trim().toLowerCase() === "embeddings")
  ) {
    return true;
  }

  // 3. capabilities list or record
  const caps =
    modelOrMetadata.capabilities ?? modelOrMetadata.metadata?.capabilities;
  if (Array.isArray(caps)) {
    if (caps.some((c) => String(c).trim().toLowerCase() === "embedding")) {
      return true;
    }
  } else if (caps && typeof caps === "object") {
    if (
      Boolean(
        (caps as Record<string, boolean>).embedding ||
          (caps as Record<string, boolean>).embeddings
      )
    ) {
      return true;
    }
  }

  return false;
}

/**
 * Returns true if the given model is suitable for conversational / chat / text generation.
 */
export function isChatModel(
  modelOrMetadata?: ModelCapabilitySource | ModelCapabilityLike | null
): boolean {
  return !isEmbeddingModel(modelOrMetadata);
}
