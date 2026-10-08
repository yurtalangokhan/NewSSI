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

  it("shows the SP SSO link on the standard Keycloak login page", () => {
    render(
      <LoginPage
        authUrl="/api/auth/oidc/authorize?redirect=true"
        spAuthUrl="/api/auth/oidc/authorize?prompt=login&redirect=true"
        authTypeMetadata={{
          ...authTypeMetadata,
          externalKeycloak: false,
          keycloakEnabled: true,
        }}
        nextUrl={null}
      />
    );
    expect(
      screen.getByRole("link", { name: /SP Keycloak SSO/i })
    ).toHaveAttribute(
      "href",
      "/api/auth/oidc/authorize?prompt=login&redirect=true"
    );
    expect(
      screen.queryByRole("button", { name: /Continue with OIDC/i })
    ).not.toBeInTheDocument();
  });

  it("keeps generic OIDC login when no SP URL is supplied", () => {
    render(
      <LoginPage
        authUrl="/api/auth/oidc/authorize?redirect=true"
        authTypeMetadata={{
          ...authTypeMetadata,
          externalKeycloak: false,
          keycloakEnabled: false,
        }}
        nextUrl={null}
      />
    );
    expect(
      screen.getByRole("button", { name: /Continue with OIDC/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /SP Keycloak SSO/i })
    ).not.toBeInTheDocument();
  });

  it("shows the oidcError the callback route already parsed", () => {
    // The OIDC callback route turns the gateway's error envelope into a user
    // message before redirecting here; the page shows it as given.
    render(
      <LoginPage
        authUrl="/api/auth/oidc/authorize?kc_idp_hint=external-keycloak"
        spAuthUrl="/api/auth/oidc/authorize?prompt=login"
        authTypeMetadata={authTypeMetadata}
        nextUrl={null}
        externalKeycloakLogin
        oidcError="Identity provider unavailable"
      />
    );

    expect(
      screen.getByText("Identity provider unavailable")
    ).toBeInTheDocument();
  });
});
