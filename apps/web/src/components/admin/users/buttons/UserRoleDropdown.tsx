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
import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
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
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingRole, setPendingRole] = useState<string | null>(null);

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
    <>
      {showConfirmModal && (
        <GenericConfirmModal
          title={t("admin.users.changeCuratorRoleTitle")}
          message={t("admin.users.changeCuratorRoleWarning", {
            newRole:
              t(`admin.users.roles.${pendingRole as UserRole}`) ??
              t(`admin.users.roles.${user.role}`),
          })}
          confirmText={t("admin.users.switchRoleToButton", {
            role:
              t(`admin.users.roles.${pendingRole as UserRole}`) ??
              t(`admin.users.roles.${user.role}`),
          })}
          onClose={() => setShowConfirmModal(false)}
          onConfirm={handleConfirm}
        />
      )}

      <InputSelect
        value={user.role}
        onValueChange={handleChange}
        disabled={isSettingRole}
      >
        <InputSelect.Trigger />

        <InputSelect.Content>
          {(Object.entries(USER_ROLE_LABELS) as [UserRole, string][]).map(
            ([role, label]) => {
              // Don't want to ever show external permissioned users because it's scary
              if (role === UserRole.EXT_PERM_USER) return null;

              // Only want to show limited users if paid enterprise features are enabled
              // Also, dont want to show these other roles in general
              const isNotVisibleRole =
                (!isPaidEnterpriseFeaturesEnabled &&
                  role === UserRole.GLOBAL_CURATOR) ||
                role === UserRole.CURATOR ||
                role === UserRole.LIMITED ||
                role === UserRole.SLACK_USER;

              // Always show the current role
              const isCurrentRole = user.role === role;

              return isNotVisibleRole && !isCurrentRole ? null : (
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
