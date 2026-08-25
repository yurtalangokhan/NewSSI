"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import LineItem from "@/refresh-components/buttons/LineItem";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import Modal from "@/refresh-components/Modal";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Tabs from "@/refresh-components/Tabs";
import Text from "@/refresh-components/texts/Text";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { cn } from "@/lib/utils";
import { toast } from "@/hooks/useToast";
import {
  SvgCheck,
  SvgEdit,
  SvgPlus,
  SvgRefreshCw,
  SvgShield,
  SvgTrash,
} from "@opal/icons";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n/config";
import { useUser } from "@/providers/UserProvider";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { formatRoleName } from "@/lib/auth/roles";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.ROLES]!;

// ─── Types ─────────────────────────────────────────────────────────

interface Permission {
  name: string;
  label: string;
  description: string | null;
  entity: string;
  service: string;
  action: string;
  feature: string | null;
  is_system: boolean;
}

interface CompositeRole {
  name: string;
  description: string | null;
  permissions: string[];
  role_ids: string[];
  is_builtin: boolean;
  is_admin: boolean;
}

interface CoarseRole {
  name: string;
  description: string | null;
  service_client: string;
  permissions: string[];
}

// ─── Feature taxonomy ───────────────────────────────────────────────

const FEATURE_LABEL_FALLBACKS: Record<string, string> = {
  access: "Users & Access",
  agents: "Agents & Assistants",
  chat: "Chat & Conversations",
  knowledge: "Knowledge & RAG",
  tools: "Tools & Integrations",
  workspace: "Workspace & Projects",
  system: "System Administration",
};

const FEATURE_ORDER = [
  "access",
  "agents",
  "chat",
  "knowledge",
  "tools",
  "workspace",
  "system",
];

function featureLabel(
  feature: string,
  translate: (key: string, options?: Record<string, string>) => string
): string {
  return translate(`features.${feature}`, {
    defaultValue:
      FEATURE_LABEL_FALLBACKS[feature] ?? feature.replace(/_/g, " "),
  });
}

// ─── Helpers ────────────────────────────────────────────────────────

function roleLabel(name: string) {
  return formatRoleName(name);
}

function coarseRoleLabel(name: string) {
  return formatRoleName(name);
}

function rolePath(name: string) {
  return encodeURIComponent(name);
}

function groupByFeature(
  permissions: Permission[]
): Record<string, Record<string, Permission[]>> {
  const grouped: Record<string, Record<string, Permission[]>> = {};
  for (const perm of permissions) {
    const feature = perm.feature ?? "system";
    let entities = grouped[feature];
    if (!entities) {
      entities = {};
      grouped[feature] = entities;
    }
    let list = entities[perm.entity];
    if (!list) {
      list = [];
      entities[perm.entity] = list;
    }
    list.push(perm);
  }
  for (const feature of Object.keys(grouped)) {
    const entities = grouped[feature];
    if (!entities) continue;
    const sorted: Record<string, Permission[]> = {};
    for (const entity of Object.keys(entities).sort()) {
      const perms = entities[entity];
      if (perms) sorted[entity] = perms;
    }
    grouped[feature] = sorted;
  }
  return grouped;
}

function orderedFeatures(
  grouped: Record<string, Record<string, Permission[]>>
): string[] {
  const known = FEATURE_ORDER.filter((feature) => grouped[feature]);
  const unknown = Object.keys(grouped).filter(
    (feature) => !FEATURE_ORDER.includes(feature)
  );
  return [...known, ...unknown];
}

function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-6 text-center">
      <Text headingH3 text05 className="block">
        {title}
      </Text>
      <Text secondaryBody text04 className="mt-2 block">
        {description}
      </Text>
    </div>
  );
}

// ─── API helpers ────────────────────────────────────────────────────

async function putPermissions(
  url: string,
  { arg }: { arg: { permissions: string[] } }
) {
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: i18n.t("admin.rolesPage.saveFailedGeneric") }));
    throw new Error(
      err.detail || i18n.t("admin.rolesPage.savePermissionsFailed")
    );
  }
  return res.json();
}

async function putRoleIds(
  url: string,
  { arg }: { arg: { role_ids: string[] } }
) {
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: i18n.t("admin.rolesPage.saveFailedGeneric") }));
    throw new Error(
      err.detail || i18n.t("admin.rolesPage.saveRoleAssignmentFailed")
    );
  }
  return res.json();
}

async function postSync(_url: string) {
  const res = await fetch("/api/user-service/roles/sync-keycloak", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: i18n.t("admin.rolesPage.syncFailedGeneric") }));
    throw new Error(
      err.detail || i18n.t("admin.rolesPage.syncToKeycloakFailed")
    );
  }
  return res.json();
}

