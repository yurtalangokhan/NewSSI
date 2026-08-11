"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR, { mutate } from "swr";

import { OrganizationAccessPanel } from "@/components/organization/OrganizationAccessPanel";
import { OrganizationDesigner } from "@/components/organization/OrganizationDesigner";
import { OrganizationTree } from "@/components/organization/OrganizationTree";
import type {
  OrganizationMember,
  OrganizationNode,
} from "@/components/organization/organizationTypes";
import { OrganizationUserAssignmentsPanel } from "@/components/organization/OrganizationUserAssignmentsPanel";
import { toast } from "@/hooks/useToast";
import { useUser } from "@/providers/UserProvider";
import { SvgOrganization, SvgShield, SvgUsers } from "@/icons";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

const DEFAULT_TREE_PANE_WIDTH = 480;
const MIN_TREE_PANE_WIDTH = 320;
const TREE_PANE_WIDTH_STORAGE_KEY = "admin-organizations-tree-pane-width";
const ORGANIZATION_TREE_KEY = "/api/user-service/organizations/tree";
const ORGANIZATION_LAYOUT_KEY = "/api/user-service/organizations/layout";

function findOrganization(
  organizations: OrganizationNode[],
  id: string | null
): OrganizationNode | null {
  if (!id) return null;
  for (const organization of organizations) {
    if (organization.id === id) return organization;
    const match = findOrganization(organization.children ?? [], id);
    if (match) return match;
  }
  return null;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(await responseDetail(response, "Request failed"));
  return response.json();
}

async function responseDetail(response: Response, fallback: string) {
  const data = (await response.json().catch(() => null)) as {
    detail?: string;
    message?: string;
  } | null;
  return data?.detail || data?.message || fallback;
}

