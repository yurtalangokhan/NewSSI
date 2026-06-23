export const WILDCARD_PERMISSION = "*";

export function hasPermission(
  permissions: readonly string[] | null | undefined,
  permission: string
): boolean {
  if (!permissions) {
    return false;
  }

  return (
    permissions.includes(WILDCARD_PERMISSION) || permissions.includes(permission)
  );
}

export function hasAnyPermission(
  permissions: readonly string[] | null | undefined,
  requiredPermissions: readonly string[] | null | undefined
): boolean {
  if (!requiredPermissions || requiredPermissions.length === 0) {
    return true;
  }

  return requiredPermissions.some((permission) =>
    hasPermission(permissions, permission)
  );
}

export function hasAllPermissions(
  permissions: readonly string[] | null | undefined,
  requiredPermissions: readonly string[] | null | undefined
): boolean {
  if (!requiredPermissions || requiredPermissions.length === 0) {
    return true;
  }

  return requiredPermissions.every((permission) =>
    hasPermission(permissions, permission)
  );
}
