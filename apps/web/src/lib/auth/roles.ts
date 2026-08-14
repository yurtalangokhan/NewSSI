import { canAccessAnyAdminRoute } from "@/lib/admin-access";

export function formatRoleName(roleName: string): string {
  return roleName
    .split("-")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function isAdminFromPermissions(
  permissions: readonly string[] | null | undefined
): boolean {
  return canAccessAnyAdminRoute(permissions);
}
