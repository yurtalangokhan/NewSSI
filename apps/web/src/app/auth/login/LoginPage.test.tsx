import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import LoginPage from "./LoginPage";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/extension/utils", () => ({
  useSendAuthRequiredMessage: jest.fn(),
}));

describe("LoginPage external Keycloak mode", () => {
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

  it("hides the IdP SSO button and keeps the SP SSO button", () => {
    render(
      <LoginPage
        authUrl="/api/auth/oidc/authorize?kc_idp_hint=external-keycloak"
        spAuthUrl="/api/auth/oidc/authorize?prompt=login"
        authTypeMetadata={authTypeMetadata}
        nextUrl={null}
        externalKeycloakLogin
      />
    );

    expect(
      screen.queryByRole("link", { name: /External SSO/i })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /SP Keycloak SSO/i })
    ).toHaveAttribute("href", "/api/auth/oidc/authorize?prompt=login");
  });
});
