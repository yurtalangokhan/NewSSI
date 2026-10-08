import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";

import useSWR, { type KeyedMutator } from "swr";
import { User } from "@/lib/types";
import {
  fetchCurrentUserWithError,
  fetchPersonalAccessTokens,
} from "@/lib/api/domains/session/api";

import type { PersonalAccessToken } from "@/lib/api/domains/session/types";
import { fetchAuthTypeForSWR } from "@/lib/api/domains/session/api";

import { AuthType } from "@/lib/constants";
import { appSettings } from "@/lib/settings";

export function useAuthType(): AuthType | null {
  const { data, error } = useSWR<{ auth_type: AuthType }>(
    sessionEndpoints.authType.browserPath,
    () => fetchAuthTypeForSWR<{ auth_type: AuthType }>()
  );
  if (appSettings.NEXT_PUBLIC_CLOUD_ENABLED) return AuthType.CLOUD;
  if (error || !data) return null;
  return data.auth_type;
}

export type { User };

/**
 * SWR hook for current user.
 * Uses fetchCurrentUserWithError which throws FetchError on non-OK.
 * Conservative revalidation settings to avoid hammering the backend.
 */
export function useCurrentUser(): {
  user: User | undefined;
  mutateUser: KeyedMutator<User>;
  userError: (Error & { status?: number }) | undefined;
} {
  const { data, mutate, error } = useSWR<User>(
    sessionEndpoints.getCurrentUser.browserPath,
    () => fetchCurrentUserWithError(),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 30_000,
    }
  );

  return { user: data, mutateUser: mutate, userError: error };
}

export function usePersonalAccessTokens(enabled: boolean) {
  return useSWR<PersonalAccessToken[]>(
    enabled ? sessionEndpoints.createPersonalAccessToken.browserPath : null,
    fetchPersonalAccessTokens,
    {
      revalidateOnFocus: true,
      dedupingInterval: 2000,
      fallbackData: [],
    }
  );
}
