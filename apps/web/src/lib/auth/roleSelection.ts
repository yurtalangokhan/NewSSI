interface RoleLike {
  name: string;
}

export function getSelectedRoleName(
  roles: readonly RoleLike[],
  selectedRole: string
): string {
  if (roles.length === 0) {
    return "";
  }

  if (selectedRole && roles.some((role) => role.name === selectedRole)) {
    return selectedRole;
  }

  return roles[0]?.name ?? "";
}
