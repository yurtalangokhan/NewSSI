import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { getServerRequestHeaders } from "@/lib/api/server-context";

export async function fetchConnectorsSS(): Promise<Response> {
  return backendRequest({
    ...datasourcesEndpoints.listConnectors.backend,
    credentials: "include",
    cache: "no-store",
    headers: await getServerRequestHeaders(),
  });
}
