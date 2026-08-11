"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import useSWR from "swr";

import type { OrganizationMember } from "@/components/organization/organizationTypes";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface AvailableUser {
  id: string;
  email: string;
}

interface RoleCatalogResponse {
  roles: Array<{ name: string }>;
}

interface OrganizationUserAssignmentsPanelProps {
  assignments: OrganizationMember[];
  onAdd: (userId: string, role: string) => Promise<void>;
  onRoleChange: (userId: string, role: string) => Promise<void>;
  onRemove: (userId: string) => Promise<void>;
  editable: boolean;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
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
  assignments,
  onAdd,
  onRoleChange,
  onRemove,
  editable,
}: OrganizationUserAssignmentsPanelProps) {
  const { t } = useTranslation();
  const [showAddUser, setShowAddUser] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedRole, setSelectedRole] = useState("unit_manager");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data: rolesData, isLoading: rolesLoading } =
    useSWR<RoleCatalogResponse>("/api/user-service/roles", fetchJson);
  const { data: usersData } = useSWR<{ users: AvailableUser[]; total: number }>(
    showAddUser ? "/api/user-service/users/" : null,
    fetchJson
  );
  const roleOptions = [
    ...(rolesData?.roles ?? [])
      .filter((role) => role.name !== "unit_manager")
      .map((role) => ({
        value: role.name,
        label: t(`admin.users.roles.${role.name}`),
      })),
    { value: "unit_manager", label: "Birim Yöneticisi" },
  ];

  async function submitUser() {
    if (!selectedUserId) return;
    setIsSubmitting(true);
    try {
      await onAdd(selectedUserId, selectedRole);
      setShowAddUser(false);
      setSelectedUserId("");
      setSelectedRole("unit_manager");
      toast.success("Member added");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Member could not be added"
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
            Members
          </Text>
          <Text secondaryBody text03 as="p">
            Manage unit membership and appoint unit managers.
          </Text>
        </div>
        <Button
          action
          primary
          size="md"
          disabled={!editable}
          onClick={() => setShowAddUser(true)}
        >
          Add user
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
              User
            </Text>
            <InputSelect
              value={selectedUserId}
              onValueChange={setSelectedUserId}
            >
              <InputSelect.Trigger
                aria-label="User"
                placeholder="Select a user"
              />
              <InputSelect.Content>
                {(usersData?.users ?? []).map((user) => (
                  <InputSelect.Item key={user.id} value={user.id}>
                    {user.email}
                  </InputSelect.Item>
                ))}
              </InputSelect.Content>
            </InputSelect>
          </div>
          <div className={cn("flex flex-col gap-2")}>
            <Text secondaryAction text03>
              Role
            </Text>
            <InputSelect
              value={selectedRole}
              onValueChange={setSelectedRole}
              disabled={rolesLoading}
            >
              <InputSelect.Trigger aria-label="New member role" />
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
              Cancel
            </Button>
            <Button
              action
              primary
              size="md"
              disabled={!selectedUserId || isSubmitting}
              onClick={submitUser}
            >
              {isSubmitting ? "Adding…" : "Add user"}
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
          No users are assigned to this organization.
        </Text>
      ) : (
        <div className={cn("flex flex-col gap-2")}>
          {assignments.map((assignment) => {
            const label = memberLabel(assignment);
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
                    Direct member of this unit
                  </Text>
                </div>
                <InputSelect
                  value={assignment.role_in_org}
                  disabled={!editable}
                  onValueChange={(value) =>
                    void onRoleChange(assignment.user_id, value)
                  }
                >
                  <InputSelect.Trigger aria-label={`Role for ${label}`} />
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
                  Remove
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
