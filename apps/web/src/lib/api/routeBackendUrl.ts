import { getInternalUrl, getUserServiceUrl } from "@/lib/env.server";

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
    const servicePath =
      firstSegment === "user-service" ? path.slice(1) : path;
    return new URL(`${base}/api/${servicePath.join("/")}`);
  }

  const base = getInternalUrl();
  return new URL(`${base}/api/${path.join("/")}`);
}
