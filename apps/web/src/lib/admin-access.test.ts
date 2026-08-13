import {
  ADMIN_ENTRY_REQUIRED_PERMISSIONS,
  canAccessAnyAdminRoute,
} from "./admin-access";

describe("admin access helpers", () => {
  it("collects admin entry permissions from configured admin routes", () => {
    expect(ADMIN_ENTRY_REQUIRED_PERMISSIONS).toContain("user:list");
    expect(ADMIN_ENTRY_REQUIRED_PERMISSIONS).toContain("role:list");
    expect(ADMIN_ENTRY_REQUIRED_PERMISSIONS).not.toContain("system-admin");
  });

  it("allows the admin entry when any route permission is present", () => {
    expect(canAccessAnyAdminRoute(["agent:list"])).toBe(true);
    expect(canAccessAnyAdminRoute(["content:read"])).toBe(false);
    expect(canAccessAnyAdminRoute(["*"])).toBe(true);
  });
});
