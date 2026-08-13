import { isAdminFromPermissions } from "./roles";

describe("isAdminFromPermissions", () => {
  it("uses permissions instead of role names to detect admin access", () => {
    expect(isAdminFromPermissions(["role:list"])).toBe(true);
    expect(isAdminFromPermissions(["chat:send"])).toBe(false);
  });
});