export default function OrganizationsPage() {
  const { hasPermission } = useUser();
  const canCreateRoot = hasPermission("org:create");
  const canEditLayout = hasPermission("org:update");
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("users");
  const [isDesignerOpen, setIsDesignerOpen] = useState(false);
  const workspaceRef = useRef<HTMLElement>(null);
  const [treePaneWidth, setTreePaneWidth] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_TREE_PANE_WIDTH;
    const storedWidth = Number(
      window.sessionStorage.getItem(TREE_PANE_WIDTH_STORAGE_KEY)
    );
    return Number.isFinite(storedWidth) && storedWidth >= MIN_TREE_PANE_WIDTH
      ? storedWidth
      : DEFAULT_TREE_PANE_WIDTH;
  });

  const clampTreePaneWidth = useCallback((width: number) => {
    const workspaceWidth = workspaceRef.current?.clientWidth || 1440;
    const maximumWidth = Math.max(
      MIN_TREE_PANE_WIDTH,
      Math.floor(workspaceWidth * 0.45)
    );
    return Math.min(maximumWidth, Math.max(MIN_TREE_PANE_WIDTH, width));
  }, []);

  useEffect(() => {
    window.sessionStorage.setItem(
      TREE_PANE_WIDTH_STORAGE_KEY,
      String(treePaneWidth)
    );
  }, [treePaneWidth]);

  const handleSplitterPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const handlePointerMove = (pointerEvent: PointerEvent) => {
        const workspaceLeft =
          workspaceRef.current?.getBoundingClientRect().left ?? 0;
        setTreePaneWidth(
          clampTreePaneWidth(pointerEvent.clientX - workspaceLeft)
        );
      };
      const handlePointerUp = () => {
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [clampTreePaneWidth]
  );

  const handleSplitterKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      setTreePaneWidth((width) => clampTreePaneWidth(width + direction * 16));
    },
    [clampTreePaneWidth]
  );

  const { data: treeData, isLoading } = useSWR<
    { roots: OrganizationNode[] } | OrganizationNode[]
  >(ORGANIZATION_TREE_KEY, fetchJson);
  const organizations = treeData
    ? "roots" in treeData
      ? treeData.roots
      : treeData
    : [];
  const selectedOrg = useMemo(
    () => findOrganization(organizations, selectedOrgId),
    [organizations, selectedOrgId]
  );
  const membersKey = selectedOrg
    ? `/api/user-service/organizations/${selectedOrg.id}/users`
    : null;
  const { data: membersData } = useSWR<{
    users: OrganizationMember[];
    count: number;
  }>(membersKey, fetchJson);
  const members = membersData?.users ?? [];
  const capabilityKey = selectedOrg
    ? `/api/user-service/organizations/${selectedOrg.id}/management-capability`
    : null;
  const { data: capability, isLoading: capabilityLoading } = useSWR<{
    editable: boolean;
  }>(
    capabilityKey,
    fetchJson
  );
  const editable = capability?.editable === true;

  const refreshOrganizations = useCallback(async () => {
    await mutate(ORGANIZATION_TREE_KEY);
  }, []);

  const refreshOrganizationsAndLayout = useCallback(async () => {
    await Promise.all([
      mutate(ORGANIZATION_TREE_KEY),
      mutate(ORGANIZATION_LAYOUT_KEY),
    ]);
  }, []);

  const handleSelectOrg = useCallback((organization: OrganizationNode) => {
    setSelectedOrgId(organization.id);
    setActiveTab("users");
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
        toast.error(
          await responseDetail(response, "Organization could not be created")
        );
        return;
      }
      await refreshOrganizationsAndLayout();
      toast.success("Organization created");
    },
    [refreshOrganizationsAndLayout]
  );

  const handleUpdateOrg = useCallback(
    async (id: string, updates: Partial<OrganizationNode>) => {
      const response = await fetch(`/api/user-service/organizations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (!response.ok) {
        toast.error(
          await responseDetail(response, "Organization could not be updated")
        );
        return;
      }
      await refreshOrganizations();
    },
    [refreshOrganizations]
  );

  const handleDeleteOrg = useCallback(
    async (id: string) => {
      const response = await fetch(`/api/user-service/organizations/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        toast.error(
          await responseDetail(response, "Organization could not be deleted")
        );
        return;
      }
      await refreshOrganizationsAndLayout();
      if (selectedOrgId === id) setSelectedOrgId(null);
    },
    [refreshOrganizationsAndLayout, selectedOrgId]
  );

  const handleMoveOrg = useCallback(
    async (id: string, newParentId: string | null) => {
      const response = await fetch(
        `/api/user-service/organizations/${id}/move`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_parent_id: newParentId }),
        }
      );
      if (!response.ok) {
        toast.error(
          await responseDetail(response, "Organization could not be moved")
        );
        return;
      }
      await refreshOrganizationsAndLayout();
    },
    [refreshOrganizationsAndLayout]
  );

  async function refreshMembers() {
    if (membersKey) await mutate(membersKey);
    await refreshOrganizations();
  }

  async function handleAddUser(
    userId: string,
    role: OrganizationMember["role_in_org"]
  ) {
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
      throw new Error(
        await responseDetail(response, "Member could not be added")
      );
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
      toast.error(
        await responseDetail(response, "Member role could not be updated")
      );
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
      toast.error(
        await responseDetail(response, "Member could not be removed")
      );
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
    <main
      ref={workspaceRef}
      className={cn(
        "flex h-screen flex-col bg-background-neutral-01 md:flex-row"
      )}
    >
      <aside
        data-testid="organization-tree-pane"
        className={cn(
          "flex h-[40vh] w-full shrink-0 flex-col overflow-hidden border-b border-border-02 max-md:!w-full",
          "md:h-auto md:border-b-0"
        )}
        style={{ width: `${treePaneWidth}px` }}
      >
        <OrganizationTree
          organizations={organizations}
          onCreateOrg={handleCreateOrg}
          onUpdateOrg={handleUpdateOrg}
          onDeleteOrg={handleDeleteOrg}
          onMoveOrg={handleMoveOrg}
          onSelectOrg={handleSelectOrg}
          onOpenDesigner={() => {
            setIsDesignerOpen(true);
            void refreshOrganizations();
          }}
          selectedOrgId={selectedOrg?.id}
        />
      </aside>

      <div
        role="separator"
        aria-label="Resize organization tree"
        aria-orientation="vertical"
        aria-valuemin={MIN_TREE_PANE_WIDTH}
        aria-valuemax={clampTreePaneWidth(Number.MAX_SAFE_INTEGER)}
        aria-valuenow={treePaneWidth}
        tabIndex={0}
        onPointerDown={handleSplitterPointerDown}
        onKeyDown={handleSplitterKeyDown}
        className={cn(
          "group relative hidden w-2 shrink-0 cursor-col-resize touch-none outline-none md:block",
          "before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-border-02",
          "hover:before:w-0.5 hover:before:bg-action-link-05 focus-visible:before:w-0.5 focus-visible:before:bg-action-link-05"
        )}
      />

      <section className={cn("flex min-w-0 flex-1 flex-col")}>
        {selectedOrg ? (
          <>
            <header
              className={cn(
                "flex flex-col gap-4 border-b border-border-02 p-6"
              )}
            >
              <div className={cn("flex items-start justify-between gap-6")}>
                <div className={cn("flex min-w-0 items-center gap-3")}>
                  <div
                    className={cn("rounded-12 bg-background-neutral-03 p-2")}
                  >
                    <SvgOrganization className={cn("h-5 w-5 stroke-text-03")} />
                  </div>
                  <div className={cn("min-w-0")}>
                    <Text headingH2 text04 as="p" className={cn("truncate")}>
                      {selectedOrg.name}
                    </Text>
                    <Text
                      secondaryBody
                      text03
                      as="p"
                      className={cn("truncate")}
                    >
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
                <OrganizationUserAssignmentsPanel
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
                  onSaveComplete={refreshOrganizations}
                />
              )}
            </div>
          </>
        ) : (
          <div
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center"
            )}
          >
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
      {isDesignerOpen && (
        <OrganizationDesigner
          organizations={organizations}
          selectedOrg={selectedOrg}
          members={members}
          editable={editable}
          capabilityLoading={Boolean(selectedOrg) && capabilityLoading}
          canCreateRoot={canCreateRoot}
          canEditLayout={canEditLayout}
          onClose={() => setIsDesignerOpen(false)}
          onSelectOrg={handleSelectOrg}
          onCreateOrg={handleCreateOrg}
          onUpdateOrg={handleUpdateOrg}
          onDeleteOrg={handleDeleteOrg}
          onMoveOrg={handleMoveOrg}
          onAddUser={handleAddUser}
          onRoleChange={handleRoleChange}
          onRemoveUser={handleRemoveUser}
          onAccessSaveComplete={refreshOrganizations}
        />
      )}
    </main>
  );
}
