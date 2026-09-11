import { authenticatedFetch } from "@/lib/fetcher";
import { UserPersonalization } from "@/lib/types";

export async function setUserDefaultModel(
  model: string | null
): Promise<Response> {
  const response = await authenticatedFetch(`/api/user/default-model`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ default_model: model }),
  });

  return response;
}

/**
 * Update the current user's personalization settings.
 */
export async function updateUserPersonalization(
  personalization: Partial<UserPersonalization>
): Promise<Response> {
  return authenticatedFetch(`/api/user/personalization`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(personalization),
  });
}
