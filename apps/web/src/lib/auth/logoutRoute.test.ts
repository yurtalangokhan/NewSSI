import { NextRequest } from "next/server";
import { GET } from "@/app/auth/logout/route";
import { AuthType } from "@/lib/constants";
import {
  getAuthTypeMetadataSS,
  logoutSS,
} from "@/lib/api/domains/session/server";

jest.mock("@/lib/api/domains/session/server", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  logoutSS: jest.fn(),
}));

jest.mock("@/lib/env", () => {
  const actual = jest.requireActual("@/lib/env");
  return {
    env: {
      ...actual.env,
      KEYCLOAK_ISSUER_URL: "http://keycloak.local/realms/agenticai",
      KEYCLOAK_CLIENT_ID: "agenticai-web",
    },
  };
});

describe("logout route", () => {
  beforeEach(() => {
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
    jest.clearAllMocks();
  });

  it("ignores an external next parameter and falls back to the login route", async () => {
    const request = new NextRequest(
      "http://localhost:3000/auth/logout?next=https://evil.example/"
    );

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location.startsWith("https://evil.example")).toBe(false);
    expect(location).toContain(
      "post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fee%2Flogin"
    );
  });

  it("ignores a protocol-relative next parameter", async () => {
    const request = new NextRequest(
      "http://localhost:3000/auth/logout?next=//evil.example/"
    );

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location).not.toContain("evil.example");
  });

  it("accepts a well-formed internal next parameter", async () => {
    const request = new NextRequest(
      "http://localhost:3000/auth/logout?next=/app/chat"
    );

    const response = await GET(request);
    const location = response.headers.get("location") ?? "";

    expect(location).toContain(
      "post_logout_redirect_uri=" +
        encodeURIComponent("http://localhost:3000/app/chat")
    );
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