async function postCreateCompositeRole(
  _url: string,
  { arg }: { arg: { name: string; description: string } }
) {
  const params = new URLSearchParams({ name: arg.name });
  if (arg.description) params.set("description", arg.description);
  const res = await fetch(`/api/user-service/roles/?${params}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: i18n.t("admin.rolesPage.createFailedGeneric") }));
    throw new Error(
      err.detail || i18n.t("admin.rolesPage.createCompositeRoleFailed")
    );
  }
  return res.json();
}

async function patchRole(
  url: string,
  { arg }: { arg: Record<string, string> }
) {
  const params = new URLSearchParams(arg);
  const res = await fetch(`${url}?${params}`, {
    method: "PATCH",
  });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: i18n.t("admin.rolesPage.updateFailedGeneric") }));
    throw new Error(err.detail || i18n.t("admin.rolesPage.updateRoleFailed"));
  }
  return res.json();
}

async function deleteRole(url: string) {
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: i18n.t("admin.rolesPage.deleteFailedGeneric") }));
    throw new Error(err.detail || i18n.t("admin.rolesPage.deleteRoleFailed"));
  }
  return res.json();
}

// ─── Skeletons ──────────────────────────────────────────────────────

function RoleCardSkeleton() {
  return (
    <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2.5">
          <div className="h-5 w-40 rounded-06 bg-background-neutral-03 animate-pulse" />
          <div className="h-4 w-72 rounded-06 bg-background-neutral-02 animate-pulse" />
          <div className="h-3.5 w-48 rounded-06 bg-background-neutral-02 animate-pulse" />
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <div className="h-8 w-20 rounded-08 bg-background-neutral-02 animate-pulse" />
          <div className="h-8 w-16 rounded-08 bg-background-neutral-02 animate-pulse" />
        </div>
      </div>
    </div>
  );
}

function RoleBundlesSkeleton() {
  return (
    <Card className="rounded-08">
      <CardHeader className="space-y-2">
        <div className="h-4 w-44 rounded-06 bg-background-neutral-03 animate-pulse" />
        <div className="h-3 w-80 rounded-06 bg-background-neutral-02 animate-pulse" />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="h-8 w-full rounded-06 bg-background-neutral-02 animate-pulse" />
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center gap-2.5 rounded-06 border border-border-01/50 bg-background-neutral-01 p-3"
            >
              <div className="h-4 w-4 shrink-0 rounded-04 bg-background-neutral-03 animate-pulse" />
              <div className="flex flex-1 flex-col gap-1 min-w-0">
                <div className="h-3.5 w-2/3 rounded bg-background-neutral-03 animate-pulse" />
                <div className="h-2.5 w-1/3 rounded bg-background-neutral-02 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function RolesPageSkeleton() {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-2">
          <div className="h-6 w-48 rounded-06 bg-background-neutral-03 animate-pulse" />
          <div className="h-4 w-96 rounded-06 bg-background-neutral-02 animate-pulse" />
        </div>
        <div className="flex items-center gap-2">
          <div className="h-8 w-24 rounded-08 bg-background-neutral-02 animate-pulse" />
          <div className="h-8 w-20 rounded-08 bg-background-neutral-02 animate-pulse" />
        </div>
      </div>

      {/* Tabs */}
      <div className="h-9 w-64 rounded-08 bg-background-neutral-02 animate-pulse" />

      {/* Main Grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        {/* Left Sidebar Skeleton */}
        <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-3 space-y-3">
          <div className="h-8 w-full rounded-06 bg-background-neutral-02 animate-pulse" />
          <div className="space-y-1.5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="flex h-10 w-full items-center justify-between rounded-08 bg-background-neutral-02/60 px-3"
              >
                <div className="h-3.5 w-24 rounded bg-background-neutral-03 animate-pulse" />
                <div className="h-3 w-8 rounded bg-background-neutral-03 animate-pulse" />
              </div>
            ))}
          </div>
        </div>

        {/* Right Panel Skeleton */}
        <div className="min-w-0 space-y-4">
          <RoleCardSkeleton />
          <RoleBundlesSkeleton />
        </div>
      </div>
    </div>
  );
}

function CreateCompositeRoleModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin.rolesPage" });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const reset = () => {
    setName("");
    setDescription("");
    setError(null);
  };

  const handleClose = () => {
    if (loading) return;
    reset();
    onClose();
  };

  const handleCreate = async () => {
    const nextName = name.trim();
    if (!nextName) {
      setError(t("compositeRoleNameRequired"));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await postCreateCompositeRole("", {
        arg: {
          name: nextName,
          description: description.trim(),
        },
      });
      onCreated(nextName);
      reset();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("unknownError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={handleClose}>
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgShield}
          title={t("createCompositeRoleTitle")}
          description={t("createCompositeRoleDescription", {
            defaultValue:
              "Create a composite role profile to bundle permissions and service roles.",
          })}
          onClose={handleClose}
        />
        <Modal.Body twoTone>
          {error && (
            <div className="mb-4 rounded-06 border border-status-danger-02 bg-background-danger-02 p-3">
              <Text secondaryBody text03 className="text-status-danger-05">
                {error}
              </Text>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleCreate();
            }}
            className="flex w-full flex-col gap-4"
          >
            <div className="flex w-full flex-col gap-1.5">
              <Text headingH3 text05 className="text-sm font-medium">
                {t("compositeRoleNameLabel")}
              </Text>
              <Text secondaryBody text04 className="text-xs">
                {t("compositeRoleNameDescription", {
                  defaultValue:
                    "Unique identifier for this role (e.g. analyst, data-scientist).",
                })}
              </Text>
              <InputTypeIn
                autoFocus
                showClearButton
                className="w-full"
                placeholder={t("compositeRoleNamePlaceholder")}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (error) setError(null);
                }}
              />
            </div>

            <div className="flex w-full flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <Text headingH3 text05 className="text-sm font-medium">
                  {t("descriptionLabel")}
                </Text>
                <Text secondaryBody text03 className="text-xs">
                  {t("optionalParenthetical", {
                    defaultValue: "(İsteğe bağlı)",
                  })}
                </Text>
              </div>
              <Text secondaryBody text04 className="text-xs">
                {t("compositeRoleDescriptionHelper", {
                  defaultValue:
                    "Summary of the access and responsibilities granted by this role.",
                })}
              </Text>
              <InputTextArea
                rows={3}
                className="w-full"
                placeholder={t("optionalDescriptionPlaceholder")}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </form>
        </Modal.Body>
        <Modal.Footer>
          <Button secondary onClick={handleClose} disabled={loading}>
            {t("cancelButton")}
          </Button>
          <Button
            action
            onClick={handleCreate}
            disabled={loading || !name.trim()}
          >
            {loading ? t("creatingButton") : t("createCompositeRoleTitle")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}

// ─── Roles Manager ──────────────────────────────────────────────────

function RolesManager() {
  const { t } = useTranslation("common", { keyPrefix: "admin.rolesPage" });
  const { hasPermission } = useUser();
  const canManageRoles = hasPermission("role:manage");
  const [activeLayer, setActiveLayer] = useState<"composite" | "coarse">(
    "composite"
  );
  const [selectedRole, setSelectedRole] = useState<string>("");
  const [selectedCoarseRole, setSelectedCoarseRole] = useState<string>("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [roleSearch, setRoleSearch] = useState("");
  const [coarseRoleSearch, setCoarseRoleSearch] = useState("");
  const [permSearch, setPermSearch] = useState("");
  const [includedSearch, setIncludedSearch] = useState("");
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [deleteConfirmRole, setDeleteConfirmRole] = useState<string | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const permSearchRef = useRef<HTMLInputElement>(null);

  const {
    data: compData,
    isLoading: compLoading,
    mutate: mutateComp,
  } = useSWR<{
    composite_roles: CompositeRole[];
  }>("/api/user-service/roles/", errorHandlingFetcher, {
    dedupingInterval: 30000,
  });

  const {
    data: coarseData,
    isLoading: coarseLoading,
    mutate: mutateCoarseData,
  } = useSWR<{
    roles: CoarseRole[];
  }>("/api/user-service/coarse-roles/", errorHandlingFetcher, {
    dedupingInterval: 30000,
  });

  const { data: permsData, isLoading: permsLoading } = useSWR<{
    permissions: Permission[];
  }>("/api/user-service/permissions/", errorHandlingFetcher, {
    dedupingInterval: 30000,
  });

  const {
    data: rolePermsData,
    isLoading: rolePermsLoading,
    mutate: mutateRolePerms,
  } = useSWR<{ name: string; permissions: string[] }>(
    selectedRole
      ? `/api/user-service/roles/${rolePath(selectedRole)}/permissions`
      : null,
    errorHandlingFetcher,
    { dedupingInterval: 5000 }
  );

  const {
    data: roleIdsData,
    mutate: mutateRoleIds,
    isLoading: roleIdsLoading,
  } = useSWR<{ name: string; role_ids: string[] }>(
    selectedRole
      ? `/api/user-service/roles/${rolePath(selectedRole)}/role-ids`
      : null,
    errorHandlingFetcher,
    { dedupingInterval: 5000 }
  );

  const {
    data: coarseRolePermsData,
    mutate: mutateCoarseRolePerms,
    isLoading: coarseRolePermsLoading,
  } = useSWR<{ name: string; permissions: string[] }>(
    selectedCoarseRole
      ? `/api/user-service/coarse-roles/${rolePath(
          selectedCoarseRole
        )}/permissions`
      : null,
    errorHandlingFetcher,
    { dedupingInterval: 5000 }
  );

  const { trigger: saveCoarsePermissions, isMutating: isSaving } =
    useSWRMutation(
      selectedCoarseRole
        ? `/api/user-service/coarse-roles/${rolePath(
            selectedCoarseRole
          )}/permissions`
        : null,
      putPermissions,
      {
        onSuccess: () => {
          mutateCoarseRolePerms();
          mutateCoarseData();
          toast.success(t("permissionsSavedToast"));
        },
        onError: (err) => toast.error(err.message),
      }
    );

  const { trigger: saveRoleIds, isMutating: isSavingRoleIds } = useSWRMutation(
    selectedRole
      ? `/api/user-service/roles/${rolePath(selectedRole)}/role-ids`
      : null,
    putRoleIds,
    {
      onSuccess: (data) => {
        mutateRoleIds();
        mutateRolePerms();
        mutateComp();
        toast.success(
          t("roleAssignmentSavedToast", {
            count: data.effective_permissions?.length ?? 0,
          })
        );
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const { trigger: syncToKeycloak, isMutating: isSyncing } = useSWRMutation(
    "/api/user-service/roles/sync-keycloak",
    postSync,
    {
      onSuccess: () => toast.success(t("syncedToKeycloakToast")),
      onError: (err) => toast.error(err.message),
    }
  );

  const roles = useMemo(() => compData?.composite_roles ?? [], [compData]);

  const selectedComp = useMemo(
    () => roles.find((role) => role.name === selectedRole) ?? null,
    [roles, selectedRole]
  );

  const coarseRoles = useMemo(() => coarseData?.roles ?? [], [coarseData]);

  const selectedCoarse = useMemo(
    () => coarseRoles.find((role) => role.name === selectedCoarseRole) ?? null,
    [coarseRoles, selectedCoarseRole]
  );

  const isBuiltin = selectedComp?.is_builtin ?? false;
  const effectivePermissions = rolePermsData?.permissions ?? [];
  const isWildcard = effectivePermissions.includes("*");
  const selectedCoarseIsWildcard =
    selectedCoarse?.permissions?.includes("*") ||
    coarseRolePermsData?.permissions?.includes("*") ||
    false;
  const canMutate = canManageRoles && !isBuiltin;
  const canMutateCoarse =
    canManageRoles && Boolean(selectedCoarseRole) && !selectedCoarseIsWildcard;

  useEffect(() => {
    if (roles.length === 0) {
      setSelectedRole("");
      return;
    }
    if (!roles.some((role) => role.name === selectedRole)) {
      setSelectedRole(roles[0]?.name ?? "");
    }
  }, [roles, selectedRole]);

  useEffect(() => {
    if (coarseRoles.length === 0) {
      setSelectedCoarseRole("");
      return;
    }
    if (!coarseRoles.some((role) => role.name === selectedCoarseRole)) {
      setSelectedCoarseRole(coarseRoles[0]?.name ?? "");
    }
  }, [coarseRoles, selectedCoarseRole]);

  const filteredRoles = useMemo(() => {
    if (!roleSearch.trim()) return roles;
    const q = roleSearch.toLowerCase();
    return roles.filter(
      (role) =>
        role.name.toLowerCase().includes(q) ||
        roleLabel(role.name).toLowerCase().includes(q)
    );
  }, [roles, roleSearch]);

  const filteredCoarseRoles = useMemo(() => {
    if (!coarseRoleSearch.trim()) return coarseRoles;
    const q = coarseRoleSearch.toLowerCase();
    return coarseRoles.filter(
      (role) =>
        role.name.toLowerCase().includes(q) ||
        coarseRoleLabel(role.name).toLowerCase().includes(q) ||
        (role.description ?? "").toLowerCase().includes(q)
    );
  }, [coarseRoles, coarseRoleSearch]);

  const groupedPermissions = useMemo(
    () => groupByFeature(permsData?.permissions ?? []),
    [permsData]
  );

  const filteredGrouped = useMemo(() => {
    if (!permSearch.trim()) return groupedPermissions;
    const q = permSearch.toLowerCase();
    const result: Record<string, Record<string, Permission[]>> = {};
    for (const [feature, entities] of Object.entries(groupedPermissions)) {
      const filteredEntities: Record<string, Permission[]> = {};
      for (const [entity, perms] of Object.entries(entities)) {
        const filtered = perms.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.label.toLowerCase().includes(q) ||
            p.action.toLowerCase().includes(q) ||
            entity.toLowerCase().includes(q) ||
            featureLabel(feature, t).toLowerCase().includes(q)
        );
        if (filtered.length > 0) filteredEntities[entity] = filtered;
      }
      if (Object.keys(filteredEntities).length > 0)
        result[feature] = filteredEntities;
    }
    return result;
  }, [groupedPermissions, permSearch, t]);

  const catalogNames = useMemo(() => {
    return new Set((permsData?.permissions ?? []).map((perm) => perm.name));
  }, [permsData]);

  const selectedPermsSet = useMemo(() => {
    const permissions = coarseRolePermsData?.permissions ?? [];
    if (permissions.includes("*")) {
      return new Set((permsData?.permissions ?? []).map((perm) => perm.name));
    }
    return new Set(permissions);
  }, [coarseRolePermsData, permsData]);

  const selectedRoleIds = useMemo(
    () => new Set(roleIdsData?.role_ids ?? []),
    [roleIdsData]
  );

  const includedCoarseRoles = useMemo(() => {
    const q = includedSearch.trim().toLowerCase();
    const pool = coarseRoles;
    const filtered = q
      ? pool.filter((role) => role.name.toLowerCase().includes(q))
      : pool;
    return filtered;
  }, [coarseRoles, includedSearch]);

  const handleToggle = useCallback(
    (name: string) => {
      if (!canMutateCoarse) return;
      mutateCoarseRolePerms(
        (prev) => {
          const perms = prev?.permissions ?? [];
          if (perms.includes(name)) {
            return {
              name: selectedCoarseRole,
              permissions: perms.filter((p) => p !== name),
            };
          }
          return { name: selectedCoarseRole, permissions: [...perms, name] };
        },
        { revalidate: false }
      );
    },
    [canMutateCoarse, mutateCoarseRolePerms, selectedCoarseRole]
  );

  const handleSelectAll = useCallback(
    (perms: Permission[], checked: boolean) => {
      if (!canMutateCoarse) return;
      mutateCoarseRolePerms(
        (prev) => {
          const current = new Set(prev?.permissions ?? []);
          for (const p of perms) {
            if (checked) current.add(p.name);
            else current.delete(p.name);
          }
          return { name: selectedCoarseRole, permissions: Array.from(current) };
        },
        { revalidate: false }
      );
    },
    [canMutateCoarse, mutateCoarseRolePerms, selectedCoarseRole]
  );

  const [isUpdatingDescription, setIsUpdatingDescription] = useState(false);

  const handleSave = useCallback(() => {
    saveCoarsePermissions({
      permissions: Array.from(selectedPermsSet).filter((permission) =>
        catalogNames.has(permission)
      ),
    });
  }, [catalogNames, selectedPermsSet, saveCoarsePermissions]);

  const handleToggleRole = useCallback(
    (roleName: string) => {
      if (!canMutate || !selectedRole) return;
      const current = new Set(roleIdsData?.role_ids ?? []);
      if (current.has(roleName)) current.delete(roleName);
      else current.add(roleName);
      saveRoleIds({ role_ids: Array.from(current) });
    },
    [canMutate, selectedRole, roleIdsData, saveRoleIds]
  );

  const handleUpdateDescription = useCallback(
    async (description: string) => {
      setIsUpdatingDescription(true);
      try {
        await patchRole(`/api/user-service/roles/${rolePath(selectedRole)}`, {
          arg: { description },
        });
        mutateComp();
        toast.success(t("roleUpdatedToast"));
        setEditingDescription(false);
      } catch (err: any) {
        toast.error(err.message);
      } finally {
        setIsUpdatingDescription(false);
      }
    },
    [selectedRole, mutateComp, t]
  );

  const handleDeleteRole = useCallback(async () => {
    if (!deleteConfirmRole) return;
    setIsDeleting(true);
    try {
      await deleteRole(
        `/api/user-service/roles/${rolePath(deleteConfirmRole)}`
      );
      mutateComp();
      if (deleteConfirmRole === selectedRole) {
        const remaining = roles.filter(
          (role) => role.name !== deleteConfirmRole
        );
        setSelectedRole(remaining[0]?.name ?? "");
      }
      setDeleteConfirmRole(null);
      toast.success(t("roleDeletedToast"));
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setIsDeleting(false);
    }
  }, [deleteConfirmRole, selectedRole, roles, mutateComp, t]);

  const isInitialLoading = compLoading || coarseLoading || permsLoading;

  if (isInitialLoading) {
    return <RolesPageSkeleton />;
  }

  const isRightPanelLoading =
    activeLayer === "composite"
      ? Boolean(selectedRole) && (rolePermsLoading || roleIdsLoading)
      : Boolean(selectedCoarseRole) && coarseRolePermsLoading;

  const hasRoles = roles.length > 0;
  const hasCoarseRoles = coarseRoles.length > 0;
  const hasActiveItems =
    activeLayer === "composite" ? hasRoles : hasCoarseRoles;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <Text headingH3 text05 className="block">
            {t("roleManagementTitle")}
          </Text>
          <Text secondaryBody text04 className="mt-1 block">
            {t("roleManagementDescription")}
          </Text>
        </div>
        <div className="flex items-center gap-2">
          {canManageRoles && (
            <Button
              leftIcon={SvgPlus}
              secondary
              onClick={() => setCreateModalOpen(true)}
            >
              {t("newRoleButton")}
            </Button>
          )}
          <Button
            leftIcon={SvgRefreshCw}
            secondary
            disabled={isSyncing || !canManageRoles}
            onClick={() => syncToKeycloak()}
          >
            {isSyncing ? t("syncingButton") : t("syncButton")}
          </Button>
        </div>
      </div>

      <Tabs
        value={activeLayer}
        onValueChange={(val) => setActiveLayer(val as "composite" | "coarse")}
      >
        <Tabs.List variant="contained">
          <Tabs.Trigger value="composite">
            {t("compositeRolesTabLabel")}
          </Tabs.Trigger>
          <Tabs.Trigger value="coarse">
            {t("featureBundlesTabLabel")}
          </Tabs.Trigger>
        </Tabs.List>
      </Tabs>

      {!hasActiveItems ? (
        <EmptyState
          title={
            activeLayer === "composite"
              ? t("noRolesFoundTitle")
              : t("noFeatureBundlesFoundTitle")
          }
          description={
            activeLayer === "composite"
              ? t("noRolesFoundDescription")
              : t("noFeatureBundlesFoundDescription")
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-3">
            <div className="relative mb-2">
              <InputTypeIn
                leftSearchIcon
                placeholder={
                  activeLayer === "composite"
                    ? t("searchRolesPlaceholder")
                    : t("searchFeatureBundlesPlaceholder")
                }
                value={
                  activeLayer === "composite" ? roleSearch : coarseRoleSearch
                }
                onChange={(e) =>
                  activeLayer === "composite"
                    ? setRoleSearch(e.target.value)
                    : setCoarseRoleSearch(e.target.value)
                }
              />
            </div>
            <div className="flex flex-col gap-1">
              {activeLayer === "composite" &&
                filteredRoles.map((role) => {
                  const selected = selectedRole === role.name;
                  const isAll = (role.permissions ?? []).includes("*");
                  return (
                    <LineItem
                      key={role.name}
                      onClick={() => setSelectedRole(role.name)}
                      selected={selected}
                      emphasized={selected}
                      rightChildren={selected ? <SvgCheck size={14} /> : null}
                    >
                      <span className="min-w-0">
                        <span className="flex items-center gap-2">
                          <Text
                            secondaryBody
                            as="span"
                            className="block truncate"
                          >
                            {roleLabel(role.name)}
                          </Text>
                          {role.is_builtin && (
                            <span className="shrink-0 rounded-04 bg-background-neutral-02 px-1.5 py-0.5 text-[0.65rem] text-text-04">
                              {t("builtInBadge")}
                            </span>
                          )}
                        </span>
                        <Text
                          secondaryBody
                          text04
                          as="span"
                          className="block truncate text-xs"
                        >
                          {isAll
                            ? t("allPermissions")
                            : t("permissionsCount", {
                                count: role.permissions.length,
                              })}
                          {role.role_ids.length > 0 &&
                            t("includedRolesSuffix", {
                              count: role.role_ids.length,
                            })}
                        </Text>
                      </span>
                    </LineItem>
                  );
                })}
              {activeLayer === "coarse" &&
                filteredCoarseRoles.map((role) => {
                  const selected = selectedCoarseRole === role.name;
                  return (
                    <LineItem
                      key={role.name}
                      onClick={() => setSelectedCoarseRole(role.name)}
                      selected={selected}
                      emphasized={selected}
                      rightChildren={selected ? <SvgCheck size={14} /> : null}
                    >
                      <span className="min-w-0">
                        <Text
                          secondaryBody
                          as="span"
                          className="block truncate capitalize"
                        >
                          {coarseRoleLabel(role.name)}
                        </Text>
                        <Text
                          secondaryBody
                          text04
                          as="span"
                          className="block truncate text-xs"
                        >
                          {role.permissions.includes("*")
                            ? t("allPermissions")
                            : t("permissionsCount", {
                                count: role.permissions.length,
                              })}
                        </Text>
                      </span>
                    </LineItem>
                  );
                })}
              {((activeLayer === "composite" && filteredRoles.length === 0) ||
                (activeLayer === "coarse" &&
                  filteredCoarseRoles.length === 0)) && (
                <Text secondaryBody text04 className="px-3 py-2">
                  {t("noRolesMatchSearch", {
                    defaultValue: "No roles match",
                  })}
                </Text>
              )}
            </div>
          </div>

          <div className="min-w-0">
            {isRightPanelLoading ? (
              <div className="space-y-4">
                <RoleCardSkeleton />
                <RoleBundlesSkeleton />
              </div>
            ) : (
              <>
                {activeLayer === "composite" && selectedComp && (
                  <div className="mb-4 rounded-08 border border-border-01 bg-background-neutral-01 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <Text headingH3 text05 className="truncate">
                            {roleLabel(selectedComp.name)}
                          </Text>
                          {isBuiltin && (
                            <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                              {t("builtInBadge")}
                            </span>
                          )}
                        </div>
                        {editingDescription ? (
                          <div className="mt-2 flex items-center gap-2">
                            <InputTypeIn
                              className="min-w-0 flex-1"
                              showClearButton={false}
                              value={descriptionDraft}
                              variant={
                                isUpdatingDescription ? "disabled" : "primary"
                              }
                              onChange={(e) =>
                                setDescriptionDraft(e.target.value)
                              }
                              onKeyDown={(e) => {
                                if (
                                  e.key === "Enter" &&
                                  !isUpdatingDescription
                                ) {
                                  void handleUpdateDescription(
                                    descriptionDraft
                                  );
                                } else if (
                                  e.key === "Escape" &&
                                  !isUpdatingDescription
                                ) {
                                  setEditingDescription(false);
                                }
                              }}
                              autoFocus
                            />
                            <Button
                              secondary
                              size="md"
                              disabled={isUpdatingDescription}
                              onClick={() =>
                                void handleUpdateDescription(descriptionDraft)
                              }
                            >
                              {isUpdatingDescription
                                ? t("savingButton")
                                : t("saveButton")}
                            </Button>
                            <Button
                              secondary
                              size="md"
                              disabled={isUpdatingDescription}
                              onClick={() => setEditingDescription(false)}
                            >
                              {t("cancelButton")}
                            </Button>
                          </div>
                        ) : (
                          <div className="mt-2 flex items-center gap-2">
                            <Text
                              secondaryBody
                              text04
                              className={cn(
                                "min-w-0 truncate px-1 py-0.5",
                                !selectedComp.description &&
                                  "italic text-text-03"
                              )}
                            >
                              {selectedComp.description || t("noDescription")}
                            </Text>
                            {canMutate && (
                              <IconButton
                                icon={SvgEdit}
                                internal
                                className="shrink-0"
                                onClick={() => {
                                  setDescriptionDraft(
                                    selectedComp.description ?? ""
                                  );
                                  setEditingDescription(true);
                                }}
                                tooltip={t("editRoleDescriptionAriaLabel")}
                              />
                            )}
                          </div>
                        )}
                        <Text secondaryBody text04 className="mt-2 block">
                          {isWildcard
                            ? t("roleGrantsEveryPermission")
                            : t("roleEffectivePermissionsSummary", {
                                bundles: selectedRoleIds.size,
                                permissions: effectivePermissions.length,
                              })}
                        </Text>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {isSavingRoleIds && (
                          <div className="flex items-center gap-1.5 text-xs text-text-03">
                            <SimpleLoader className="h-3.5 w-3.5" />
                            <span>{t("savingButton")}</span>
                          </div>
                        )}
                        <Button
                          leftIcon={isSavingRoleIds ? SimpleLoader : SvgCheck}
                          disabled={isSavingRoleIds || !canMutate}
                          onClick={() => {
                            if (selectedRole && roleIdsData?.role_ids) {
                              void saveRoleIds({
                                role_ids: roleIdsData.role_ids,
                              });
                            }
                          }}
                        >
                          {isSavingRoleIds
                            ? t("savingButton")
                            : t("saveButton")}
                        </Button>
                        {canMutate && (
                          <Button
                            leftIcon={SvgTrash}
                            secondary
                            className="text-danger-03"
                            onClick={() =>
                              setDeleteConfirmRole(selectedComp.name)
                            }
                          >
                            {t("deleteButton")}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {selectedComp && (
                  <Card className="mb-4">
                    <CardHeader className="flex flex-row items-center justify-between gap-3">
                      <div>
                        <CardTitle className="text-sm">
                          {t("includedServiceRolesTitle", {
                            defaultValue: "Included service roles",
                          })}
                        </CardTitle>
                        <Text secondaryBody text04 className="mt-1 block">
                          {t("includedServiceRolesDescription", {
                            defaultValue:
                              "Inherited service roles contribute to this role's effective permissions.",
                          })}
                        </Text>
                      </div>
                      <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                        {t("includedServiceRolesSelectedCount", {
                          count: selectedRoleIds.size,
                          defaultValue: "{{count}} selected",
                        })}
                      </span>
                    </CardHeader>
                    <CardContent>
                      <div className="relative mb-3">
                        <InputTypeIn
                          leftSearchIcon
                          placeholder={t("searchIncludedRolesPlaceholder")}
                          value={includedSearch}
                          onChange={(e) => setIncludedSearch(e.target.value)}
                        />
                      </div>
                      {includedCoarseRoles.length === 0 ? (
                        <Text secondaryBody text04>
                          {t("noServiceRolesMatchSearch", {
                            defaultValue: "No service roles match",
                          })}
                        </Text>
                      ) : (
                        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
                          {includedCoarseRoles.map((role) => (
                            <label
                              key={`${role.service_client}:${role.name}`}
                              className={cn(
                                "flex items-center gap-2 rounded-06 px-3 py-2",
                                canMutate
                                  ? "cursor-pointer hover:bg-background-neutral-02"
                                  : ""
                              )}
                            >
                              {canMutate && (
                                <Checkbox
                                  checked={selectedRoleIds.has(role.name)}
                                  disabled={isSavingRoleIds}
                                  onCheckedChange={() =>
                                    handleToggleRole(role.name)
                                  }
                                />
                              )}
                              <span className="min-w-0">
                                <Text
                                  secondaryBody
                                  text02
                                  className="block truncate"
                                >
                                  {role.name}
                                </Text>
                                <Text
                                  secondaryBody
                                  text04
                                  className="block truncate text-xs"
                                >
                                  {t("serviceRolePermissionCount", {
                                    serviceClient: role.service_client,
                                    count: role.permissions.length,
                                    defaultValue:
                                      "{{serviceClient}} · {{count}} permissions",
                                  })}
                                </Text>
                              </span>
                            </label>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {activeLayer === "coarse" && selectedCoarse && (
                  <div className="mb-4 rounded-08 border border-border-01 bg-background-neutral-01 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <Text
                          headingH3
                          text05
                          className="block truncate capitalize"
                        >
                          {coarseRoleLabel(selectedCoarse.name)}
                        </Text>
                        <Text secondaryBody text04 className="mt-2 block">
                          {selectedCoarse.description || t("noDescription")}
                        </Text>
                        <Text secondaryBody text04 className="mt-2 block">
                          {selectedCoarseIsWildcard
                            ? t("allPermissions")
                            : t("permissionsSelectedCount", {
                                count: selectedPermsSet.size,
                              })}
                        </Text>
                      </div>
                      {!selectedCoarseIsWildcard && (
                        <div className="flex shrink-0 items-center gap-2">
                          {isSaving && (
                            <div className="flex items-center gap-1.5 text-xs text-text-03">
                              <SimpleLoader className="h-3.5 w-3.5" />
                              <span>{t("savingButton")}</span>
                            </div>
                          )}
                          <Button
                            leftIcon={isSaving ? SimpleLoader : SvgCheck}
                            disabled={isSaving || !canMutateCoarse}
                            onClick={handleSave}
                          >
                            {isSaving ? t("savingButton") : t("saveButton")}
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeLayer === "composite" ? (
                  <>
                    <div>
                      <Text headingH3 text05 className="mb-2 block">
                        {t("includedFeatureBundlesTitle")}
                      </Text>
                      <Text secondaryBody text04 className="mb-3 block">
                        {t("includedFeatureBundlesDescription")}
                      </Text>
                      <div className="relative mb-3">
                        <InputTypeIn
                          leftSearchIcon
                          placeholder={t("searchFeatureBundlesPlaceholder")}
                          value={includedSearch}
                          onChange={(e) => setIncludedSearch(e.target.value)}
                        />
                      </div>
                      <Card className="rounded-08">
                        <CardContent className="p-4">
                          {includedCoarseRoles.length === 0 ? (
                            <Text secondaryBody text04 className="py-2">
                              {t("noFeatureBundlesAvailable")}
                            </Text>
                          ) : (
                            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
                              {includedCoarseRoles.map((role) => (
                                <label
                                  key={role.name}
                                  className={cn(
                                    "flex items-center gap-2 rounded-06 px-3 py-2",
                                    canMutate
                                      ? "cursor-pointer hover:bg-background-neutral-02"
                                      : ""
                                  )}
                                >
                                  {canMutate && (
                                    <Checkbox
                                      checked={selectedRoleIds.has(role.name)}
                                      disabled={isSavingRoleIds}
                                      onCheckedChange={() =>
                                        handleToggleRole(role.name)
                                      }
                                    />
                                  )}
                                  <span className="min-w-0">
                                    <Text
                                      secondaryBody
                                      text05
                                      className="block truncate capitalize"
                                    >
                                      {coarseRoleLabel(role.name)}
                                    </Text>
                                    <Text
                                      secondaryBody
                                      text04
                                      className="block text-xs"
                                    >
                                      {t("permissionsCount", {
                                        count: role.permissions.length,
                                      })}
                                    </Text>
                                  </span>
                                </label>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </div>

                    <div className="mt-6">
                      <Text headingH3 text05 className="mb-2 block">
                        {t("effectivePermissionsTitle")}
                      </Text>
                      <Text secondaryBody text04 className="mb-3 block">
                        {t("effectivePermissionsDescription")}
                      </Text>
                      {effectivePermissions.length === 0 ? (
                        <Text secondaryBody text04>
                          {t("noEffectivePermissions")}
                        </Text>
                      ) : (
                        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
                          {effectivePermissions.map((permission) => (
                            <div
                              key={permission}
                              className="rounded-06 bg-background-neutral-01 px-3 py-2"
                            >
                              <Text
                                secondaryBody
                                text04
                                className="block truncate font-mono text-xs"
                              >
                                {permission}
                              </Text>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    {selectedCoarseIsWildcard && (
                      <div className="mb-4 rounded-08 border border-border-01 bg-background-neutral-01 p-6">
                        <div className="flex items-center gap-2">
                          <SvgShield size={18} className="text-text-03" />
                          <Text headingH3 text05>
                            {t("allPermissionsGrantedTitle")}
                          </Text>
                        </div>
                        <Text secondaryBody text04 className="mt-2 block">
                          {t("allPermissionsGrantedDescription")}
                        </Text>
                      </div>
                    )}

                    <div className="relative mb-4">
                      <InputTypeIn
                        ref={permSearchRef}
                        leftSearchIcon
                        placeholder={t("searchPermissionsPlaceholder")}
                        value={permSearch}
                        onChange={(e) => setPermSearch(e.target.value)}
                        onClear={() => setPermSearch("")}
                      />
                    </div>

                    {orderedFeatures(filteredGrouped).map((feature) => {
                      const entities = filteredGrouped[feature];
                      if (!entities) return null;
                      const featurePerms = Object.values(entities).flat();
                      const featureSelected = featurePerms.filter((p) =>
                        selectedPermsSet.has(p.name)
                      ).length;
                      const featureAll =
                        featureSelected === featurePerms.length;
                      return (
                        <div key={feature} className="mb-5">
                          <div className="mb-3 flex items-center gap-2">
                            <div className="h-px flex-1 bg-border-01" />
                            {canMutateCoarse && (
                              <Checkbox
                                checked={featureAll}
                                onCheckedChange={(checked) =>
                                  handleSelectAll(featurePerms, !!checked)
                                }
                              />
                            )}
                            <Text headingH3 text05 className="capitalize">
                              {featureLabel(feature, t)}
                            </Text>
                            <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                              {featureSelected}/{featurePerms.length}
                            </span>
                            <div className="h-px flex-1 bg-border-01" />
                          </div>
                          {Object.entries(entities).map(([entity, perms]) => {
                            const selectedCount = perms.filter((p) =>
                              selectedPermsSet.has(p.name)
                            ).length;
                            const allSelected = selectedCount === perms.length;
                            return (
                              <Card key={entity} className="mb-2">
                                <CardHeader className="flex flex-row items-center justify-between">
                                  <div className="flex items-center gap-3">
                                    {canMutateCoarse && (
                                      <Checkbox
                                        checked={allSelected}
                                        onCheckedChange={(checked) =>
                                          handleSelectAll(perms, !!checked)
                                        }
                                      />
                                    )}
                                    <CardTitle className="capitalize text-sm">
                                      {entity.replace(/_/g, " ")}
                                    </CardTitle>
                                    <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                                      {selectedCount}/{perms.length}
                                    </span>
                                  </div>
                                </CardHeader>
                                <CardContent>
                                  <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
                                    {perms.map((perm) => (
                                      <label
                                        key={perm.name}
                                        className={cn(
                                          "flex items-center gap-2 rounded-06 px-2 py-1.5 hover:bg-background-neutral-02",
                                          canMutateCoarse
                                            ? "cursor-pointer"
                                            : ""
                                        )}
                                      >
                                        {canMutateCoarse && (
                                          <Checkbox
                                            checked={selectedPermsSet.has(
                                              perm.name
                                            )}
                                            onCheckedChange={() =>
                                              handleToggle(perm.name)
                                            }
                                          />
                                        )}
                                        <div className="flex min-w-0 flex-col">
                                          <Text
                                            secondaryBody
                                            text02
                                            className="truncate"
                                          >
                                            {perm.label}
                                          </Text>
                                          {perm.description && (
                                            <Text
                                              secondaryBody
                                              text04
                                              className="truncate"
                                            >
                                              {perm.description}
                                            </Text>
                                          )}
                                          <Text
                                            secondaryBody
                                            text04
                                            className="truncate font-mono text-[0.7rem]"
                                          >
                                            {perm.action}
                                          </Text>
                                        </div>
                                      </label>
                                    ))}
                                  </div>
                                </CardContent>
                              </Card>
                            );
                          })}
                        </div>
                      );
                    })}

                    {Object.keys(filteredGrouped).length === 0 && (
                      <div className="py-8 text-center">
                        <Text secondaryBody text03>
                          {permSearch
                            ? t("noPermissionsMatchSearch")
                            : t("noPermissionsFound")}
                        </Text>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <CreateCompositeRoleModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onCreated={(name) => {
          void mutateComp().then(() => setSelectedRole(name));
        }}
      />

      {deleteConfirmRole && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("deleteRoleTitle")}
          onClose={() => setDeleteConfirmRole(null)}
          submit={
            <Button danger onClick={handleDeleteRole} disabled={isDeleting}>
              {isDeleting ? t("deletingButton") : t("deleteButton")}
            </Button>
          }
        >
          <div className="flex flex-col gap-2">
            <Text as="p" text04>
              {t("confirmDeleteRole", {
                name: roleLabel(deleteConfirmRole),
                defaultValue: `Are you sure you want to delete "${roleLabel(
                  deleteConfirmRole
                )}"?`,
              })}
            </Text>
            <Text as="p" secondaryBody text03>
              {t("deleteRoleWarning", {
                defaultValue:
                  "This action cannot be undone and will permanently remove this role.",
              })}
            </Text>
          </div>
        </ConfirmationModalLayout>
      )}
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────

