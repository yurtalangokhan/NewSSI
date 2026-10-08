import { parseResponseModel } from "@/lib/api/responseModel";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { getServerRequestHeaders } from "@/lib/api/server-context";
import { getErrorMsg } from "@/lib/fetchUtils";

import type { MinimalPersonaSnapshot } from "./types";

export type FetchAgentsResponse = [MinimalPersonaSnapshot[], string | null];

export async function fetchAgentsSS(): Promise<FetchAgentsResponse> {
  const response = await backendRequest({
    ...agentsEndpoints.listPersonas.backend,
    credentials: "include",
    cache: "no-store",
    headers: await getServerRequestHeaders(),
  });
  if (response.ok) {
    return [await parseResponseModel<MinimalPersonaSnapshot[]>(response), null];
  }
  return [[], (await getErrorMsg(response)) || "Unknown Error"];
}
