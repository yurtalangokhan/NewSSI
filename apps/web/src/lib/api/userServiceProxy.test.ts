import { getBackendUrl } from "@/lib/api/routeBackendUrl";

describe("user-service API proxy routing", () => {
  it("strips the frontend user-service alias before forwarding", () => {
    const url = getBackendUrl(["user-service", "users", "me", "permissions"]);

    expect(url.pathname).toBe("/api/users/me/permissions");
  });

  it("keeps direct user-service resource paths unchanged", () => {
    const url = getBackendUrl(["roles", "sync-keycloak"]);

    expect(url.pathname).toBe("/api/roles/sync-keycloak");
  });
});
