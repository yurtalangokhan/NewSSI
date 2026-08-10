"use client";

import { useCallback, useState } from "react";
import useSWR, { mutate } from "swr";

import SvgOrganization from "@opal/icons/organization";
import SvgShield from "@opal/icons/shield";
import SvgUsers from "@opal/icons/users";

import { OrganizationAccessPanel } from "@/components/organization/OrganizationAccessPanel";
import { OrganizationTree } from "@/components/organization/OrganizationTree";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationNode {
  id: string;
  name: string;
  path: string;
  parent_id: string | null;
  description?: string;
  metadata?: Record<string, unknown>;
  children?: OrganizationNode[];
  user_count?: number;
  permission_count?: number;
}

interface OrganizationMember {
  id: string;
  user_id: string;
  organization_id: string;
  role_in_org: "viewer" | "member" | "unit_manager";
  is_active?: boolean;
  user?: {
    id: string;
    email?: string;
    first_name?: string;
    last_name?: string;
    username?: string;
  } | null;
}

interface AvailableUser {
  id: string;
  email: string;
}

const ROLE_OPTIONS: Array<{ value: OrganizationMember["role_in_org"]; label: string }> = [
  { value: "viewer", label: "Viewer" },
  { value: "member", label: "Member" },
  { value: "unit_manager", label: "Unit manager" },
];

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(await responseDetail(response, "Request failed"));
  return response.json();
}

async function responseDetail(response: Response, fallback: string) {
  const data = (await response.json().catch(() => null)) as
    | { detail?: string; message?: string }
    | null;
  return data?.detail || data?.message || fallback;
}

function memberLabel(member: OrganizationMember) {
  const name = [member.user?.first_name, member.user?.last_name]
    .filter(Boolean)
    .join(" ");
  return name || member.user?.email || member.user?.username || member.user_id;
}

