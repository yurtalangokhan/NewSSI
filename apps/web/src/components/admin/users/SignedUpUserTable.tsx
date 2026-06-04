"use client";

import { type User, UserRole, USER_ROLE_LABELS } from "@/lib/types";
import { ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import CenteredPageSelector from "./CenteredPageSelector";
import { toast } from "@/hooks/useToast";
import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { TableHeader } from "@/components/ui/table";
import UserRoleDropdown from "./buttons/UserRoleDropdown";
import DeactivateUserButton from "./buttons/DeactivateUserButton";
import usePaginatedFetch from "@/hooks/usePaginatedFetch";
import { ThreeDotsLoader } from "@/components/Loading";
import { ErrorCallout } from "@/components/ErrorCallout";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import {
  Select,
  SelectContent,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import Button from "@/refresh-components/buttons/Button";
import { useUser } from "@/providers/UserProvider";
import { LeaveOrganizationButton } from "./buttons/LeaveOrganizationButton";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import ResetPasswordModal from "./ResetPasswordModal";
import EditUserModal from "./EditUserModal";
import Popover from "@/refresh-components/Popover";
import {
  SvgKey,
  SvgLogOut,
  SvgMoreHorizontal,
} from "@opal/icons";
import { Button as OpalButton } from "@opal/components";
const ITEMS_PER_PAGE = 10;
const PAGES_PER_BATCH = 2;

interface ActionMenuProps {
  user: User;
  currentUser: User | null;
  refresh: () => void;
  onEditUser: (user: User) => void;
  handleResetPassword: (user: User) => void;
}

export interface SignedUpUserTableProps {
  q: string;
  countDisplay?: ReactNode;
  onTotalItemsChange?: (count: number) => void;
  onLoadingChange?: (isLoading: boolean) => void;
}

export default function SignedUpUserTable({
  q = "",
  countDisplay,
  onTotalItemsChange,
  onLoadingChange,
}: SignedUpUserTableProps) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<{
    is_active?: boolean;
    roles?: UserRole[];
    invited?: boolean;
  }>({ invited: false });

  const [selectedRoles, setSelectedRoles] = useState<UserRole[]>([]);
  const [resetPasswordUser, setResetPasswordUser] = useState<User | null>(null);
  const [editUser, setEditUser] = useState<User | null>(null);

  const {
    currentPageData: pageOfUsers,
    isLoading,
    error,
    currentPage,
    totalPages,
    goToPage,
    refresh,
    totalItems,
  } = usePaginatedFetch<User>({
    itemsPerPage: ITEMS_PER_PAGE,
    pagesPerBatch: PAGES_PER_BATCH,
    endpoint: "/api/user-service/users",
    query: q,
    filter: filters,
  });

  const { user: currentUser } = useUser();

  useEffect(() => {
    onLoadingChange?.(isLoading);
  }, [isLoading, onLoadingChange]);

  useEffect(() => {
    if (pageOfUsers !== null) {
      onTotalItemsChange?.(totalItems);
    }
  }, [pageOfUsers, totalItems, onTotalItemsChange]);

  if (error) {
    return (
      <ErrorCallout
        errorTitle={t("admin.users.errorLoadingUsers")}
        errorMsg={error?.message}
      />
    );
  }

  const handlePopup = (message: string, type: "success" | "error") => {
    if (type === "success") refresh();
    if (type === "success") {
      toast.success(message);
    } else {
      toast.error(message);
    }
  };

  const onRoleChangeSuccess = () =>
    handlePopup(t("admin.users.roleUpdateSuccess"), "success");
  const onRoleChangeError = (errorMsg: string) =>
    handlePopup(t("admin.users.roleUpdateError", { error: errorMsg }), "error");

  const toggleRole = (roleEnum: UserRole) => {
    setFilters((prev) => {
      const currentRoles = prev.roles || [];
      const newRoles = currentRoles.includes(roleEnum)
        ? currentRoles.filter((r) => r !== roleEnum) // Remove role if already selected
        : [...currentRoles, roleEnum]; // Add role if not selected

      setSelectedRoles(newRoles); // Update selected roles state
      return {
        ...prev,
        roles: newRoles,
      };
    });
  };

  const removeRole = (roleEnum: UserRole) => {
    setSelectedRoles((prev) => prev.filter((role) => role !== roleEnum)); // Remove role from selected roles
    toggleRole(roleEnum); // Deselect the role in filters
  };

  const handleResetPassword = (user: User) => {
    setResetPasswordUser(user);
  };

  // --------------
  // Render Functions
  // --------------

  const renderFilters = () => (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 py-4">
        <div className="flex flex-wrap items-center gap-4">
          <InputSelect
            value={filters.is_active?.toString() || "all"}
            onValueChange={(selectedStatus) =>
              setFilters((prev) => {
                if (selectedStatus === "all") {
                  const { is_active, ...rest } = prev;
                  return rest;
                }
                return {
                  ...prev,
                  is_active: selectedStatus === "true",
                };
              })
            }
          >
            <InputSelect.Trigger />

            <InputSelect.Content>
              <InputSelect.Item value="all">
                {t("admin.users.allStatus")}
              </InputSelect.Item>
              <InputSelect.Item value="true">
                {t("admin.users.activeStatus")}
              </InputSelect.Item>
              <InputSelect.Item value="false">
                {t("admin.users.inactiveStatus")}
              </InputSelect.Item>
            </InputSelect.Content>
          </InputSelect>

          <Select value="roles">
            <SelectTrigger className="w-[260px] h-[34px] bg-neutral">
              <SelectValue>
                {filters.roles?.length
                  ? t("admin.users.rolesSelected", {
                      count: filters.roles.length,
                    })
                  : t("admin.users.allRoles")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="bg-background-tint-00">
              {Object.entries(USER_ROLE_LABELS).map(([role]) => (
                <div
                  key={role}
                  className="flex items-center space-x-2 px-2 py-1.5 cursor-pointer hover:bg-background-200"
                  onClick={() => toggleRole(role as UserRole)}
                >
                  <input
                    type="checkbox"
                    checked={filters.roles?.includes(role as UserRole) || false}
                    onChange={(e) => e.stopPropagation()}
                  />
                  <label className="text-sm font-normal">
                    {t(`admin.users.roles.${role}`)}
                  </label>
                </div>
              ))}
            </SelectContent>
          </Select>
        </div>
        {countDisplay}
      </div>
      <div className="flex gap-2 py-1">
        {selectedRoles.map((role) => (
          <button
            key={role}
            className="border border-background-300 bg-neutral p-1 rounded text-sm hover:bg-background-200"
            onClick={() => removeRole(role)}
            style={{ padding: "2px 8px" }}
          >
            <span>{t(`admin.users.roles.${role}`)}</span>
            <span className="ml-3">&times;</span>
          </button>
        ))}
      </div>
    </>
  );

  const renderUserRoleDropdown = (user: User) => {
    return (
      <UserRoleDropdown
        user={user}
        onSuccess={onRoleChangeSuccess}
        onError={onRoleChangeError}
      />
    );
  };

  const ActionMenu: React.FC<ActionMenuProps> = ({
    user,
    currentUser,
    refresh,
    onEditUser,
    handleResetPassword,
  }) => {
    const buttonClassName = "w-full";

    return (
      <Popover>
        <Popover.Trigger asChild>
          <OpalButton prominence="secondary" icon={SvgMoreHorizontal} />
        </Popover.Trigger>
        <Popover.Content>
          <div className="grid gap-1">
            {NEXT_PUBLIC_CLOUD_ENABLED && user.id === currentUser?.id ? (
              <LeaveOrganizationButton
                user={user}
                mutate={refresh}
                className={buttonClassName}
              >
                <SvgLogOut className="mr-2" size={16} />
                <span>{t("admin.users.leaveOrganization")}</span>
              </LeaveOrganizationButton>
            ) : (
              <>
                <DeactivateUserButton
                  user={user}
                  deactivate={user.is_active}
                  mutate={refresh}
                  className={buttonClassName}
                >
                  {/*<UserX className="mr-2 h-4 w-4" />*/}
                  {user.is_active
                    ? t("admin.users.deactivateUserButton")
                    : t("admin.users.activateUserButton")}
                </DeactivateUserButton>
              </>
            )}
            {user.password_configured && (
              <Button
                className={buttonClassName}
                onClick={() => handleResetPassword(user)}
                leftIcon={SvgKey}
              >
                {t("admin.users.resetPasswordButton")}
              </Button>
            )}
            <Button
              className={buttonClassName}
              onClick={() => onEditUser(user)}
            >
              Edit User
            </Button>
          </div>
        </Popover.Content>
      </Popover>
    );
  };

  const renderActionButtons = (user: User) => {
    return (
      <div className="flex items-center justify-end gap-2">
        <ActionMenu
          user={user}
          currentUser={currentUser}
          refresh={refresh}
          onEditUser={setEditUser}
          handleResetPassword={handleResetPassword}
        />
      </div>
    );
  };

  return (
    <>
      {renderFilters()}
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.users.emailHeader")}</TableHead>
            <TableHead className="text-center">
              {t("admin.users.roleHeader")}
            </TableHead>
            <TableHead className="text-center">
              {t("admin.users.statusHeader")}
            </TableHead>
            <TableHead>
              <div className="flex">
                <div className="ml-auto">{t("admin.users.actionsHeader")}</div>
              </div>
            </TableHead>
          </TableRow>
        </TableHeader>
        {isLoading ? (
          <TableBody>
            <TableRow>
              <TableCell colSpan={4} className="text-center">
                <ThreeDotsLoader />
              </TableCell>
            </TableRow>
          </TableBody>
        ) : (
          <TableBody>
            {!pageOfUsers?.length ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center">
                  <p className="pt-4 pb-4">
                    {filters.roles?.length || filters.is_active !== undefined
                      ? t("admin.users.noUsersMatchingFilters")
                      : t("admin.users.noUsersFoundMatching", { query: q })}
                  </p>
                </TableCell>
              </TableRow>
            ) : (
              pageOfUsers.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>{user.email}</TableCell>
                  <TableCell className="w-[180px]">
                    {renderUserRoleDropdown(user)}
                  </TableCell>
                  <TableCell className="text-center w-[140px]">
                    <i>
                      {user.is_active
                        ? t("admin.users.activeStatus")
                        : t("admin.users.inactiveStatus")}
                    </i>
                  </TableCell>
                  <TableCell className="text-right  w-[300px] ">
                    {renderActionButtons(user)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        )}
      </Table>
      {totalPages > 1 && (
        <CenteredPageSelector
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={goToPage}
        />
      )}
      {resetPasswordUser && (
        <ResetPasswordModal
          user={resetPasswordUser}
          onClose={() => setResetPasswordUser(null)}
        />
      )}
      {editUser && (
        <EditUserModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSuccess={refresh}
          canDelete={!(NEXT_PUBLIC_CLOUD_ENABLED && editUser.id === currentUser?.id)}
        />
      )}
    </>
  );
}
