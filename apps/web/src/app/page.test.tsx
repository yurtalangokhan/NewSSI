import Page from "@/app/page";
import { AuthType } from "@/lib/constants";
import { getAuthTypeMetadataSS, getCurrentUserSS } from "@/lib/userSS";
import { redirect } from "next/navigation";

jest.mock("@/lib/userSS", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  getCurrentUserSS: jest.fn(),
}));

jest.mock("next/navigation", () => ({
  redirect: jest.fn(),
}));

describe("root page auth routing", () => {
  const authTypeMetadata = {
    authType: AuthType.OIDC,
    autoRedirect: false,
    requiresVerification: false,
    anonymousUserEnabled: false,
    hasUsers: true,
    oauthEnabled: true,
    externalKeycloak: true,
    external_keycloak: true,
    externalKeycloakAlias: "external-keycloak",
  };

  beforeEach(() => {
    jest.mocked(getAuthTypeMetadataSS).mockResolvedValue(authTypeMetadata);
    jest.mocked(getCurrentUserSS).mockResolvedValue(null);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("redirects authenticated users to the app instead of login", async () => {
    jest.mocked(getCurrentUserSS).mockResolvedValue({
      id: "user-1",
      email: "user@example.com",
      username: "user@example.com",
      role: "enduser",
      is_active: true,
      is_verified: true,
      is_anonymous_user: false,
    } as never);

    await Page();

    expect(redirect).toHaveBeenCalledWith("/app");
  });

  it("redirects unauthenticated users to the selected login page", async () => {
    await Page();

    expect(redirect).toHaveBeenCalledWith("/auth/ee/login");
  });
});
