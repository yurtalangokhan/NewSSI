import { requireAdminAuth, requireAuth } from "./requireAuth";
import {
  type AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserAccessSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/userSS", () => ({
  getAuthTypeMetadataSS: jest.fn(),
  getCurrentUserAccessSS: jest.fn(),
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
    jest
      .mocked(getCurrentUserAccessSS)
      .mockResolvedValue({ permissions: [], isAdmin: false });
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

  it("admits users who can access at least one enabled admin route", async () => {
    const user = {
      id: "user-1",
      role: "enduser",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserAccessSS).mockResolvedValue({
      permissions: ["agent:list"],
      isAdmin: false,
    });

    const result = await requireAdminAuth();

    expect(result).toMatchObject({ user });
    expect(result).not.toHaveProperty("redirect");
  });

  it("admits authenticated users with wildcard access", async () => {
    const user = {
      id: "user-1",
      role: "system-admin",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserAccessSS).mockResolvedValue({
      permissions: ["*"],
      isAdmin: true,
    });

    const result = await requireAdminAuth();

    expect(result).toMatchObject({ user });
    expect(result).not.toHaveProperty("redirect");
  });

  it("redirects authenticated users without admin access", async () => {
    const user = {
      id: "user-1",
      role: "enduser",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserAccessSS).mockResolvedValue({
      permissions: ["chat:send"],
      isAdmin: false,
    });

    await expect(requireAdminAuth()).resolves.toMatchObject({
      user,
      redirect: "/error/403",
    });
  });
});
