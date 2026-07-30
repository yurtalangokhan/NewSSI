import { buildPublicUserAuthUrl } from "@/lib/api/publicUserAuthUrl";

describe("buildPublicUserAuthUrl", () => {
  const originalUserServiceUrl = process.env.USER_SERVICE_URL;

  afterEach(() => {
    if (originalUserServiceUrl === undefined) {
      delete process.env.USER_SERVICE_URL;
    } else {
      process.env.USER_SERVICE_URL = originalUserServiceUrl;
    }
  });

  it("uses the canonical service-scoped auth path for Kong bases", () => {
    process.env.USER_SERVICE_URL = "http://localhost:8000";

    expect(buildPublicUserAuthUrl("/oidc/callback").toString()).toBe(
      "http://localhost:8000/user-service/api/v1/auth/oidc/callback"
    );
  });

  it("keeps existing service-scoped base paths for public browser auth", () => {
    process.env.USER_SERVICE_URL = "http://kong:8000/user-service";

    expect(buildPublicUserAuthUrl("/oidc/authorize").toString()).toBe(
      "http://kong:8000/user-service/api/v1/auth/oidc/authorize"
    );
  });
});
