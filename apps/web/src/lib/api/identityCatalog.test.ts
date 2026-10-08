import { isIdentityCatalogKey } from "@/lib/api/identityCatalog";

describe("identity catalog refresh", () => {
  it.each([
    "/api/user-service/roles/",
    "/api/user-service/coarse-roles/",
    "/api/user-service/permissions/",
    "/api/user-service/roles/custom%20role/permissions",
    "/api/user-service/roles/custom/role-ids",
    "/api/user-service/coarse-roles/workspace/permissions",
  ])("refreshes the catalog and open editors: %s", (key) => {
    expect(isIdentityCatalogKey(key)).toBe(true);
  });

  it.each([
    null,
    ["roles"],
    "/api/user-service/users/",
    "/api/agent-service/roles/",
    "/api/user-service/roles/sync-keycloak",
    "/api/user-service/roles-other/",
  ])("does not refresh unrelated data or write operations: %s", (key) => {
    expect(isIdentityCatalogKey(key)).toBe(false);
  });
});
