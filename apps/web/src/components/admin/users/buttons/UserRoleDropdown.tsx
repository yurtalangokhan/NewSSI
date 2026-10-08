import { errorMessageFromUnknown } from "@/lib/api/errors";
import { type User } from "@/lib/types";
import { setDirectoryUserRole } from "@/lib/api/domains/access/api";
import { useDirectoryRoles } from "@/lib/api/domains/access/hooks";
import { useEffect, useMemo, useState } from "react";
import useSWRMutation from "swr/mutation";
import { formatRoleName } from "@/lib/auth/roles";

import InputSelect from "@/refresh-components/inputs/InputSelect";
import { useTranslation } from "react-i18next";

export interface UserRoleDropdownProps {
  user: User;
  onSuccess: (user: User) => void;
  onError: (message: string) => void;
}

export default function UserRoleDropdown({
  user,
  onSuccess,
  onError,
}: UserRoleDropdownProps) {
  const { t } = useTranslation();
  const { data: roles, isLoading: isRolesLoading } = useDirectoryRoles();
  // The user record carries the primary role's name; the API takes its Keycloak ID.
  const currentRoleId = useMemo(
    () => roles?.roles.find((role) => role.name === user.role)?.id ?? "",
    [roles, user.role]
  );
  const [selectedRole, setSelectedRole] = useState(currentRoleId);

  const { trigger: setUserRole, isMutating: isSettingRole } = useSWRMutation(
    ["set-directory-user-role", user.id],
    (_key, { arg }: { arg: string }) => setDirectoryUserRole(user.id, arg)
  );

  useEffect(() => {
    setSelectedRole(currentRoleId);
  }, [currentRoleId]);

  const handleChange = async (roleId: string) => {
    if (roleId === selectedRole) return;

    const previousRole = selectedRole;
    setSelectedRole(roleId);

    try {
      const updatedUser = await setUserRole(roleId);
      onSuccess(updatedUser);
    } catch (error) {
      setSelectedRole(previousRole);
      onError(errorMessageFromUnknown(error));
    }
  };

  return (
    <>
      <InputSelect
        value={selectedRole}
        onValueChange={handleChange}
        disabled={isSettingRole || isRolesLoading}
      >
        <InputSelect.Trigger />

        <InputSelect.Content>
          {!isRolesLoading && roles?.roles
            ? roles.roles.map((role) => (
                <InputSelect.Item
                  key={role.id}
                  value={role.id}
                  data-testid={`user-role-dropdown-${role.name}`}
                  title={role.description ?? ""}
                  data-tooltip-delay="0"
                >
                  {t(`admin.users.roles.${role.name}`, {
                    defaultValue: formatRoleName(role.name),
                  })}
                </InputSelect.Item>
              ))
            : null}
        </InputSelect.Content>
      </InputSelect>
    </>
  );
}
