import { requireAuth } from "./requireAuth";
import {
  type AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/userSS", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  getCurrentUserSS: jest.fn(),
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

  it("redirects to login when the user cannot be resolved", async () => {
    await expect(requireAuth()).resolves.toMatchObject({
      user: null,
      redirect: "/auth/login",
    });
  });
});
