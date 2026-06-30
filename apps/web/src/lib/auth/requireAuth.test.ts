import { requireAuth } from "./requireAuth";
import {
  type AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
  hasRefreshTokenCookieSS,
} from "@/lib/userSS";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/userSS", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  getCurrentUserSS: jest.fn(),
  hasRefreshTokenCookieSS: jest.fn(),
}));

const authTypeMetadata: AuthTypeMetadata = {
  authType: AuthType.BASIC,
  autoRedirect: false,
  anonymousUserEnabled: false,
  hasUsers: true,
  oauthEnabled: false,
  externalKeycloak: false,
  external_keycloak: false,
  requiresVerification: false,
};

describe("requireAuth", () => {
  beforeEach(() => {
    jest.mocked(getAuthTypeMetadataSS).mockResolvedValue(authTypeMetadata);
    jest.mocked(getCurrentUserSS).mockResolvedValue(null);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("redirects to login when a refresh token cookie exists but the user cannot be resolved", async () => {
    jest.mocked(hasRefreshTokenCookieSS).mockResolvedValue(true);

    await expect(requireAuth()).resolves.toMatchObject({
      user: null,
      redirect: "/auth/login",
    });
  });

  it("redirects to the 401 error page when the request has no refresh token cookie", async () => {
    jest.mocked(hasRefreshTokenCookieSS).mockResolvedValue(false);

    await expect(requireAuth()).resolves.toMatchObject({
      user: null,
      redirect: "/error/401",
    });
  });
});
