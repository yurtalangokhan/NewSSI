import { NextRequest } from "next/server";
import { GET } from "@/app/auth/logout/route";
import { AuthType } from "@/lib/constants";
import { getAuthTypeMetadataSS, logoutSS } from "@/lib/userSS";

jest.mock("@/lib/userSS", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  logoutSS: jest.fn(),
}));

describe("logout route", () => {
  const originalKeycloakIssuerUrl = process.env.KEYCLOAK_ISSUER_URL;
  const originalKeycloakClientId = process.env.KEYCLOAK_CLIENT_ID;

  beforeEach(() => {
    process.env.KEYCLOAK_ISSUER_URL = "http://keycloak.local/realms/agenticai";
    process.env.KEYCLOAK_CLIENT_ID = "agenticai-web";

    jest.mocked(getAuthTypeMetadataSS).mockResolvedValue({
      authType: AuthType.OIDC,
      autoRedirect: false,
      requiresVerification: false,
      anonymousUserEnabled: false,
      hasUsers: true,
      oauthEnabled: false,
      externalKeycloak: true,
    });
    jest
      .mocked(logoutSS)
      .mockResolvedValue(new Response(null, { status: 200 }));
  });

  afterEach(() => {
    if (originalKeycloakIssuerUrl === undefined) {
      delete process.env.KEYCLOAK_ISSUER_URL;
    } else {
      process.env.KEYCLOAK_ISSUER_URL = originalKeycloakIssuerUrl;
    }

    if (originalKeycloakClientId === undefined) {
      delete process.env.KEYCLOAK_CLIENT_ID;
    } else {
      process.env.KEYCLOAK_CLIENT_ID = originalKeycloakClientId;
    }

    jest.clearAllMocks();
  });

  it("redirects OIDC logout back to the login route without a logged_out query parameter", async () => {
    const request = new NextRequest("http://localhost:3000/auth/logout");

    const response = await GET(request);
    const location = response.headers.get("location");

    expect(location).toBe(
      "http://keycloak.local/realms/agenticai/protocol/openid-connect/logout" +
        "?client_id=agenticai-web" +
        "&post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fee%2Flogin"
    );
    expect(logoutSS).toHaveBeenCalledWith(
      AuthType.OIDC,
      request.headers,
      "http://localhost:3000/auth/ee/login"
    );
  });
});
