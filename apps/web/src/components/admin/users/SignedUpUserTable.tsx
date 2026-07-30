"use client";

import { type User } from "@/lib/types";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import useSWR from "swr";
import CenteredPageSelector from "@/components/admin/users/CenteredPageSelector";
import { toast } from "@/hooks/useToast";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
  TableHeader,
} from "@/components/ui/table";
import UserRoleDropdown from "@/components/admin/users/buttons/UserRoleDropdown";
import DeactivateUserButton from "@/components/admin/users/buttons/DeactivateUserButton";
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
import LineItem from "@/refresh-components/buttons/LineItem";
import Text from "@/refresh-components/texts/Text";
import Chip from "@/refresh-components/Chip";
import { useUser } from "@/providers/UserProvider";
import { LeaveOrganizationButton } from "@/components/admin/users/buttons/LeaveOrganizationButton";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
import ResetPasswordModal from "@/components/admin/users/ResetPasswordModal";
import EditUserModal from "@/components/admin/users/EditUserModal";
import Popover from "@/refresh-components/Popover";
import {
  SvgCheck,
  SvgFilter,
  SvgKey,
  SvgLogOut,
  SvgMoreHorizontal,
} from "@opal/icons";
import { Button as OpalButton } from "@opal/components";
import { cn } from "@/lib/utils";

const ITEMS_PER_PAGE = 10;
const PAGES_PER_BATCH = 2;

interface ActionMenuProps {
  user: User;
  currentUser: User | null;
  refresh: () => void;
  onUserChange: (user: User) => void;
  onEditUser: (user: User) => void;
  handleResetPassword: (user: User) => void;
}

export interface SignedUpUserTableProps {
  q: string;
  onTotalItemsChange?: (count: number) => void;
  onLoadingChange?: (isLoading: boolean) => void;
}

export default function SignedUpUserTable({
  q = "",
  onTotalItemsChange,
  onLoadingChange,
}: SignedUpUserTableProps) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<{
    is_active?: boolean;
    roles?: string[];
    invited?: boolean;
  }>({ invited: false });

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
    updateItem,
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

  const handlePopup = (message: string, type: "success" | "error") => {
    if (type === "success") {
      toast.success(message);
    } else {
      toast.error(message);
    }
  };

  const onRoleChangeSuccess = (updatedUser: User) => {
    updateItem(updatedUser.id, (user) => ({
      ...user,
      role: updatedUser.role,
    }));
    handlePopup(t("admin.users.roleUpdateSuccess"), "success");
  };
  const onRoleChangeError = (errorMsg: string) =>
    handlePopup(t("admin.users.roleUpdateError", { error: errorMsg }), "error");

  const updateUserRow = useCallback(
    (updatedUser: User) => {
      updateItem(updatedUser.id, (user) => ({
        ...user,
        ...updatedUser,
      }));
    },
    [updateItem]
  );

  const handleEditUserSuccess = useCallback(
    (updatedUser?: User) => {
      if (updatedUser) {
        updateUserRow(updatedUser);
        return;
      }

      refresh();
    },
    [refresh, updateUserRow]
  );

  const selectedRoles = useMemo(() => filters.roles ?? [], [filters.roles]);

  const setActiveFilter = useCallback((selectedStatus: string) => {
    setFilters((prev) => {
      if (selectedStatus === "all") {
        const { is_active, ...rest } = prev;
        return rest;
      }

      return {
        ...prev,
        is_active: selectedStatus === "true",
      };
    });
  }, []);

  const toggleRole = useCallback((roleName: string) => {
    setFilters((prev) => {
      const currentRoles = prev.roles || [];
      const newRoles = currentRoles.includes(roleName)
        ? currentRoles.filter((r) => r !== roleName)
        : [...currentRoles, roleName];

      return {
        ...prev,
        roles: newRoles.length ? newRoles : undefined,
      };
    });
  }, []);

  const removeRole = useCallback((roleName: string) => {
    setFilters((prev) => {
      const nextRoles = (prev.roles || []).filter((role) => role !== roleName);
      return {
        ...prev,
        roles: nextRoles.length ? nextRoles : undefined,
      };
    });
  }, []);

  const handleResetPassword = (user: User) => {
    setResetPasswordUser(user);
  };

  // --------------
  // Render Functions
  // --------------

  const renderFilters = () => (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-01 bg-background-neutral-00 px-3 py-2">
        <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto">
          <InputSelect
            value={filters.is_active?.toString() || "all"}
            onValueChange={setActiveFilter}
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
            <SelectTrigger className="h-[34px] w-[260px] border-border-01 bg-background-neutral-00">
              <SvgFilter className="mr-2 h-4 w-4 stroke-text-02" />
              <SelectValue>
                {selectedRoles.length
                  ? t("admin.users.rolesSelected", {
                      count: selectedRoles.length,
                    })
                  : t("admin.users.allRoles")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="bg-background-tint-00">
              <DynamicRoleFilterCheckboxes
                selectedRoles={selectedRoles}
                toggleRole={toggleRole}
              />
            </SelectContent>
          </Select>
        </div>
      </div>
      {selectedRoles.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border-01 bg-background-neutral-01 px-3 py-2">
          <Text as="p" figureSmallLabel text03>
            {t("admin.users.rolesSelected", { count: selectedRoles.length })}
          </Text>
          {selectedRoles.map((role) => (
            <Chip key={role} onRemove={() => removeRole(role)}>
              {t(`admin.users.roles.${role}`)}
            </Chip>
          ))}
        </div>
      )}
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

  function ActionMenu({
    user,
    currentUser,
    refresh,
    onUserChange,
    onEditUser,
    handleResetPassword,
  }: ActionMenuProps) {
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
                <Text as="span" mainUiBody>
                  {t("admin.users.leaveOrganization")}
                </Text>
              </LeaveOrganizationButton>
            ) : (
              <DeactivateUserButton
                user={user}
                deactivate={user.is_active}
                mutate={refresh}
                onSuccess={onUserChange}
                className={buttonClassName}
              >
                {user.is_active
                  ? t("admin.users.deactivateUserButton")
                  : t("admin.users.activateUserButton")}
              </DeactivateUserButton>
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
              {t("admin.users.editUserModal.title")}
            </Button>
          </div>
        </Popover.Content>
      </Popover>
    );
  }

  const renderActionButtons = (user: User) => {
    return (
      <div className="flex items-center justify-end gap-2">
        <ActionMenu
          user={user}
          currentUser={currentUser}
          refresh={refresh}
          onUserChange={updateUserRow}
          onEditUser={setEditUser}
          handleResetPassword={handleResetPassword}
        />
      </div>
    );
  };

  if (error) {
    return (
      <ErrorCallout
        errorTitle={t("admin.users.errorLoadingUsers")}
        errorMsg={error?.message}
      />
    );
  }

  return (
    <>
      {renderFilters()}
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow className="bg-background-neutral-01">
            <TableHead className="h-10">
              <Text as="span" figureSmallLabel text03>
                {t("admin.users.emailHeader")}
              </Text>
            </TableHead>
            <TableHead className="text-center">
              <Text as="span" figureSmallLabel text03>
                {t("admin.users.roleHeader")}
              </Text>
            </TableHead>
            <TableHead className="text-center">
              <Text as="span" figureSmallLabel text03>
                {t("admin.users.statusHeader")}
              </Text>
            </TableHead>
            <TableHead>
              <div className="flex">
                <div className="ml-auto">
                  <Text as="span" figureSmallLabel text03>
                    {t("admin.users.actionsHeader")}
                  </Text>
                </div>
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
                  <Text as="p" mainUiMuted text03 className="py-4">
                    {filters.roles?.length || filters.is_active !== undefined
                      ? t("admin.users.noUsersMatchingFilters")
                      : t("admin.users.noUsersFoundMatching", { query: q })}
                  </Text>
                </TableCell>
              </TableRow>
            ) : (
              pageOfUsers.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="py-3">
                    <UserEmailCell email={user.email} />
                  </TableCell>
                  <TableCell className="w-[200px] py-3">
                    {renderUserRoleDropdown(user)}
                  </TableCell>
                  <TableCell className="w-[140px] py-3">
                    <div className="flex justify-center">
                      <StatusBadge
                        active={user.is_active}
                        label={
                          user.is_active
                            ? t("admin.users.activeStatus")
                            : t("admin.users.inactiveStatus")
                        }
                      />
                    </div>
                  </TableCell>
                  <TableCell className="w-[96px] py-3 text-right">
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
          onSuccess={handleEditUserSuccess}
          canDelete={
            !(NEXT_PUBLIC_CLOUD_ENABLED && editUser.id === currentUser?.id)
          }
        />
      )}
    </>
  );
}

