import { getInternalUrl, getUserServiceUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { isUserServiceCollectionPath } from "@/lib/api/userServicePath";

const USER_PREFIXES = new Set([
  "users",
  "roles",
  "permissions",
  "user-service",
]);

export function getBackendUrl(path: string[]): URL {
  const firstSegment = path[0] ?? "";

  if (USER_PREFIXES.has(firstSegment)) {
    const base = getUserServiceUrl();
    const servicePath = firstSegment === "user-service" ? path.slice(1) : path;
    const pathSuffix = isUserServiceCollectionPath(servicePath) ? "/" : "";
    return buildServiceUrl(
      base,
      "user",
      `/api/${servicePath.join("/")}${pathSuffix}`
    );
  }

  const base = getInternalUrl();
  return buildServiceUrl(base, "agent", `/api/${path.join("/")}`);
}
