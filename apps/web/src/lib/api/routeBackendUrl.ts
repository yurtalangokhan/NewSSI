import { INTERNAL_URL, USER_SERVICE_URL } from "@/lib/constants";

const USER_PREFIXES = new Set([
  "users",
  "roles",
  "permissions",
  "user-service",
]);

export function getBackendUrl(path: string[]): URL {
  const firstSegment = path[0] ?? "";

  if (USER_PREFIXES.has(firstSegment)) {
    const base = USER_SERVICE_URL || "http://localhost:8090";
    const servicePath =
      firstSegment === "user-service" ? path.slice(1) : path;
    return new URL(`${base}/api/${servicePath.join("/")}`);
  }

  const base = INTERNAL_URL || "http://localhost:8123";
  return new URL(`${base}/api/${path.join("/")}`);
}
