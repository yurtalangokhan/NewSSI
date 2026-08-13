"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR, { mutate } from "swr";
import { useTranslation } from "react-i18next";

import { OrganizationAccessPanel } from "@/components/organization/OrganizationAccessPanel";
import { OrganizationDesigner } from "@/components/organization/OrganizationDesigner";
import { OrganizationTree } from "@/components/organization/OrganizationTree";
import type {
  OrganizationMember,
  OrganizationMembersByUnit,
  OrganizationNode,
  OrganizationRevealRequest,
} from "@/components/organization/organizationTypes";
import { OrganizationUserAssignmentsPanel } from "@/components/organization/OrganizationUserAssignmentsPanel";
import { toast } from "@/hooks/useToast";
import { useUser } from "@/providers/UserProvider";
import { SvgOrganization, SvgUsers } from "@/icons";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

const DEFAULT_TREE_PANE_WIDTH = 480;
const MIN_TREE_PANE_WIDTH = 320;
const TREE_PANE_WIDTH_STORAGE_KEY = "admin-organizations-tree-pane-width";
const ORGANIZATION_TREE_KEY = "/api/user-service/organizations/tree?max_depth=2";
const ORGANIZATION_LAYOUT_KEY = "/api/user-service/organizations/layout";
const ORGANIZATION_MEMBERS_KEY = "/api/user-service/organizations/members";
const SHOW_MEMBERS_STORAGE_KEY = "admin-organizations-show-members";

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

function mergeSubunits(
  nodes: OrganizationNode[],
  subunitsByParentId: Record<string, OrganizationNode[]>
): OrganizationNode[] {
  return nodes.map((node) => {
    const loadedChildren = subunitsByParentId[node.id];
    const existingChildren = node.children ?? [];
    const existingIds = new Set(existingChildren.map((child) => child.id));
    const additionalChildren = (loadedChildren ?? []).filter(
      (child) => !existingIds.has(child.id)
    );
    const combinedChildren = [...existingChildren, ...additionalChildren];
    const mergedChildren = mergeSubunits(combinedChildren, subunitsByParentId);
    const totalChildCount =
      loadedChildren && loadedChildren.length > 0
        ? loadedChildren.length
        : node.children_count ?? (node.children?.length || 0);
    return {
      ...node,
      children: mergedChildren,
      has_children:
        (node.children && node.children.length > 0) ||
        (loadedChildren && loadedChildren.length > 0) ||
        node.has_children,
      children_count: totalChildCount,
    };
  });
}

function sortOrganizations(
  first: OrganizationNode,
  second: OrganizationNode
) {
  const orderDifference =
    (first.order_index ?? Number.MAX_SAFE_INTEGER) -
    (second.order_index ?? Number.MAX_SAFE_INTEGER);
  if (orderDifference !== 0) return orderDifference;
  const nameDifference = first.name.localeCompare(second.name);
  return nameDifference !== 0 ? nameDifference : first.id.localeCompare(second.id);
}

function mergeOrganizationsById(...lists: OrganizationNode[][]) {
  const organizationsById = new Map<string, OrganizationNode>();
  lists.flat().forEach((organization) => {
    organizationsById.set(organization.id, {
      ...organizationsById.get(organization.id),
      ...organization,
    });
  });
  return Array.from(organizationsById.values()).sort(sortOrganizations);
}

type SearchSurface = "tree" | "designer";

interface PendingReveal extends OrganizationRevealRequest {
  surface: SearchSurface;
}

