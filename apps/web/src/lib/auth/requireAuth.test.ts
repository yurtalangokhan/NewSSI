import { requireAdminAuth, requireAuth } from "./requireAuth";
import {
  getAuthTypeMetadataSS,
  getCurrentUserAccessSS,
  getCurrentUserSS,
} from "@/lib/api/domains/session/server";
import type { AuthTypeMetadata } from "@/lib/api/domains/session/types";
import { AuthType } from "@/lib/constants";

jest.mock("@/lib/api/domains/session/server", () => ({
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
      permissions: ["agent:view"],
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
      permissions: [
        "chat:send",
        "agent:list",
        "datasource:read",
        "provider:read",
        "mcp_tool:read",
      ],
      isAdmin: false,
    });

    await expect(requireAdminAuth()).resolves.toMatchObject({
      user,
      redirect: "/error/403",
    });
  });

  it("denies a server-rendered admin page without its view grant", async () => {
    const user = {
      id: "user-1",
      role: "enterprise-admin",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserAccessSS).mockResolvedValue({
      permissions: ["agent:view"],
      isAdmin: true,
    });

    await expect(
      requireAdminAuth("/admin/bots/1/channels/new")
    ).resolves.toMatchObject({
      user,
      redirect: "/error/403",
    });
  });

  it("admits a server-rendered admin page with its view grant", async () => {
    const user = {
      id: "user-1",
      role: "enterprise-admin",
      is_superuser: false,
      is_verified: true,
    };
    jest.mocked(getCurrentUserSS).mockResolvedValue(user as never);
    jest.mocked(getCurrentUserAccessSS).mockResolvedValue({
      permissions: ["slack_bot:view"],
      isAdmin: true,
    });

    await expect(
      requireAdminAuth("/admin/bots/1/channels/new")
    ).resolves.toEqual({
      user,
      authTypeMetadata,
    });
  });
});
