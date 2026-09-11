import { authenticatedFetch } from "@/lib/fetcher";
import { APIKeyArgs, APIKey } from "./types";

export const createApiKey = async (apiKeyArgs: APIKeyArgs) => {
  return authenticatedFetch("/api/admin/api-key", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(apiKeyArgs),
  });
};

export const regenerateApiKey = async (apiKey: APIKey) => {
  return authenticatedFetch(
    `/api/admin/api-key/${apiKey.api_key_id}/regenerate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
};

export const updateApiKey = async (
  apiKeyId: number,
  apiKeyArgs: APIKeyArgs
) => {
  return authenticatedFetch(`/api/admin/api-key/${apiKeyId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(apiKeyArgs),
  });
};

export const deleteApiKey = async (apiKeyId: number) => {
  return authenticatedFetch(`/api/admin/api-key/${apiKeyId}`, {
    method: "DELETE",
  });
};
