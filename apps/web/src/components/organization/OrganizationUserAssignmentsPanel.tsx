"use client";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

import {
  fetchDirectoryRoleCatalog,
  fetchDirectoryAssignableUsers,
} from "@/lib/api/domains/access/api";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import useSWR from "swr";

import type { OrganizationMember } from "@/components/organization/organizationTypes";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import { OrganizationUserPicker } from "./OrganizationUserPicker";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface RoleCatalogResponse {
  roles: Array<{ name: string }>;
}

interface OrganizationUserAssignmentsPanelProps {
  organizationId: string;
  globalAccess: boolean;
  assignments: OrganizationMember[];
  onAdd: (userId: string, role: string) => Promise<void>;
  onRoleChange: (userId: string, role: string) => Promise<void>;
  onRemove: (userId: string) => Promise<void>;
  editable: boolean;
}

async function fetchJson<T>(request: Promise<Response>): Promise<T> {
  const response = await request;
  if (!response.ok) throw new Error("Request failed");
  return response.json();
}

function memberLabel(member: OrganizationMember) {
  const name = [member.user?.first_name, member.user?.last_name]
    .filter(Boolean)
    .join(" ");
  return name || member.user?.email || member.user?.username || member.user_id;
}

export function OrganizationUserAssignmentsPanel({
  organizationId,
  globalAccess,
  assignments,
  onAdd,
  onRoleChange,
  onRemove,
  editable,
}: OrganizationUserAssignmentsPanelProps) {
  const { t } = useTranslation();
  const [showAddUser, setShowAddUser] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data: rolesData, isLoading: rolesLoading } =
    useSWR<RoleCatalogResponse>(
      globalAccess ? accessEndpoints.userServiceRoles.browserPath : null,
      () => fetchJson<RoleCatalogResponse>(fetchDirectoryRoleCatalog())
    );
  const normalizeRole = (name: string | null | undefined) =>
    (name ?? "").toLowerCase().replace(/[\s_-]/g, "");
  const catalog = rolesData?.roles ?? [];
  const endUser =
    catalog.find((role) => role.name === "enduser") ??
    catalog.find((role) => normalizeRole(role.name) === "enduser");
  const catalogOptions = catalog
    .filter(
      (role) => normalizeRole(role.name) !== "enduser" || role === endUser
    )
    .filter(
      (role) =>
        !["systemadmin", "enterpriseadmin", "unitmanager"].includes(
          normalizeRole(role.name)
        )
    )
    .map((role) => ({
      value: role.name,
      label:
        normalizeRole(role.name) === "enduser"
          ? t("admin.users.roles.enduser")
          : t(`admin.users.roles.${role.name}`, { defaultValue: role.name }),
    }));
  const roleOptions = globalAccess
    ? catalogOptions
    : [{ value: "enduser", label: t("admin.users.roles.enduser") }];
  if (globalAccess && rolesData)
    roleOptions.push({
      value: "unit_manager",
      label: t("admin.organizations.users.unitManager"),
    });
  const effectiveRole =
    roleOptions.length === 1
      ? roleOptions[0]!.value
      : roleOptions.some((role) => role.value === selectedRole)
        ? selectedRole
        : "";

  async function submitUser() {
    if (!selectedUserId || !effectiveRole || !editable) return;
    setIsSubmitting(true);
    try {
      await onAdd(selectedUserId, effectiveRole);
      setShowAddUser(false);
      setSelectedUserId("");
      setSelectedRole("");
      toast.success(t("admin.organizations.users.memberAdded"));
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("admin.organizations.notifications.memberAddFailed")
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className={cn("flex flex-col gap-4")}>
      <div className={cn("flex items-center justify-between gap-4")}>
        <div>
          <Text headingH3 text04 as="p">
            {t("admin.organizations.users.title")}
          </Text>
          <Text secondaryBody text03 as="p">
            {t("admin.organizations.users.description")}
          </Text>
        </div>
        <Button
          action
          primary
          size="md"
          disabled={!editable || showAddUser}
          onClick={() => {
            setSelectedRole("");
            setSelectedUserId("");
            setShowAddUser(true);
          }}
        >
          {t("admin.organizations.users.addUser")}
        </Button>
      </div>

      {showAddUser && (
        <div
          className={cn(
            "grid gap-3 rounded-12 border border-border-01 bg-background-neutral-00 p-4 md:grid-cols-2"
          )}
        >
          <div className={cn("flex flex-col gap-2")}>
            <Text secondaryAction text03>
              {t("admin.organizations.users.user")}
            </Text>
            <OrganizationUserPicker
              organizationId={organizationId}
              onSelect={setSelectedUserId}
            />
          </div>
          <div className={cn("flex flex-col gap-2")}>
            <Text secondaryAction text03>
              {t("admin.organizations.users.role")}
            </Text>
            <InputSelect
              value={effectiveRole}
              onValueChange={setSelectedRole}
              disabled={rolesLoading || !roleOptions.length}
            >
              <InputSelect.Trigger
                aria-label={t("admin.organizations.users.newMemberRole")}
                placeholder={t("admin.organizations.users.selectRole")}
              />
              <InputSelect.Content>
                {roleOptions.map((role) => (
                  <InputSelect.Item key={role.value} value={role.value}>
                    {role.label}
                  </InputSelect.Item>
                ))}
              </InputSelect.Content>
            </InputSelect>
          </div>
          <div className={cn("flex justify-end gap-2 md:col-span-2")}>
            <Button secondary size="md" onClick={() => setShowAddUser(false)}>
              {t("admin.organizations.actions.cancel")}
            </Button>
            <Button
              action
              primary
              size="md"
              disabled={
                !selectedUserId || !effectiveRole || isSubmitting || !editable
              }
              onClick={submitUser}
            >
              {isSubmitting
                ? t("admin.organizations.users.adding")
                : t("admin.organizations.users.addUser")}
            </Button>
          </div>
        </div>
      )}

      {assignments.length === 0 ? (
        <Text
          text03
          as="p"
          className={cn("rounded-12 bg-background-neutral-00 p-8 text-center")}
        >
          {t("admin.organizations.users.empty")}
        </Text>
      ) : (
        <div className={cn("flex flex-col gap-2")}>
          {assignments.map((assignment) => {
            const label = memberLabel(assignment);
            const currentRole = roleOptions.find(
              (role) =>
                normalizeRole(role.value) ===
                normalizeRole(assignment.role_in_org)
            );
            const assignedCatalogRole = catalog.find(
              (role) =>
                normalizeRole(role.name) ===
                normalizeRole(assignment.role_in_org)
            );
            const assignedName = assignment.role_in_org ?? "";
            const normalizedAssignedName = normalizeRole(assignedName);
            let currentRoleLabel: string | undefined;
            if (normalizedAssignedName === "unitmanager") {
              currentRoleLabel = t("admin.organizations.users.unitManager");
            } else if (assignedCatalogRole) {
              currentRoleLabel = t(`admin.users.roles.${assignedCatalogRole.name}`, {
                defaultValue: assignedCatalogRole.name,
              });
            } else if (
              ["systemadmin", "enterpriseadmin"].includes(normalizedAssignedName)
            ) {
              currentRoleLabel = t(`admin.users.roles.${assignedName}`, {
                defaultValue: assignedName,
              });
            }
            return (
              <div
                key={assignment.id}
                className={cn(
                  "grid items-center gap-3 rounded-12 border border-border-01 bg-background-neutral-00 p-4 md:grid-cols-[minmax(0,1fr)_11rem_auto]"
                )}
              >
                <div className={cn("min-w-0")}>
                  <Text mainUiAction text04 as="p" className={cn("truncate")}>
                    {label}
                  </Text>
                  <Text secondaryBody text03 as="p">
                    {t("admin.organizations.users.directMember")}
                  </Text>
                </div>
                <InputSelect
                  value={currentRole?.value ?? ""}
                  disabled={!editable}
                  onValueChange={(value) =>
                    void onRoleChange(assignment.user_id, value)
                  }
                >
                  <InputSelect.Trigger
                    placeholder={t("admin.organizations.users.selectRole")}
                    aria-label={t("admin.organizations.users.roleFor", {
                      name: label,
                    })}
                  >
                    {!currentRole ? currentRoleLabel : undefined}
                  </InputSelect.Trigger>
                  <InputSelect.Content>
                    {roleOptions.map((role) => (
                      <InputSelect.Item key={role.value} value={role.value}>
                        {role.label}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Content>
                </InputSelect>
                <Button
                  danger
                  secondary
                  size="md"
                  disabled={!editable}
                  onClick={() => void onRemove(assignment.user_id)}
                >
                  {t("admin.organizations.users.remove")}
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
