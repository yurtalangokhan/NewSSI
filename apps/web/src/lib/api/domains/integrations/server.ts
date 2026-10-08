import { integrationsEndpoints } from "@/lib/api/domains/integrations/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { getServerRequestHeaders } from "@/lib/api/server-context";

export async function fetchSlackChannelsSS(): Promise<Response> {
  return backendRequest({
    ...integrationsEndpoints.listSlackChannels.backend,
    credentials: "include",
    cache: "no-store",
    headers: await getServerRequestHeaders(),
  });
}
