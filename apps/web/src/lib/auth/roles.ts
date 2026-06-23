import type { User } from "@/lib/types";

export const ADMIN_ROLES = new Set(["system-admin", "enterprise-admin"]);

export function getEffectiveUserRole(
  user: Pick<User, "role" | "is_superuser">
): string {
  if (user.is_superuser) {
    return "system-admin";
  }

  return user.role;
}

export function isAdminUser(
  user: Pick<User, "role" | "is_superuser"> | null | undefined
) {
  if (!user) {
    return false;
  }

  return ADMIN_ROLES.has(getEffectiveUserRole(user));
}