export default function OrganizationsPage() {
  const { t } = useTranslation();
  const { hasPermission } = useUser();
  const canCreateRoot = hasPermission("org:create");
  const canEditLayout = hasPermission("org:update");
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<OrganizationNode[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [resultsLimited, setResultsLimited] = useState(false);
  const [revealLoading, setRevealLoading] = useState(false);
  const [pendingReveal, setPendingReveal] = useState<PendingReveal | null>(null);
  const searchControllerRef = useRef<AbortController | null>(null);
  const searchRequestIdRef = useRef(0);
  const revealRequestIdRef = useRef(0);
  const [activeTab, setActiveTab] = useState("users");
  const [isDesignerOpen, setIsDesignerOpen] = useState(false);
  const [showMembers, setShowMembers] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.sessionStorage.getItem(SHOW_MEMBERS_STORAGE_KEY) === "true";
  });
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

  const [subunitsByParentId, setSubunitsByParentId] = useState<
    Record<string, OrganizationNode[]>
  >({});
  const [unitMembersMap, setUnitMembersMap] = useState<OrganizationMembersByUnit>({});

  const { data: treeData, isLoading } = useSWR<
    { roots: OrganizationNode[] } | OrganizationNode[]
  >(ORGANIZATION_TREE_KEY, fetchJson);
  const rawOrganizations = useMemo(() => {
    if (!treeData) return [];
    return "roots" in treeData ? treeData.roots : treeData;
  }, [treeData]);
  const organizations = useMemo(
    () => mergeSubunits(rawOrganizations, subunitsByParentId),
    [rawOrganizations, subunitsByParentId]
  );
  const selectedOrg = useMemo(
    () => findOrganization(organizations, selectedOrgId),
    [organizations, selectedOrgId]
  );

  const handleOrganizationSearch = useCallback(
    async (query: string) => {
      const trimmedQuery = query.trim();
      searchControllerRef.current?.abort();
      const requestId = ++searchRequestIdRef.current;
      if (trimmedQuery.length < 2) {
        setSearchResults([]);
        setSearchLoading(false);
        setSearchError(null);
        setResultsLimited(false);
        return;
      }

      const controller = new AbortController();
      searchControllerRef.current = controller;
      setSearchLoading(true);
      setSearchError(null);
      try {
        const response = await fetch(
          `/api/user-service/organizations/search?q=${encodeURIComponent(trimmedQuery)}&max_results=100`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error("organization-search-failed");
        const data = (await response.json()) as {
          results?: OrganizationNode[];
        };
        if (
          controller.signal.aborted ||
          requestId !== searchRequestIdRef.current
        ) {
          return;
        }
        const results = Array.isArray(data.results) ? data.results : [];
        setSearchResults(results);
        setResultsLimited(results.length === 100);
      } catch {
        if (
          controller.signal.aborted ||
          requestId !== searchRequestIdRef.current
        ) {
          return;
        }
        setSearchError(t("admin.organizations.tree.searchFailed"));
      } finally {
        if (requestId === searchRequestIdRef.current) {
          setSearchLoading(false);
        }
      }
    },
    [t]
  );

  useEffect(
    () => () => {
      searchControllerRef.current?.abort();
    },
    []
  );
  const membersKey = selectedOrg
    ? `/api/user-service/organizations/${selectedOrg.id}/users`
    : null;
  const { data: membersData } = useSWR<{
    users: OrganizationMember[];
    count: number;
  }>(membersKey, fetchJson);
  const members = membersData?.users ?? [];
  const {
    data: allMembersData,
    error: allMembersError,
    isLoading: allMembersLoading,
  } = useSWR<{
    members_by_organization: OrganizationMembersByUnit;
    count: number;
  }>(null, fetchJson);
  const membersByOrganizationId = useMemo(() => {
    const base = allMembersData?.members_by_organization ?? {};
    const merged: OrganizationMembersByUnit = { ...base, ...unitMembersMap };
    if (selectedOrg && members.length > 0 && !merged[selectedOrg.id]) {
      merged[selectedOrg.id] = members;
    }
    return merged;
  }, [allMembersData, unitMembersMap, selectedOrg, members]);

  const handleExpandOrg = useCallback(
    async (orgId: string) => {
      const promises: Promise<void>[] = [];

      if (!subunitsByParentId[orgId]) {
        promises.push(
          fetch(`/api/user-service/organizations/${orgId}/children`)
            .then(async (res) => {
              if (res.ok) {
                const data = await res.json();
                if (data?.children) {
                  setSubunitsByParentId((prev) => ({
                    ...prev,
                    [orgId]: data.children,
                  }));
                }
              }
            })
            .catch(() => {})
        );
      }

      if (showMembers && !unitMembersMap[orgId]) {
        promises.push(
          fetch(`/api/user-service/organizations/${orgId}/users`)
            .then(async (res) => {
              if (res.ok) {
                const data = await res.json();
                if (data?.users) {
                  setUnitMembersMap((prev) => ({
                    ...prev,
                    [orgId]: data.users,
                  }));
                }
              }
            })
            .catch(() => {})
        );
      }

      if (promises.length > 0) {
        await Promise.all(promises);
      }
    },
    [showMembers, subunitsByParentId, unitMembersMap]
  );
  const capabilityKey = selectedOrg
    ? `/api/user-service/organizations/${selectedOrg.id}/management-capability`
    : null;
  const { data: capability, isLoading: capabilityLoading } = useSWR<{
    editable: boolean;
  }>(capabilityKey, fetchJson);
  const editable = capability?.editable === true;

  useEffect(() => {
    window.sessionStorage.setItem(
      SHOW_MEMBERS_STORAGE_KEY,
      String(showMembers)
    );
    if (showMembers) {
      rawOrganizations.forEach((org) => {
        void handleExpandOrg(org.id);
      });
    }
  }, [showMembers, rawOrganizations, handleExpandOrg]);

  useEffect(() => {
    if (allMembersError) {
      toast.error(t("admin.organizations.notifications.membersLoadFailed"));
    }
  }, [allMembersError, t]);

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

  const handleRevealResult = useCallback(
    async (surface: SearchSurface, result: OrganizationNode) => {
      setRevealLoading(true);
      setSearchError(null);
      try {
        const ancestorsResponse = await fetch(
          `/api/user-service/organizations/${result.id}/ancestors`
        );
        if (!ancestorsResponse.ok) throw new Error("reveal-failed");
        const ancestorsData = (await ancestorsResponse.json()) as {
          ancestors?: OrganizationNode[];
        };
        const ancestors = Array.isArray(ancestorsData.ancestors)
          ? ancestorsData.ancestors.filter(
              (ancestor) => ancestor.id !== result.id
            )
          : [];
        setSubunitsByParentId((current) => {
          const next = { ...current };
          let nestedChild = result;
          [...ancestors].reverse().forEach((ancestor) => {
            next[ancestor.id] = mergeOrganizationsById(
              current[ancestor.id] ?? [],
              [nestedChild]
            );
            nestedChild = {
              ...ancestor,
              children: mergeOrganizationsById(
                ancestor.children ?? [],
                [nestedChild]
              ),
              has_children: true,
            };
          });
          return next;
        });
        setPendingReveal({
          id: ++revealRequestIdRef.current,
          surface,
          result,
          ancestorIds: ancestors.map(({ id }) => id),
        });
      } catch (error) {
        const message = t("admin.organizations.tree.revealFailed");
        setSearchError(message);
        toast.error(message);
        if (error instanceof Error && error.message === "missing-target") {
          setSearchResults((current) =>
            current.filter(({ id }) => id !== result.id)
          );
        }
        setRevealLoading(false);
      }
    },
    [t]
  );

  const handleRevealReady = useCallback(
    (organization: OrganizationNode) => {
      handleSelectOrg(organization);
      setRevealLoading(false);
    },
    [handleSelectOrg]
  );

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
          await responseDetail(
            response,
            t("admin.organizations.notifications.createFailed")
          )
        );
        return;
      }
      await refreshOrganizationsAndLayout();
      toast.success(t("admin.organizations.notifications.created"));
    },
    [refreshOrganizationsAndLayout, t]
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
          await responseDetail(
            response,
            t("admin.organizations.notifications.updateFailed")
          )
        );
        return;
      }
      await refreshOrganizations();
    },
    [refreshOrganizations, t]
  );

  const handleDeleteOrg = useCallback(
    async (id: string) => {
      const response = await fetch(`/api/user-service/organizations/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        toast.error(
          await responseDetail(
            response,
            t("admin.organizations.notifications.deleteFailed")
          )
        );
        return;
      }
      await refreshOrganizationsAndLayout();
      if (selectedOrgId === id) setSelectedOrgId(null);
    },
    [refreshOrganizationsAndLayout, selectedOrgId, t]
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
          await responseDetail(
            response,
            t("admin.organizations.notifications.moveFailed")
          )
        );
        return false;
      }
      await refreshOrganizationsAndLayout();
      toast.success(t("admin.organizations.notifications.moved"));
      return true;
    },
    [refreshOrganizationsAndLayout, t]
  );

  async function refreshMembers() {
    if (membersKey) await mutate(membersKey);
    if (showMembers) await mutate(ORGANIZATION_MEMBERS_KEY);
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
        await responseDetail(
          response,
          t("admin.organizations.notifications.memberAddFailed")
        )
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
        await responseDetail(
          response,
          t("admin.organizations.notifications.memberRoleUpdateFailed")
        )
      );
      return;
    }
    await refreshMembers();
    toast.success(t("admin.organizations.notifications.memberRoleUpdated"));
  }

  async function handleRemoveUser(userId: string) {
    if (
      !selectedOrg ||
      !confirm(t("admin.organizations.notifications.memberRemoveConfirm"))
    )
      return;
    const response = await fetch(
      `/api/user-service/organizations/${selectedOrg.id}/users/${userId}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      toast.error(
        await responseDetail(
          response,
          t("admin.organizations.notifications.memberRemoveFailed")
        )
      );
      return;
    }
    await refreshMembers();
  }

  if (isLoading) {
    return (
      <div className={cn("flex h-screen items-center justify-center")}>
        <Text text03>{t("admin.organizations.page.loading")}</Text>
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
          showMembers={showMembers}
          membersByOrganizationId={membersByOrganizationId}
          onShowMembersChange={setShowMembers}
          membersLoading={allMembersLoading}
          onExpandOrg={handleExpandOrg}
          searchResults={searchResults}
          searchLoading={searchLoading}
          searchError={searchError}
          resultsLimited={resultsLimited}
          revealLoading={revealLoading}
          onSearch={handleOrganizationSearch}
          onRevealResult={(result) => void handleRevealResult("tree", result)}
          revealRequest={
            pendingReveal?.surface === "tree" ? pendingReveal : null
          }
          onRevealReady={handleRevealReady}
        />
      </aside>

      <div
        role="separator"
        aria-label={t("admin.organizations.page.resizeTree")}
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
                  </div>
                </div>
                <div className={cn("flex gap-6")}>
                  <div className={cn("text-right")}>
                    <Text figureSmallValue text04 as="p">
                      {members.length}
                    </Text>
                    <Text figureSmallLabel text03>
                      {t("admin.organizations.page.activeMembers")}
                    </Text>
                  </div>
                  <div className={cn("text-right")}>
                    <Text figureSmallValue text04 as="p">
                      {selectedOrg.permission_count ?? 0}
                    </Text>
                    <Text figureSmallLabel text03>
                      {t("admin.organizations.page.directGrants")}
                    </Text>
                  </div>
                </div>
              </div>
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <Tabs.List
                  variant="pill"
                  className={cn(
                    "bg-background-neutral-02",
                    "[&_[data-state=active]]:bg-background-neutral-04",
                    "[&_[data-state=active]]:text-text-05"
                  )}
                >
                  <Tabs.Trigger value="users" icon={SvgUsers}>
                    {t("admin.organizations.page.usersTab")}
                  </Tabs.Trigger>
                  <Tabs.Trigger value="agents">
                    {t("admin.organizations.access.agents")}
                  </Tabs.Trigger>
                  <Tabs.Trigger value="collections">
                    {t("admin.organizations.access.collections")}
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
                  resourceType={
                    activeTab === "agents" ? "agent" : "rag_collection"
                  }
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
              {t("admin.organizations.page.selectTitle")}
            </Text>
            <Text text03 as="p">
              {t("admin.organizations.page.selectDescription")}
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
          showMembers={showMembers}
          membersByOrganizationId={membersByOrganizationId}
          onShowMembersChange={setShowMembers}
          membersLoading={allMembersLoading}
          onExpandOrg={handleExpandOrg}
          searchResults={searchResults}
          searchLoading={searchLoading}
          searchError={searchError}
          resultsLimited={resultsLimited}
          revealLoading={revealLoading}
          onSearch={handleOrganizationSearch}
          onRevealResult={(result) =>
            void handleRevealResult("designer", result)
          }
          revealRequest={
            pendingReveal?.surface === "designer" ? pendingReveal : null
          }
          onRevealReady={handleRevealReady}
        />
      )}
    </main>
  );
}
