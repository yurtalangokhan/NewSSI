import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";

import { runConnector } from "@/lib/api/domains/datasources/api";

import { mutate } from "swr";

export async function triggerIndexing(
  fromBeginning: boolean,
  connectorId: number,
  credentialId: number,
  ccPairId: number
): Promise<{ success: boolean; message: string }> {
  const errorMsg = await runConnector(
    connectorId,
    [credentialId],
    fromBeginning
  );

  mutate(datasourcesEndpoints.ccPairInfoWithQuery(ccPairId).browserPath);

  if (errorMsg) {
    return {
      success: false,
      message: errorMsg,
    };
  } else {
    return {
      success: true,
      message: "Triggered connector run",
    };
  }
}

export function getTooltipMessage(
  isInvalid: boolean,
  isDeleting: boolean,
  isIndexing: boolean,
  isDisabled: boolean
): string | undefined {
  if (isInvalid) {
    return "Connector is in an invalid state. Please update the credentials or configuration before re-indexing.";
  }
  if (isDeleting) {
    return "Cannot index while connector is deleting";
  }
  if (isIndexing) {
    return "Indexing is already in progress";
  }
  if (isDisabled) {
    return "Connector must be re-enabled before indexing";
  }
  return undefined;
}
