import { NextRequest } from "next/server";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

const USER_SERVICE_COLLECTION_PATHS = new Set([
  "coarse-roles",
  "permissions",
  "roles",
  "users",
]);

export function isUserServiceCollectionPath(path: string[]): boolean {
  return path.length === 1 && USER_SERVICE_COLLECTION_PATHS.has(path[0] ?? "");
}

export function buildUserServicePath(path: string[], request: NextRequest) {
  return accessEndpoints.userServiceProxy(
    path,
    isUserServiceCollectionPath(path) || request.nextUrl.pathname.endsWith("/")
  ).backend.path;
}
