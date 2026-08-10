import { NextRequest } from "next/server";

const USER_SERVICE_COLLECTION_PATHS = new Set([
  "coarse-roles",
  "organizations",
  "permissions",
  "roles",
  "users",
]);

export function isUserServiceCollectionPath(path: string[]): boolean {
  return path.length === 1 && USER_SERVICE_COLLECTION_PATHS.has(path[0] ?? "");
}

export function buildUserServicePath(path: string[], request: NextRequest) {
  let result = `/api/v1/${path.join("/")}`;
  if (
    (isUserServiceCollectionPath(path) ||
      request.nextUrl.pathname.endsWith("/")) &&
    !result.endsWith("/")
  ) {
    result += "/";
  }
  return result;
}
