import {
  type User,
  UserRole,
  USER_ROLE_LABELS,
  INVALID_ROLE_HOVER_TEXT,
} from "@/lib/types";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import useSWRMutation from "swr/mutation";

import InputSelect from "@/refresh-components/inputs/InputSelect";
import GenericConfirmModal from "@/components/modals/GenericConfirmModal";
import { useState } from "react";

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
  const { trigger: setUserRole, isMutating: isSettingRole } = useSWRMutation(
    "/api/manage/set-user-role",
    userMutationFetcher,
    { onSuccess, onError }
  );
  const isPaidEnterpriseFeaturesEnabled = usePaidEnterpriseFeaturesEnabled();

  const handleChange = (value: string) => {
    if (value === user.role) return;
    if (user.role === UserRole.CURATOR) {
      setShowConfirmModal(true);
      setPendingRole(value);
    } else {
      setUserRole({
        user_email: user.email,
        new_role: value,
      });
    }
  };

  const handleConfirm = () => {
    if (pendingRole) {
      setUserRole({
        user_email: user.email,
        new_role: pendingRole,
      });
    }
    setShowConfirmModal(false);
    setPendingRole(null);
  };

  return (
    <InputSelect
      value={user.role}
      onValueChange={handleChange}
      disabled={isSettingRole}
    >
      <InputSelect.Trigger />

      <InputSelect.Content>
        {allowedRoles.map((role) => (
          <InputSelect.Item
            key={role}
            value={role}
            data-testid={`user-role-dropdown-${role}`}
          >
            {USER_ROLE_LABELS[role]}
          </InputSelect.Item>
        ))}
      </InputSelect.Content>
    </InputSelect>
  );
}