export default function OrganizationsPage() {
  const [selectedOrg, setSelectedOrg] = useState<OrganizationNode | null>(null);
  const [activeTab, setActiveTab] = useState("users");

  const { data: treeData, isLoading } = useSWR<
    { roots: OrganizationNode[] } | OrganizationNode[]
  >("/api/user-service/organizations/tree", fetchJson);
  const organizations = treeData
    ? "roots" in treeData
      ? treeData.roots
      : treeData
    : [];
  const membersKey = selectedOrg
    ? `/api/user-service/organizations/${selectedOrg.id}/users`
    : null;
  const { data: membersData } = useSWR<{ users: OrganizationMember[]; count: number }>(
    membersKey,
    fetchJson
  );
  const members = membersData?.users ?? [];
  const capabilityKey = selectedOrg
    ? `/api/user-service/organizations/${selectedOrg.id}/management-capability`
    : null;
  const { data: capability } = useSWR<{ editable: boolean }>(capabilityKey, fetchJson);
  const editable = capability?.editable === true;

  const refreshOrganizations = useCallback(async () => {
    await mutate("/api/user-service/organizations/tree");
  }, []);

  const handleCreateOrg = useCallback(
    async (parentId: string | null, name: string) => {
      const code = name
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9\s-]/g, "")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-+|-+$/g, "");
      const response = await fetch("/api/user-service/organizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, code, parent_id: parentId }),
      });
      if (!response.ok) {
        toast.error(await responseDetail(response, "Organization could not be created"));
        return;
      }
      await refreshOrganizations();
      toast.success("Organization created");
    },
    [refreshOrganizations]
  );

  const handleUpdateOrg = useCallback(
    async (id: string, updates: Partial<OrganizationNode>) => {
      const response = await fetch(`/api/user-service/organizations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (!response.ok) {
        toast.error(await responseDetail(response, "Organization could not be updated"));
        return;
      }
      await refreshOrganizations();
      if (selectedOrg?.id === id) setSelectedOrg({ ...selectedOrg, ...updates });
    },
    [refreshOrganizations, selectedOrg]
  );

  const handleDeleteOrg = useCallback(
    async (id: string) => {
      const response = await fetch(`/api/user-service/organizations/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        toast.error(await responseDetail(response, "Organization could not be deleted"));
        return;
      }
      await refreshOrganizations();
      if (selectedOrg?.id === id) setSelectedOrg(null);
    },
    [refreshOrganizations, selectedOrg]
  );

  const handleMoveOrg = useCallback(
    async (id: string, newParentId: string | null) => {
      const response = await fetch(`/api/user-service/organizations/${id}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_parent_id: newParentId }),
      });
      if (!response.ok) {
        toast.error(await responseDetail(response, "Organization could not be moved"));
        return;
      }
      await refreshOrganizations();
    },
    [refreshOrganizations]
  );

  async function refreshMembers() {
    if (membersKey) await mutate(membersKey);
    await refreshOrganizations();
  }

  async function handleAddUser(userId: string, role: OrganizationMember["role_in_org"]) {
    if (!selectedOrg) return;
    const response = await fetch(
      `/api/user-service/organizations/${selectedOrg.id}/users`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, role_in_org: role }),
      }
    );
    if (!response.ok) {
      throw new Error(await responseDetail(response, "Member could not be added"));
    }
    await refreshMembers();
  }

  async function handleRoleChange(
    userId: string,
    role: OrganizationMember["role_in_org"]
  ) {
    if (!selectedOrg) return;
    const response = await fetch(
      `/api/user-service/organizations/${selectedOrg.id}/users/${userId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role_in_org: role }),
      }
    );
    if (!response.ok) {
      toast.error(await responseDetail(response, "Member role could not be updated"));
      return;
    }
    await refreshMembers();
    toast.success("Member role updated");
  }

  async function handleRemoveUser(userId: string) {
    if (!selectedOrg || !confirm("Remove user from this organization?")) return;
    const response = await fetch(
      `/api/user-service/organizations/${selectedOrg.id}/users/${userId}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      toast.error(await responseDetail(response, "Member could not be removed"));
      return;
    }
    await refreshMembers();
  }

  if (isLoading) {
    return (
      <div className={cn("flex h-screen items-center justify-center")}>
        <Text text03>Loading organizations…</Text>
      </div>
    );
  }

  return (
    <main className={cn("flex h-screen bg-background-neutral-01")}>
      <aside className={cn("flex w-96 flex-col overflow-x-auto border-r border-border-02")}>
        <OrganizationTree
          organizations={organizations}
          onCreateOrg={handleCreateOrg}
          onUpdateOrg={handleUpdateOrg}
          onDeleteOrg={handleDeleteOrg}
          onMoveOrg={handleMoveOrg}
          onSelectOrg={(organization) => {
            setSelectedOrg(organization);
            setActiveTab("users");
          }}
          selectedOrgId={selectedOrg?.id}
        />
      </aside>

      <section className={cn("flex min-w-0 flex-1 flex-col")}>
        {selectedOrg ? (
          <>
            <header className={cn("flex flex-col gap-4 border-b border-border-02 p-6")}>
              <div className={cn("flex items-start justify-between gap-6")}>
                <div className={cn("flex min-w-0 items-center gap-3")}>
                  <div className={cn("rounded-12 bg-background-neutral-03 p-2")}>
                    <SvgOrganization className={cn("h-5 w-5 stroke-text-03")} />
                  </div>
                  <div className={cn("min-w-0")}>
                    <Text headingH2 text04 as="p" className={cn("truncate")}>
                      {selectedOrg.name}
                    </Text>
                    <Text secondaryBody text03 as="p" className={cn("truncate")}>
                      {selectedOrg.path}
                    </Text>
                  </div>
                </div>
                <div className={cn("flex gap-6")}>
                  <div className={cn("text-right")}>
                    <Text figureSmallValue text04 as="p">
                      {members.length}
                    </Text>
                    <Text figureSmallLabel text03>
                      Active members
                    </Text>
                  </div>
                  <div className={cn("text-right")}>
                    <Text figureSmallValue text04 as="p">
                      {selectedOrg.permission_count ?? 0}
                    </Text>
                    <Text figureSmallLabel text03>
                      Direct grants
                    </Text>
                  </div>
                </div>
              </div>
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <Tabs.List variant="pill">
                  <Tabs.Trigger value="users" icon={SvgUsers}>
                    Users
                  </Tabs.Trigger>
                  <Tabs.Trigger value="access" icon={SvgShield}>
                    Access
                  </Tabs.Trigger>
                </Tabs.List>
              </Tabs>
            </header>

            <div className={cn("flex-1 overflow-y-auto p-6")}>
              {activeTab === "users" ? (
                <UserAssignmentsPanel
                  assignments={members}
                  onAdd={handleAddUser}
                  onRoleChange={handleRoleChange}
                  onRemove={handleRemoveUser}
                  editable={editable}
                />
              ) : (
                <OrganizationAccessPanel
                  organization={selectedOrg}
                  members={members}
                  editable={editable}
                />
              )}
            </div>
          </>
        ) : (
          <div className={cn("flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center")}>
            <SvgOrganization className={cn("mb-2 h-12 w-12 stroke-text-02")} />
            <Text headingH3 text03 as="p">
              Select an organization
            </Text>
            <Text text03 as="p">
              Choose a unit from the tree to manage members and direct access.
            </Text>
          </div>
        )}
      </section>
    </main>
  );
}

function UserAssignmentsPanel({
  assignments,
  onAdd,
  onRoleChange,
  onRemove,
  editable,
}: {
  assignments: OrganizationMember[];
  onAdd: (userId: string, role: OrganizationMember["role_in_org"]) => Promise<void>;
  onRoleChange: (
    userId: string,
    role: OrganizationMember["role_in_org"]
  ) => Promise<void>;
  onRemove: (userId: string) => Promise<void>;
  editable: boolean;
}) {
  const [showAddUser, setShowAddUser] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedRole, setSelectedRole] = useState<OrganizationMember["role_in_org"]>(
    "member"
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data: usersData } = useSWR<{ users: AvailableUser[]; total: number }>(
    showAddUser ? "/api/user-service/users/" : null,
    fetchJson
  );

  async function submitUser() {
    if (!selectedUserId) return;
    setIsSubmitting(true);
    try {
      await onAdd(selectedUserId, selectedRole);
      setShowAddUser(false);
      setSelectedUserId("");
      setSelectedRole("member");
      toast.success("Member added");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Member could not be added");
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
        <div className={cn("grid gap-3 rounded-12 border border-border-01 bg-background-neutral-00 p-4 md:grid-cols-2")}>
          <div className={cn("flex flex-col gap-2")}>
            <Text secondaryAction text03>
              User
            </Text>
            <InputSelect value={selectedUserId} onValueChange={setSelectedUserId}>
              <InputSelect.Trigger aria-label="User" placeholder="Select a user" />
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
              onValueChange={(value) =>
                setSelectedRole(value as OrganizationMember["role_in_org"])
              }
            >
              <InputSelect.Trigger aria-label="New member role" />
              <InputSelect.Content>
                {ROLE_OPTIONS.map((role) => (
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
        <Text text03 as="p" className={cn("rounded-12 bg-background-neutral-00 p-8 text-center")}>
          No users are assigned to this organization.
        </Text>
      ) : (
        <div className={cn("flex flex-col gap-2")}>
          {assignments.map((assignment) => {
            const label = memberLabel(assignment);
            return (
              <div
                key={assignment.id}
                className={cn("grid items-center gap-3 rounded-12 border border-border-01 bg-background-neutral-00 p-4 md:grid-cols-[minmax(0,1fr)_11rem_auto]")}
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
                    void onRoleChange(
                      assignment.user_id,
                      value as OrganizationMember["role_in_org"]
                    )
                  }
                >
                  <InputSelect.Trigger aria-label={`Role for ${label}`} />
                  <InputSelect.Content>
                    {ROLE_OPTIONS.map((role) => (
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
