import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";

import useSWR, { mutate } from "swr";
import {
  fetchConnectorsByCredential,
  fetchGoogleAppCredential,
  fetchGoogleServiceAccountKey,
  fetchSimilarCredentials,
} from "@/lib/api/domains/datasources/api";
import { FetchError } from "@/lib/api/http/errors";
import { Credential } from "@/lib/connectors/credentials";
import { ConnectorSnapshot } from "@/lib/connectors/connectors";
import { ValidSources } from "@/lib/types";

// Constants for service names to avoid typos
export const GOOGLE_SERVICES = {
  GMAIL: "gmail",
  GOOGLE_DRIVE: "google-drive",
} as const;

export const useGoogleAppCredential = (service: "gmail" | "google_drive") => {
  const endpoint = datasourcesEndpoints.googleAppCredential(
    service === "gmail" ? GOOGLE_SERVICES.GMAIL : GOOGLE_SERVICES.GOOGLE_DRIVE
  ).browserPath;

  return useSWR<{ client_id: string }, FetchError>(endpoint, () =>
    fetchGoogleAppCredential<{ client_id: string }>(
      service === "gmail" ? GOOGLE_SERVICES.GMAIL : GOOGLE_SERVICES.GOOGLE_DRIVE
    )
  );
};

export const useGoogleServiceAccountKey = (
  service: "gmail" | "google_drive"
) => {
  const endpoint = datasourcesEndpoints.googleServiceAccountKey(
    service === "gmail" ? GOOGLE_SERVICES.GMAIL : GOOGLE_SERVICES.GOOGLE_DRIVE
  ).browserPath;

  return useSWR<{ service_account_email: string }, FetchError>(endpoint, () =>
    fetchGoogleServiceAccountKey<{ service_account_email: string }>(
      service === "gmail" ? GOOGLE_SERVICES.GMAIL : GOOGLE_SERVICES.GOOGLE_DRIVE
    )
  );
};

export const useGoogleCredentials = (
  source: ValidSources.Gmail | ValidSources.GoogleDrive
) => {
  return useSWR<Credential<any>[]>(
    datasourcesEndpoints.similarCredentialInfo(source).browserPath,
    () => fetchSimilarCredentials<Credential<any>[]>(source),
    { refreshInterval: 5000 }
  );
};

export const useConnectorsByCredentialId = (credential_id: number | null) => {
  let url: string | null = null;
  if (credential_id !== null) {
    url = datasourcesEndpoints.fetchConnectors(credential_id).browserPath;
  }
  const swrResponse = useSWR<ConnectorSnapshot[]>(url, () =>
    fetchConnectorsByCredential<ConnectorSnapshot[]>(credential_id!)
  );

  return {
    ...swrResponse,
    refreshConnectorsByCredentialId: () => mutate(url),
  };
};

export const checkCredentialsFetched = (
  appCredentialData: any,
  appCredentialError: FetchError | undefined,
  serviceAccountKeyData: any,
  serviceAccountKeyError: FetchError | undefined
) => {
  const appCredentialSuccessfullyFetched =
    appCredentialData ||
    (appCredentialError && appCredentialError.status === 404);

  const serviceAccountKeySuccessfullyFetched =
    serviceAccountKeyData ||
    (serviceAccountKeyError && serviceAccountKeyError.status === 404);

  return {
    appCredentialSuccessfullyFetched,
    serviceAccountKeySuccessfullyFetched,
  };
};

export const filterUploadedCredentials = <
  T extends { authentication_method?: string },
>(
  credentials: Credential<T>[] | undefined
): { credential_id: number | null; uploadedCredentials: Credential<T>[] } => {
  let credential_id = null;
  let uploadedCredentials: Credential<T>[] = [];

  if (credentials) {
    uploadedCredentials = credentials.filter(
      (credential) =>
        credential.credential_json.authentication_method !== "oauth_interactive"
    );

    if (uploadedCredentials.length > 0 && uploadedCredentials[0]) {
      credential_id = uploadedCredentials[0].id;
    }
  }

  return { credential_id, uploadedCredentials };
};

export const checkConnectorsExist = (
  connectors: ConnectorSnapshot[] | undefined
): boolean => {
  return !!connectors && connectors.length > 0;
};

export const refreshAllGoogleData = (
  source: ValidSources.Gmail | ValidSources.GoogleDrive
) => {
  mutate(datasourcesEndpoints.similarCredentialInfo(source).browserPath);

  const service =
    source === ValidSources.Gmail
      ? GOOGLE_SERVICES.GMAIL
      : GOOGLE_SERVICES.GOOGLE_DRIVE;
  mutate(datasourcesEndpoints.googleAppCredential(service).browserPath);
  mutate(datasourcesEndpoints.googleServiceAccountKey(service).browserPath);
};
