import { resolveBackendUrl } from "@/lib/api/http/server";
import { isUserServiceCollectionPath } from "@/lib/api/userServicePath";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";

const USER_PREFIXES = new Set([
  "users",
  "roles",
  "permissions",
  "user-service",
]);

export function getBackendUrl(path: string[]): URL {
  const firstSegment = path[0] ?? "";

  if (USER_PREFIXES.has(firstSegment)) {
    const servicePath = firstSegment === "user-service" ? path.slice(1) : path;
    return resolveBackendUrl(
      accessEndpoints.userServiceProxy(
        servicePath,
        isUserServiceCollectionPath(servicePath)
      ).backend
    );
  }

  return resolveBackendUrl(agentsEndpoints.apiProxy(path).backend);
}
