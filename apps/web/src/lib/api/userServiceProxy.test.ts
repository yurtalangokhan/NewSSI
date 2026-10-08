import { getBackendUrl } from "@/lib/api/routeBackendUrl";
import {
  buildUserServicePath,
  isUserServiceCollectionPath,
} from "@/lib/api/userServicePath";
import { NextRequest } from "next/server";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";

const mocked = { USER_SERVICE_URL: "http://user-service" };

jest.mock("@/lib/settings", () => ({
  appSettings: {
    get USER_SERVICE_URL() {
      return mocked.USER_SERVICE_URL;
    },
    AGENT_SERVICE_URL: "http://agent-service",
    RAG_SERVICE_URL: "http://rag-service",
    TOOLS_SERVICE_URL: "http://tools-service",
  },
}));

it("keeps catch-all target construction in domain catalogs", () => {
  expect(accessEndpoints).toHaveProperty("userServiceProxy");
  expect(agentsEndpoints).toHaveProperty("apiProxy");
  const userTarget = Reflect.get(accessEndpoints, "userServiceProxy");
  const agentTarget = Reflect.get(agentsEndpoints, "apiProxy");
  expect(userTarget(["users"], true).backend).toEqual({
    service: "user",
    path: "/api/v1/users/",
  });
  expect(userTarget(["users", "me"], false).backend).toEqual({
    service: "user",
    path: "/api/v1/users/me",
  });
  expect(userTarget(["users", "me/"], true).backend.path).toBe(
    "/api/v1/users/me/"
  );
  expect(agentTarget(["agent-definitions", "a b"]).backend).toEqual({
    service: "agent",
    path: "/api/v1/agent-definitions/a b",
  });
});

describe("user-service API proxy routing", () => {
  beforeEach(() => {
    mocked.USER_SERVICE_URL = "http://user-service";
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

  it("uses the service scope explicitly configured in the base URL", () => {
    mocked.USER_SERVICE_URL = "http://apisix:8000/user-service";

    const url = getBackendUrl(["user-service", "users", "me"]);

    expect(url.toString()).toBe(
      "http://apisix:8000/user-service/api/v1/users/me"
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

  it("keeps the organization collection on its canonical no-slash route", () => {
    const request = new NextRequest(
      "http://localhost/api/user-service/organizations"
    );

    expect(isUserServiceCollectionPath(["organizations"])).toBe(false);
    expect(buildUserServicePath(["organizations"], request)).toBe(
      "/api/v1/organizations"
    );
    expect(getBackendUrl(["user-service", "organizations"]).pathname).toBe(
      "/api/v1/organizations"
    );
  });

  it("forwards organization tree paths without treating them as collections", () => {
    const treeUrl = getBackendUrl(["user-service", "organizations", "tree"]);
    const request = new NextRequest(
      "http://localhost/api/user-service/organizations/tree"
    );
    const trailingSlashRequest = new NextRequest(
      "http://localhost/api/user-service/organizations/tree/"
    );

    expect(treeUrl.pathname).toBe("/api/v1/organizations/tree");
    expect(buildUserServicePath(["organizations", "tree"], request)).toBe(
      "/api/v1/organizations/tree"
    );
    expect(
      buildUserServicePath(["organizations", "tree"], trailingSlashRequest)
    ).toBe("/api/v1/organizations/tree/");
  });

  it("does not expose a user-organizations collection the backend does not define", () => {
    expect(isUserServiceCollectionPath(["user-organizations"])).toBe(false);
  });
});
