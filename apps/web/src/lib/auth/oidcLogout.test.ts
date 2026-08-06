import { AuthType } from "@/lib/constants";
import { buildOidcLogoutUrl } from "./oidcLogout";

describe("buildOidcLogoutUrl", () => {
  it("builds a Keycloak logout URL for OIDC even after backend logout succeeds", () => {
    const url = buildOidcLogoutUrl({
      authType: AuthType.OIDC,
      issuer: "http://keycloak.local/realms/agenticai/",
      clientId: "agenticai-web",
      postLogoutRedirectUri: "http://localhost:8126/auth/ee/login",
      idTokenHint: "id-token",
    });

    expect(url?.toString()).toBe(
      "http://keycloak.local/realms/agenticai/protocol/openid-connect/logout" +
        "?client_id=agenticai-web" +
        "&post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A8126%2Fauth%2Fee%2Flogin" +
        "&id_token_hint=id-token"
    );
  });

  it("does not build a Keycloak logout URL for non-OIDC auth", () => {
    const url = buildOidcLogoutUrl({
      authType: AuthType.BASIC,
      issuer: "http://keycloak.local/realms/agenticai",
      clientId: "agenticai-web",
      postLogoutRedirectUri: "http://localhost:8126/auth/login",
    });

    expect(url).toBeNull();
  });
});
