import {
  ADMIN_PATHS,
  ADMIN_ROUTE_CONFIG,
  canAccessAdminPanel,
  getFirstAccessibleAdminPath,
  getAdminRouteConfigForPathname,
  sidebarItem,
} from "./admin-routes";
import { hasAllPermissions } from "@/lib/auth/permissions";
import i18n from "@/i18n/config";

describe("admin route permissions", () => {
  it("grants admin-panel entry when an enabled route is accessible", () => {
    expect(ADMIN_ROUTE_CONFIG[ADMIN_PATHS.AGENTS]?.enabled).not.toBe(false);
    expect(
      hasAllPermissions(
        ["agent:list"],
        ADMIN_ROUTE_CONFIG[ADMIN_PATHS.AGENTS]?.requiredPermissions
      )
    ).toBe(true);
    expect(canAccessAdminPanel(["agent:list"])).toBe(true);
    expect(canAccessAdminPanel(["user:list"])).toBe(true);
  });

  it("denies admin-panel entry without permissions for an enabled route", () => {
    expect(canAccessAdminPanel(["chat:send"])).toBe(false);
    expect(canAccessAdminPanel([])).toBe(false);
  });

  it("supports wildcard admin-panel access", () => {
    expect(canAccessAdminPanel(["*"])).toBe(true);
  });

  it("selects an admin landing page the user can access", () => {
    expect(getFirstAccessibleAdminPath(["user:list"])).toBe(ADMIN_PATHS.GROUPS);
  });

  it("requires role and permission list access for the roles page", () => {
    expect(ADMIN_ROUTE_CONFIG[ADMIN_PATHS.ROLES]?.requiredPermissions).toEqual([
      "role:list",
      "role:read",
      "permission:list",
    ]);
  });

  it("includes permission requirements in sidebar items", () => {
    expect(sidebarItem(ADMIN_PATHS.USERS).requiredPermissions).toEqual([
      "user:list",
    ]);
  });

  it("registers mail configs under configuration permissions", () => {
    expect(
      ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MAIL_CONFIGS]?.requiredPermissions
    ).toEqual(["settings:read"]);
  });

  it("supports filtering sidebar items by all required permissions", () => {
    const items = [
      sidebarItem(ADMIN_PATHS.USERS),
      sidebarItem(ADMIN_PATHS.ROLES),
    ];

    const visible = items.filter((item) =>
      hasAllPermissions(
        ["role:list", "role:read", "permission:list"],
        item.requiredPermissions
      )
    );

    expect(visible.map((item) => item.link)).toEqual([ADMIN_PATHS.ROLES]);
  });

  it("resolves nested admin pages to the nearest route permission config", () => {
    expect(
      getAdminRouteConfigForPathname("/admin/users/add")?.requiredPermissions
    ).toEqual(["user:list"]);
    expect(
      getAdminRouteConfigForPathname("/admin/documents/sets/new")
        ?.requiredPermissions
    ).toEqual(["collection:list"]);
  });

  it("localizes the organizations sidebar label", async () => {
    await i18n.changeLanguage("en");
    expect(sidebarItem(ADMIN_PATHS.ORGANIZATIONS, i18n.t).name).toBe(
      "Organization"
    );

    await i18n.changeLanguage("tr");
    expect(sidebarItem(ADMIN_PATHS.ORGANIZATIONS, i18n.t).name).toBe(
      "Organizasyon"
    );

    await i18n.changeLanguage("en");
  });
});
