import { type User } from "@/lib/types";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import { useEffect, useState } from "react";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { formatRoleName } from "@/lib/auth/roles";

import InputSelect from "@/refresh-components/inputs/InputSelect";
import { useTranslation } from "react-i18next";

interface Role {
  name: string;
  description: string | null;
  is_builtin: boolean;
}

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
  const [selectedRole, setSelectedRole] = useState(user.role);

  const { data: roles, isLoading: isRolesLoading } = useSWR<{ roles: Role[] }>(
    "/api/user-service/roles",
    errorHandlingFetcher
  );

  const { trigger: setUserRole, isMutating: isSettingRole } = useSWRMutation(
    `/api/user-service/users/${user.id}/role`,
    userMutationFetcher
  );

  useEffect(() => {
    setSelectedRole(user.role);
  }, [user]);

  const handleChange = async (value: string) => {
    if (value === selectedRole) return;

    const previousRole = selectedRole;
    setSelectedRole(value);

    try {
      const updatedUser = (await setUserRole({
        role: value,
        method: "POST",
      })) as User;
      onSuccess(updatedUser);
    } catch (error) {
      setSelectedRole(previousRole);
      onError(error instanceof Error ? error.message : String(error));
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
                  key={role.name}
                  value={role.name}
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
