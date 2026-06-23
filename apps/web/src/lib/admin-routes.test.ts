import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG, sidebarItem } from "./admin-routes";
import { hasAllPermissions } from "@/lib/auth/permissions";

describe("admin route permissions", () => {
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
});
