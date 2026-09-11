import {
  hasAllPermissions,
  hasAnyPermission,
  hasPermission,
} from "./permissions";

describe("permission helpers", () => {
  it("matches exact permissions", () => {
    expect(hasPermission(["role:list"], "role:list")).toBe(true);
    expect(hasPermission(["role:list"], "role:manage")).toBe(false);
  });

  it("treats wildcard as all permissions", () => {
    expect(hasPermission(["*"], "role:manage")).toBe(true);
    expect(hasAnyPermission(["*"], ["user:list", "role:manage"])).toBe(true);
  });

  it("matches any required permission and allows empty requirements", () => {
    expect(hasAnyPermission(["user:list"], ["role:list", "user:list"])).toBe(
      true
    );
    expect(hasAnyPermission(["user:list"], ["role:list"])).toBe(false);
    expect(hasAnyPermission(["user:list"], [])).toBe(true);
  });

  it("requires every permission when checking all permissions", () => {
    expect(
      hasAllPermissions(
        ["role:list", "permission:list"],
        ["role:list", "permission:list"]
      )
    ).toBe(true);
    expect(
      hasAllPermissions(["role:list"], ["role:list", "permission:list"])
    ).toBe(false);
    expect(hasAllPermissions(["*"], ["role:list", "permission:list"])).toBe(
      true
    );
  });
});