export default function Page() {
  const { t } = useTranslation();
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        title={t(route.titleKey || "", { defaultValue: route.title })}
        icon={route.icon}
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          title={t("admin.roles.workspaceTitle", {
            defaultValue: "Access policy workspace",
          })}
          description={t("admin.roles.workspaceDescription", {
            defaultValue:
              "Manage the roles users hold, grant permissions grouped by capability, and sync roles to identity infrastructure.",
          })}
          metrics={[
            {
              label: t("admin.roles.featureLayerLabel", {
                defaultValue: "Permission groups",
              }),
              value: t("admin.roles.features", {
                defaultValue: "Features",
              }),
            },
            {
              label: t("admin.roles.roleProfilesLabel", {
                defaultValue: "Role profiles",
              }),
              value: t("admin.roles.roles", { defaultValue: "Roles" }),
            },
            {
              label: t("admin.roles.permissionCatalogLabel", {
                defaultValue: "Permission catalog",
              }),
              value: t("admin.roles.permissions", {
                defaultValue: "Permissions",
              }),
            },
          ]}
          actions={[
            {
              label: t("admin.navigation.routes.users.sidebar", {
                defaultValue: "Users",
              }),
              href: ADMIN_PATHS.USERS,
              primary: true,
            },
          ]}
        />
        <RolesManager />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
