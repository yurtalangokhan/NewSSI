import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import Page from "./page";
import {
  getAuthTypeMetadataSS,
  getAuthUrlSS,
  getCurrentUserSS,
} from "@/lib/api/domains/session/server";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/api/domains/session/server", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  getAuthUrlSS: jest.fn(),
  getCurrentUserSS: jest.fn(),
}));
jest.mock("@/components/auth/AuthFlowContainer", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
jest.mock("./LoginAdminNote", () => ({ LoginAdminNote: () => null }));
jest.mock("./LoginPage", () => ({
  __esModule: true,
  default: ({ spAuthUrl }: { spAuthUrl?: string }) => (
    <a href={spAuthUrl}>SP Keycloak SSO</a>
  ),
}));

it("passes a prompt-login SP URL to the standard Keycloak page, preserving next", async () => {
  jest.mocked(getCurrentUserSS).mockResolvedValue(null);
  jest.mocked(getAuthTypeMetadataSS).mockResolvedValue({
    authType: AuthType.OIDC,
    keycloakEnabled: true,
    externalKeycloak: false,
    autoRedirect: false,
    requiresVerification: false,
    anonymousUserEnabled: false,
    hasUsers: true,
    oauthEnabled: true,
  });
  const url = "/api/auth/oidc/authorize?next=%2Fapp&prompt=login&redirect=true";
  jest.mocked(getAuthUrlSS).mockResolvedValue(url);
  render(await Page({ searchParams: Promise.resolve({ next: "/app" }) }));
  expect(getAuthUrlSS).toHaveBeenCalledWith(AuthType.OIDC, "/app", null, {
    prompt: "login",
  });
  expect(screen.getByRole("link", { name: "SP Keycloak SSO" })).toHaveAttribute(
    "href",
    url
  );
});
