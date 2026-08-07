import { ADMIN_ROUTE_CONFIG } from "@/lib/admin-routes";
import { hasAnyPermission } from "@/lib/auth/permissions";

export const ADMIN_ENTRY_REQUIRED_PERMISSIONS = Array.from(
  new Set(
    Object.values(ADMIN_ROUTE_CONFIG).flatMap(
      (routeConfig) => routeConfig.requiredPermissions ?? []
    )
  )
);

export function canAccessAnyAdminRoute(
  permissions: readonly string[] | null | undefined
): boolean {
  return hasAnyPermission(permissions, ADMIN_ENTRY_REQUIRED_PERMISSIONS);
}
