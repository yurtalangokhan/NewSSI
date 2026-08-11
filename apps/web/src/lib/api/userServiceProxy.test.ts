import { getBackendUrl } from "@/lib/api/routeBackendUrl";
import {
  buildUserServicePath,
  isUserServiceCollectionPath,
} from "@/lib/api/userServicePath";
import { NextRequest } from "next/server";

describe("user-service API proxy routing", () => {
  beforeEach(() => {
    process.env.USER_SERVICE_URL = "http://user-service";
  });

  afterEach(() => {
    delete process.env.USER_SERVICE_URL;
  });

  it("strips the frontend user-service alias before forwarding", () => {
    const url = getBackendUrl(["user-service", "users", "me", "permissions"]);

    expect(url.pathname).toBe("/api/v1/users/me/permissions");
  });

  it("keeps direct user-service resource paths unchanged", () => {
    const url = getBackendUrl(["roles", "sync-keycloak"]);

    expect(url.pathname).toBe("/api/v1/roles/sync-keycloak");
  });

  it("adds trailing slashes for direct user-service collection paths", () => {
    const rolesUrl = getBackendUrl(["roles"]);
    const usersUrl = getBackendUrl(["user-service", "users"]);

    expect(rolesUrl.pathname).toBe("/api/v1/roles/");
    expect(usersUrl.pathname).toBe("/api/v1/users/");
  });

  it("adds the user-service scope for Kong bases", () => {
    process.env.USER_SERVICE_URL = "http://kong:8000";

    const url = getBackendUrl(["user-service", "users", "me"]);

    expect(url.toString()).toBe(
      "http://kong:8000/user-service/api/v1/users/me"
    );
  });

  it("adds backend trailing slashes for FastAPI collection routes only", () => {
    const request = new NextRequest("http://localhost/api/user-service/roles");

    expect(buildUserServicePath(["roles"], request)).toBe("/api/v1/roles/");
    expect(buildUserServicePath(["users"], request)).toBe("/api/v1/users/");
    expect(buildUserServicePath(["roles", "sync-keycloak"], request)).toBe(
      "/api/v1/roles/sync-keycloak"
    );
    expect(buildUserServicePath(["users", "me"], request)).toBe(
      "/api/v1/users/me"
    );
  });

  it("forwards organization layout paths without treating them as collections", () => {
    const layoutUrl = getBackendUrl([
      "user-service",
      "organizations",
      "layout",
    ]);
    const request = new NextRequest(
      "http://localhost/api/user-service/organizations/layout"
    );
    const trailingSlashRequest = new NextRequest(
      "http://localhost/api/user-service/organizations/layout/"
    );

    expect(layoutUrl.pathname).toBe("/api/v1/organizations/layout");
    expect(buildUserServicePath(["organizations", "layout"], request)).toBe(
      "/api/v1/organizations/layout"
    );
    expect(
      buildUserServicePath(["organizations", "layout"], trailingSlashRequest)
    ).toBe("/api/v1/organizations/layout/");
  });

  it("does not expose a user-organizations collection the backend does not define", () => {
    expect(isUserServiceCollectionPath(["user-organizations"])).toBe(false);
  });
});