function UserEmailCell({ email }: { email: string }) {
  const initial = email.trim().charAt(0).toUpperCase() || "?";

  return (
    <div className="flex min-w-[220px] items-center gap-2">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-08 border border-border-01 bg-background-neutral-02">
        <Text as="span" figureSmallLabel text03>
          {initial}
        </Text>
      </div>
      <Text mainUiBody text05 className="truncate">
        {email}
      </Text>
    </div>
  );
}

function StatusBadge({ active, label }: { active: boolean; label: string }) {
  return (
    <div
      className={cn(
        "inline-flex min-w-[88px] items-center justify-center gap-1.5 rounded-08 border px-2 py-1",
        active
          ? "border-status-success-02 bg-status-success-00"
          : "border-border-01 bg-background-neutral-01"
      )}
    >
      <div
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          active ? "bg-status-success-05" : "bg-text-02"
        )}
      />
      <Text
        as="span"
        figureSmallLabel
        text03={!active}
        className={active ? "text-status-success-05" : undefined}
      >
        {label}
      </Text>
    </div>
  );
}

function DynamicRoleFilterCheckboxes({
  selectedRoles,
  toggleRole,
}: {
  selectedRoles: string[];
  toggleRole: (role: string) => void;
}) {
  const { t } = useTranslation();
  const { data: roles } = useSWR<{ roles: { name: string }[] }>(
    "/api/user-service/roles",
    errorHandlingFetcher
  );

  return (
    <>
      {roles?.roles?.map((role) => (
        <LineItem
          key={role.name}
          selected={selectedRoles.includes(role.name)}
          emphasized
          onClick={() => toggleRole(role.name)}
          rightChildren={
            selectedRoles.includes(role.name) ? (
              <SvgCheck className="h-3 w-3 stroke-text-05" />
            ) : (
              <div className="h-2 w-2 rounded-full border border-border-02" />
            )
          }
        >
          {t(`admin.users.roles.${role.name}`)}
        </LineItem>
      ))}
    </>
  );
}
