import { requireAdminAuth, requireAuth } from "./requireAuth";
import {
  type AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserPermissionsSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/userSS", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  getCurrentUserPermissionsSS: jest.fn(),
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
    jest.mocked(getCurrentUserPermissionsSS).mockResolvedValue([]);
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

  it("does not reject authenticated users by hardcoded admin role when permissions grant admin access", async () => {
    const user = {
      id: "user-1",
      role: "enduser",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserPermissionsSS).mockResolvedValue(["role:list"]);

    const result = await requireAdminAuth();

    expect(result).toMatchObject({ user });
    expect(result).not.toHaveProperty("redirect");
  });

  it("redirects authenticated users without admin permissions", async () => {
    const user = {
      id: "user-1",
      role: "system-admin",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserPermissionsSS).mockResolvedValue(["chat:send"]);

    await expect(requireAdminAuth()).resolves.toMatchObject({
      user,
      redirect: "/error/403",
    });
  });
});
