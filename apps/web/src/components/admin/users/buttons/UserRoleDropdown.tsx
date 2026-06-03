import { type User, UserRole, USER_ROLE_LABELS } from "@/lib/types";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import useSWRMutation from "swr/mutation";

import InputSelect from "@/refresh-components/inputs/InputSelect";
import { useTranslation } from "react-i18next";

export interface UserRoleDropdownProps {
  user: User;
  onSuccess: () => void;
  onError: (message: string) => void;
}

export default function UserRoleDropdown({
  user,
  onSuccess,
  onError,
}: UserRoleDropdownProps) {
  const { t } = useTranslation();

  const { trigger: setUserRole, isMutating: isSettingRole } = useSWRMutation(
    `/api/user-service/users/${user.id}/role`,
    userMutationFetcher,
    { onSuccess, onError }
  );

  const handleChange = (value: string) => {
    if (value === user.role) return;
    setUserRole({
      role: value,
      method: "POST",
    });
  };

  return (
    <>
      <InputSelect
        value={user.role}
        onValueChange={handleChange}
        disabled={isSettingRole}
      >
        <InputSelect.Trigger />

        <InputSelect.Content>
          {(Object.entries(USER_ROLE_LABELS) as [UserRole, string][]).map(
            ([role]) => {
              return (
                <InputSelect.Item
                  key={role}
                  value={role}
                  data-testid={`user-role-dropdown-${role}`}
                  title={t(`admin.users.rolesHover.${role}`) ?? ""}
                  data-tooltip-delay="0"
                >
                  {t(`admin.users.roles.${role}`)}
                </InputSelect.Item>
              );
            }
          )}
        </InputSelect.Content>
      </InputSelect>
    </>
  );
}
