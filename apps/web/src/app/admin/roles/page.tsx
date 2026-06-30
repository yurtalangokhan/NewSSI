"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import Modal from "@/refresh-components/Modal";
import SimpleTabs from "@/refresh-components/SimpleTabs";
import Text from "@/refresh-components/texts/Text";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/Spinner";
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
  SvgSearch,
  SvgShield,
  SvgServer,
  SvgTrash,
  SvgX,
} from "@opal/icons";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { useTranslation } from "react-i18next";
import { useUser } from "@/providers/UserProvider";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.ROLES]!;

// ─── Types ─────────────────────────────────────────────────────────

interface Permission {
  name: string;
  label: string;
  description: string | null;
  entity: string;
  service: string;
  action: string;
  is_system: boolean;
}

interface Role {
  name: string;
  description: string | null;
  service_client: string;
  permissions: string[];
}

interface CompositeRole {
  name: string;
  description: string | null;
  permissions: string[];
  role_ids: string[];
  is_builtin: boolean;
  is_admin: boolean;
}

// ─── Helpers ────────────────────────────────────────────────────────

const COMPOSITE_ROLE_LABELS: Record<string, string> = {
  "system-admin": "System Admin",
  "enterprise-admin": "Enterprise Admin",
  enduser: "End User",
};

const UNEDITABLE_ROLES = new Set(["system-admin"]);

function rolePath(name: string) {
  return encodeURIComponent(name);
}

function groupRolesByService(roles: Role[] | undefined) {
  const grouped: Record<string, Role[]> = {};
  for (const role of roles ?? []) {
    const serviceRoles = grouped[role.service_client];
    if (serviceRoles) {
      serviceRoles.push(role);
    } else {
      grouped[role.service_client] = [role];
    }
  }
  return grouped;
}

function roleLabel(name: string) {
  return COMPOSITE_ROLE_LABELS[name] || name;
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
      <Text headingH3 text01 className="block">
        {title}
      </Text>
      <Text secondaryBody text-03 className="mt-2 block">
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
    const err = await res.json().catch(() => ({ detail: "Failed to save" }));
    throw new Error(err.detail || "Failed to save permissions");
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
    const err = await res.json().catch(() => ({ detail: "Failed to save" }));
    throw new Error(err.detail || "Failed to save role assignment");
  }
  return res.json();
}

async function postSync(_url: string) {
  const res = await fetch("/api/user-service/roles/sync-keycloak", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Sync failed" }));
    throw new Error(err.detail || "Sync to Keycloak failed");
  }
  return res.json();
}

async function postCreateRole(
  _url: string,
  {
    arg,
  }: { arg: { name: string; description: string; service_client: string } }
) {
  const params = new URLSearchParams({
    name: arg.name,
    service_client: arg.service_client,
  });
  if (arg.description) params.set("description", arg.description);
  const res = await fetch(`/api/user-service/coarse-roles/?${params}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail || "Failed to create role");
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
    const err = await res.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail || "Failed to create composite role");
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
    const err = await res.json().catch(() => ({ detail: "Update failed" }));
    throw new Error(err.detail || "Failed to update role");
  }
  return res.json();
}

async function deleteRole(url: string) {
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Delete failed" }));
    throw new Error(err.detail || "Failed to delete role");
  }
  return res.json();
}

// ─── Create Role Modal ──────────────────────────────────────────────

function CreateRoleModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [serviceClient, setServiceClient] = useState("user-service");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) {
      setError("Role name is required");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await postCreateRole("", {
        arg: {
          name: name.trim(),
          description: description.trim(),
          service_client: serviceClient,
        },
      });
      onCreated();
      onClose();
      setName("");
      setDescription("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onClose}>
      <Modal.Content>
        <Modal.Header title="Create Role" onClose={onClose} />
        <Modal.Body>
          {error && (
            <div className="mb-3 p-2 rounded-06 bg-background-danger-02">
              <Text secondaryBody text-03>
                {error}
              </Text>
            </div>
          )}
          <div className="flex flex-col gap-3">
            <div>
              <Text secondaryBody text-02 className="mb-1 block">
                Role Name
              </Text>
              <input
                className="w-full px-3 py-2 rounded-06 border-01 bg-background-neutral-01 text-01 text-sm outline-none focus:border-action-link-05"
                placeholder="e.g. analyst"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <Text secondaryBody text-02 className="mb-1 block">
                Service Client
              </Text>
              <select
                className="w-full px-3 py-2 rounded-06 border-01 bg-background-neutral-01 text-01 text-sm outline-none focus:border-action-link-05"
                value={serviceClient}
                onChange={(e) => setServiceClient(e.target.value)}
              >
                <option value="user-service">user-service</option>
                <option value="agent-service">agent-service</option>
                <option value="rag-service">rag-service</option>
                <option value="tools-service">tools-service</option>
              </select>
            </div>
            <div>
              <Text secondaryBody text-02 className="mb-1 block">
                Description
              </Text>
              <input
                className="w-full px-3 py-2 rounded-06 border-01 bg-background-neutral-01 text-01 text-sm outline-none focus:border-action-link-05"
                placeholder="Optional description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button secondary onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={loading}>
            {loading ? "Creating..." : "Create Role"}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
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
      setError("Composite role name is required");
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
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={handleClose}>
      <Modal.Content>
        <Modal.Header title="Create Composite Role" onClose={handleClose} />
        <Modal.Body>
          {error && (
            <div className="mb-3 rounded-06 bg-background-danger-02 p-2">
              <Text secondaryBody text-03>
                {error}
              </Text>
            </div>
          )}
          <div className="flex flex-col gap-3">
            <div>
              <Text secondaryBody text-02 className="mb-1 block">
                Composite Role Name
              </Text>
              <input
                className="w-full rounded-06 border-01 bg-background-neutral-01 px-3 py-2 text-01 text-sm outline-none focus:border-action-link-05"
                placeholder="e.g. agent-admin"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <Text secondaryBody text-02 className="mb-1 block">
                Description
              </Text>
              <input
                className="w-full rounded-06 border-01 bg-background-neutral-01 px-3 py-2 text-01 text-sm outline-none focus:border-action-link-05"
                placeholder="Optional description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button secondary onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={loading}>
            {loading ? "Creating..." : "Create Composite Role"}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}

// ─── Roles Tab ──────────────────────────────────────────────────────

function RolesTab() {
  const { hasPermission } = useUser();
  const canManageRoles = hasPermission("role:manage");
  const [selectedRole, setSelectedRole] = useState<string>("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [deleteConfirmRole, setDeleteConfirmRole] = useState<string | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const {
    data: rolesData,
    isLoading: rolesLoading,
    mutate: mutateRoles,
  } = useSWR<{
    roles: Role[];
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
    mutate: mutateRolePerms,
    isLoading: rolePermsLoading,
  } = useSWR<{ name: string; permissions: string[] }>(
    selectedRole
      ? `/api/user-service/coarse-roles/${rolePath(selectedRole)}/permissions`
      : null,
    errorHandlingFetcher,
    { dedupingInterval: 5000 }
  );

  const { trigger: savePermissions, isMutating: isSaving } = useSWRMutation(
    selectedRole
      ? `/api/user-service/coarse-roles/${rolePath(selectedRole)}/permissions`
      : null,
    putPermissions,
    {
      onSuccess: () => {
        mutateRolePerms();
        toast.success("Permissions saved");
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const { trigger: syncToKeycloak, isMutating: isSyncing } = useSWRMutation(
    "/api/user-service/roles/sync-keycloak",
    postSync,
    {
      onSuccess: () => toast.success(`Synced to Keycloak`),
      onError: (err) => toast.error(err.message),
    }
  );

  const groupedRoles = useMemo(
    () => groupRolesByService(rolesData?.roles),
    [rolesData]
  );

  const selectedRoleData = useMemo(() => {
    return rolesData?.roles.find((r) => r.name === selectedRole) ?? null;
  }, [rolesData, selectedRole]);

  const selectedServiceClient = selectedRoleData?.service_client ?? "";

  const groupedPermissions = useMemo(() => {
    if (!permsData?.permissions) return {};
    const permissionPool = selectedServiceClient
      ? permsData.permissions.filter(
          (permission) => permission.service === selectedServiceClient
        )
      : [];
    const grouped: Record<string, Record<string, Permission[]>> = {};
    for (const perm of permissionPool) {
      let serviceGroup = grouped[perm.service];
      if (!serviceGroup) {
        serviceGroup = {};
        grouped[perm.service] = serviceGroup;
      }
      let entityList = serviceGroup[perm.entity];
      if (!entityList) {
        entityList = [];
        serviceGroup[perm.entity] = entityList;
      }
      entityList.push(perm);
    }
    return grouped;
  }, [permsData, selectedServiceClient]);

  const assignablePermissionNames = useMemo(() => {
    const names = new Set<string>();
    for (const entities of Object.values(groupedPermissions)) {
      for (const permissions of Object.values(entities)) {
        for (const permission of permissions) {
          names.add(permission.name);
        }
      }
    }
    return names;
  }, [groupedPermissions]);

  const filteredGrouped = useMemo(() => {
    if (!searchQuery.trim()) return groupedPermissions;
    const q = searchQuery.toLowerCase();
    const result: Record<string, Record<string, Permission[]>> = {};
    for (const [service, entities] of Object.entries(groupedPermissions)) {
      const filteredEntities: Record<string, Permission[]> = {};
      for (const [entity, perms] of Object.entries(entities)) {
        const filtered = perms.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.label.toLowerCase().includes(q) ||
            p.action.toLowerCase().includes(q) ||
            entity.toLowerCase().includes(q)
        );
        if (filtered.length > 0) filteredEntities[entity] = filtered;
      }
      if (Object.keys(filteredEntities).length > 0)
        result[service] = filteredEntities;
    }
    return result;
  }, [groupedPermissions, searchQuery]);

  const selectedPermsSet = useMemo(() => {
    return new Set(rolePermsData?.permissions ?? []);
  }, [rolePermsData]);

  useEffect(() => {
    const roles = rolesData?.roles ?? [];
    if (roles.length === 0) {
      setSelectedRole("");
      return;
    }
    if (!roles.some((role) => role.name === selectedRole)) {
      setSelectedRole(roles[0]?.name ?? "");
    }
  }, [rolesData, selectedRole]);

  const handleToggle = useCallback(
    (name: string) => {
      mutateRolePerms(
        (prev) => {
          const perms = prev?.permissions ?? [];
          if (perms.includes(name)) {
            return {
              name: selectedRole,
              permissions: perms.filter((p) => p !== name),
            };
          }
          return { name: selectedRole, permissions: [...perms, name] };
        },
        { revalidate: false }
      );
    },
    [mutateRolePerms, selectedRole]
  );

  const handleSelectAll = useCallback(
    (entityPerms: Permission[], checked: boolean) => {
      mutateRolePerms(
        (prev) => {
          const current = new Set(prev?.permissions ?? []);
          for (const p of entityPerms) {
            if (checked) current.add(p.name);
            else current.delete(p.name);
          }
          return { name: selectedRole, permissions: Array.from(current) };
        },
        { revalidate: false }
      );
    },
    [mutateRolePerms, selectedRole]
  );

  const handleSave = useCallback(() => {
    savePermissions({
      permissions: Array.from(selectedPermsSet).filter((permission) =>
        assignablePermissionNames.has(permission)
      ),
    });
  }, [assignablePermissionNames, selectedPermsSet, savePermissions]);

  const handleDeleteRoleAction = useCallback(
    async (roleName: string) => {
      if (!canManageRoles) return;
      setIsDeleting(true);
      try {
        await deleteRole(
          `/api/user-service/coarse-roles/${rolePath(roleName)}`
        );
        mutateRoles();
        if (roleName === selectedRole) {
          const remaining = (rolesData?.roles ?? []).filter(
            (r) => r.name !== roleName
          );
          const first = remaining[0];
          if (first) setSelectedRole(first.name);
        }
        setDeleteConfirmRole(null);
        toast.success("Role deleted");
      } catch (err: any) {
        toast.error(err.message);
      } finally {
        setIsDeleting(false);
      }
    },
    [canManageRoles, selectedRole, mutateRoles, rolesData]
  );

  const handleUpdateDescription = useCallback(
    async (description: string) => {
      try {
        await patchRole(
          `/api/user-service/coarse-roles/${rolePath(selectedRole)}`,
          { arg: { description } }
        );
        mutateRoles();
        toast.success("Role updated");
      } catch (err: any) {
        toast.error(err.message);
      }
    },
    [selectedRole, mutateRoles]
  );

  const isLocked = false; // no "built-in" concept for roles
  const canMutate = canManageRoles && !isLocked;

  const hasRoles = (rolesData?.roles ?? []).length > 0;
  const waitingForSelectedRole = hasRoles && !selectedRoleData;
  const allLoading =
    rolesLoading ||
    permsLoading ||
    waitingForSelectedRole ||
    (Boolean(selectedRole) && rolePermsLoading);

  if (allLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <Text headingH3 text01 className="block">
            Service roles
          </Text>
          <Text secondaryBody text-03 className="mt-1 block">
            Choose a role, select permissions, then save the assignment.
          </Text>
        </div>
        <div className="flex items-center gap-2">
          {canManageRoles && (
            <Button
              leftIcon={SvgPlus}
              secondary
              onClick={() => setCreateModalOpen(true)}
            >
              New role
            </Button>
          )}
          <Button
            leftIcon={SvgRefreshCw}
            disabled={isSyncing || !canManageRoles}
            onClick={() => syncToKeycloak()}
          >
            {isSyncing ? "Syncing..." : "Sync"}
          </Button>
        </div>
      </div>

      {!hasRoles ? (
        <EmptyState
          title="No roles found"
          description="Create a service role before assigning permissions."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-3">
            <div className="flex flex-col gap-4">
              {Object.entries(groupedRoles).map(([service, roles]) => (
                <div key={service}>
                  <Text secondaryBody text-04 className="mb-2 block text-xs">
                    {service}
                  </Text>
                  <div className="flex flex-col gap-1">
                    {roles.map((role) => {
                      const selected = selectedRole === role.name;
                      return (
                        <button
                          key={role.name}
                          type="button"
                          onClick={() => setSelectedRole(role.name)}
                          className={cn(
                            "flex w-full items-center justify-between gap-2 rounded-06 px-3 py-2 text-left transition-colors",
                            selected
                              ? "bg-action-link-05 text-text-light-05"
                              : "bg-background-neutral-00 text-text-02 hover:bg-background-neutral-02"
                          )}
                        >
                          <span className="min-w-0">
                            <Text
                              secondaryBody
                              as="span"
                              className={cn(
                                "block truncate",
                                selected ? "text-text-light-05" : "text-text-02"
                              )}
                            >
                              {role.name}
                            </Text>
                            <Text
                              secondaryBody
                              as="span"
                              className={cn(
                                "block truncate text-xs",
                                selected ? "text-text-light-03" : "text-text-04"
                              )}
                            >
                              {role.permissions.length} permissions
                            </Text>
                          </span>
                          {selected && <SvgCheck size={14} />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="min-w-0">
            {selectedRoleData && (
              <div className="mb-4 rounded-08 border border-border-01 bg-background-neutral-01 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Text headingH3 text01 className="truncate">
                        {selectedRoleData.name}
                      </Text>
                      <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                        {selectedRoleData.service_client}
                      </span>
                    </div>
                    {editingDescription ? (
                      <div className="mt-3 flex items-center gap-2">
                        <input
                          className="min-w-0 flex-1 rounded-04 border-01 bg-background-neutral-00 px-2 py-1 text-sm text-text-01"
                          value={descriptionDraft}
                          onChange={(e) => setDescriptionDraft(e.target.value)}
                          autoFocus
                        />
                        <button
                          type="button"
                          className="text-sm font-medium text-action-link-05 hover:underline"
                          onClick={() => {
                            handleUpdateDescription(descriptionDraft);
                            setEditingDescription(false);
                          }}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="text-sm text-text-03 hover:underline"
                          onClick={() => setEditingDescription(false)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="mt-2 flex items-center gap-2">
                        <Text secondaryBody text-04 className="truncate italic">
                          {selectedRoleData.description || "No description"}
                        </Text>
                        {canMutate && (
                          <button
                            type="button"
                            onClick={() => {
                              setDescriptionDraft(
                                selectedRoleData.description ?? ""
                              );
                              setEditingDescription(true);
                            }}
                            className="shrink-0 text-text-03 hover:text-text-01"
                            aria-label="Edit role description"
                          >
                            <SvgEdit size={14} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      leftIcon={SvgCheck}
                      disabled={isSaving || !canMutate}
                      onClick={handleSave}
                    >
                      {isSaving ? "Saving..." : "Save"}
                    </Button>
                    {canMutate && (
                      <Button
                        leftIcon={SvgTrash}
                        secondary
                        className="text-danger-03"
                        onClick={() => setDeleteConfirmRole(selectedRole)}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="relative mb-4">
              <SvgSearch
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-03 pointer-events-none"
              />
              <input
                ref={searchRef}
                className="w-full pl-9 pr-8 py-2 rounded-06 border-01 bg-background-neutral-01 text-01 text-sm outline-none focus:border-action-link-05"
                placeholder="Search permissions..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-03 hover:text-01"
                  onClick={() => setSearchQuery("")}
                >
                  <SvgX size={14} />
                </button>
              )}
            </div>

            {Object.entries(filteredGrouped).map(([service, entities]) => (
              <div key={service} className="mb-5">
                <div className="flex items-center gap-2 mb-3">
                  <div className="h-px flex-1 bg-border-01" />
                  <Text headingH3 text01 className="capitalize">
                    {service}
                  </Text>
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
                          {canMutate && (
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
                          <span className="text-xs text-03 bg-background-neutral-02 px-2 py-0.5 rounded-04">
                            {selectedCount}/{perms.length}
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1">
                          {perms.map((perm) => (
                            <label
                              key={perm.name}
                              className={cn(
                                "flex items-center gap-2 py-1.5 px-2 rounded-06 hover:bg-background-neutral-02",
                                canMutate ? "cursor-pointer" : ""
                              )}
                            >
                              {canMutate && (
                                <Checkbox
                                  checked={selectedPermsSet.has(perm.name)}
                                  onCheckedChange={() =>
                                    handleToggle(perm.name)
                                  }
                                />
                              )}
                              <div className="flex flex-col min-w-0">
                                <Text
                                  secondaryBody
                                  text-02
                                  className="truncate"
                                >
                                  {perm.label}
                                </Text>
                                {perm.description && (
                                  <Text
                                    secondaryBody
                                    text-04
                                    className="truncate"
                                  >
                                    {perm.description}
                                  </Text>
                                )}
                                <Text
                                  secondaryBody
                                  text-04
                                  className="text-[0.7rem] font-mono truncate"
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
            ))}

            {Object.keys(filteredGrouped).length === 0 && (
              <div className="py-8 text-center">
                <Text secondaryBody text-03>
                  {searchQuery
                    ? "No permissions match your search"
                    : "No permissions found"}
                </Text>
              </div>
            )}
          </div>
        </div>
      )}

      <CreateRoleModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onCreated={() => mutateRoles()}
      />

      <Modal
        open={!!deleteConfirmRole}
        onOpenChange={() => setDeleteConfirmRole(null)}
      >
        <Modal.Content>
          <Modal.Header
            title="Delete Role"
            onClose={() => setDeleteConfirmRole(null)}
          />
          <Modal.Body>
            <Text secondaryBody text-02 as="span">
              Are you sure you want to delete{" "}
              <span className="font-medium text-text-01">
                {deleteConfirmRole}
              </span>
              ?
            </Text>
          </Modal.Body>
          <Modal.Footer>
            <Button secondary onClick={() => setDeleteConfirmRole(null)}>
              Cancel
            </Button>
            <Button
              danger
              onClick={() => {
                if (deleteConfirmRole)
                  handleDeleteRoleAction(deleteConfirmRole);
              }}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete Role"}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>
    </div>
  );
}

// ─── Composite Roles Tab ────────────────────────────────────────────

function CompositeRolesTab() {
  const { hasPermission } = useUser();
  const canManage = hasPermission("role:manage");
  const [selectedComposite, setSelectedComposite] = useState<string>("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [deleteConfirmRole, setDeleteConfirmRole] = useState<string | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);

  const {
    data: compData,
    isLoading: compLoading,
    mutate: mutateComp,
  } = useSWR<{
    composite_roles: CompositeRole[];
  }>("/api/user-service/roles/", errorHandlingFetcher, {
    dedupingInterval: 30000,
  });

  const { data: rolesData, isLoading: rolesLoading } = useSWR<{
    roles: Role[];
  }>("/api/user-service/coarse-roles/", errorHandlingFetcher, {
    dedupingInterval: 30000,
  });

  const {
    data: roleIdsData,
    mutate: mutateRoleIds,
    isLoading: roleIdsLoading,
  } = useSWR<{
    name: string;
    role_ids: string[];
  }>(
    selectedComposite
      ? `/api/user-service/roles/${rolePath(selectedComposite)}/role-ids`
      : null,
    errorHandlingFetcher,
    { dedupingInterval: 5000 }
  );

  const { trigger: saveRoleIds, isMutating: isSavingRoleIds } = useSWRMutation(
    selectedComposite
      ? `/api/user-service/roles/${rolePath(selectedComposite)}/role-ids`
      : null,
    putRoleIds,
    {
      onSuccess: (data) => {
        mutateRoleIds();
        toast.success(
          `Role assignment saved — ${
            data.effective_permissions?.length ?? 0
          } effective permissions`
        );
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const selectedComp = useMemo(
    () =>
      compData?.composite_roles.find((r) => r.name === selectedComposite) ??
      null,
    [compData, selectedComposite]
  );

  const isLocked = selectedComposite
    ? UNEDITABLE_ROLES.has(selectedComposite)
    : false;
  const canMutate = canManage && !isLocked;

  const groupedRoles = useMemo(
    () => groupRolesByService(rolesData?.roles),
    [rolesData]
  );

  const selectedRoleIds = useMemo(
    () => new Set(roleIdsData?.role_ids ?? []),
    [roleIdsData]
  );

  useEffect(() => {
    const roles = compData?.composite_roles ?? [];
    if (roles.length === 0) {
      setSelectedComposite("");
      return;
    }
    if (!roles.some((role) => role.name === selectedComposite)) {
      setSelectedComposite(roles[0]?.name ?? "");
    }
  }, [compData, selectedComposite]);

  const handleToggleRole = useCallback(
    (roleName: string) => {
      if (!canMutate || !selectedComposite) return;
      const current = new Set(roleIdsData?.role_ids ?? []);
      if (current.has(roleName)) current.delete(roleName);
      else current.add(roleName);
      saveRoleIds({ role_ids: Array.from(current) });
    },
    [canMutate, selectedComposite, roleIdsData, saveRoleIds]
  );

  const allLoading =
    compLoading ||
    rolesLoading ||
    (Boolean(selectedComposite) && roleIdsLoading);

  if (allLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <Text headingH3 text01 className="block">
            Composite roles
          </Text>
          <Text secondaryBody text-03 className="mt-1 block">
            Select a composite role and assign the service roles it should
            include.
          </Text>
        </div>
        {canManage && (
          <Button
            leftIcon={SvgPlus}
            secondary
            onClick={() => setCreateModalOpen(true)}
          >
            New composite role
          </Button>
        )}
      </div>

      {(compData?.composite_roles ?? []).length === 0 ? (
        <EmptyState
          title="No composite roles found"
          description="Create a composite role before assigning service roles."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-3">
            <div className="flex flex-col gap-1">
              {(compData?.composite_roles ?? []).map((cr) => {
                const selected = selectedComposite === cr.name;
                return (
                  <button
                    key={cr.name}
                    type="button"
                    onClick={() => setSelectedComposite(cr.name)}
                    className={cn(
                      "flex w-full items-center justify-between gap-2 rounded-06 px-3 py-2 text-left transition-colors",
                      selected
                        ? "bg-action-link-05 text-text-light-05"
                        : "bg-background-neutral-00 text-text-02 hover:bg-background-neutral-02"
                    )}
                  >
                    <span className="min-w-0">
                      <Text
                        secondaryBody
                        as="span"
                        className={cn(
                          "block truncate",
                          selected ? "text-text-light-05" : "text-text-02"
                        )}
                      >
                        {roleLabel(cr.name)}
                      </Text>
                      <Text
                        secondaryBody
                        as="span"
                        className={cn(
                          "block truncate text-xs",
                          selected ? "text-text-light-03" : "text-text-04"
                        )}
                      >
                        {(cr.role_ids?.length ?? 0) + " assigned roles"}
                      </Text>
                    </span>
                    {selected && <SvgCheck size={14} />}
                  </button>
                );
              })}
            </div>
          </div>

          {selectedComp && (
            <div className="min-w-0">
              <div className="mb-4 rounded-08 border border-border-01 bg-background-neutral-01 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Text headingH3 text01 className="truncate">
                        {roleLabel(selectedComp.name)}
                      </Text>
                      {isLocked && (
                        <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                          built-in
                        </span>
                      )}
                    </div>
                    {editingDescription ? (
                      <div className="mt-3 flex items-center gap-2">
                        <input
                          className="min-w-0 flex-1 rounded-04 border-01 bg-background-neutral-00 px-2 py-1 text-sm text-text-01"
                          value={descriptionDraft}
                          onChange={(e) => setDescriptionDraft(e.target.value)}
                          autoFocus
                        />
                        <button
                          type="button"
                          className="text-sm font-medium text-action-link-05 hover:underline"
                          onClick={async () => {
                            try {
                              await patchRole(
                                `/api/user-service/roles/${rolePath(
                                  selectedComposite
                                )}`,
                                { arg: { description: descriptionDraft } }
                              );
                              mutateComp();
                              toast.success("Updated");
                            } catch (err: any) {
                              toast.error(err.message);
                            }
                            setEditingDescription(false);
                          }}
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          className="text-sm text-text-03 hover:underline"
                          onClick={() => setEditingDescription(false)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="mt-2 flex items-center gap-2">
                        <Text secondaryBody text-04 className="truncate italic">
                          {selectedComp.description || "No description"}
                        </Text>
                        {canMutate && (
                          <button
                            type="button"
                            onClick={() => {
                              setDescriptionDraft(
                                selectedComp.description ?? ""
                              );
                              setEditingDescription(true);
                            }}
                            className="shrink-0 text-text-03 hover:text-text-01"
                            aria-label="Edit composite role description"
                          >
                            <SvgEdit size={14} />
                          </button>
                        )}
                      </div>
                    )}
                    <Text secondaryBody text-04 className="mt-2 block">
                      {selectedRoleIds.size > 0
                        ? `${selectedRoleIds.size} service roles assigned`
                        : "No service roles assigned"}
                    </Text>
                  </div>
                  {canMutate && (
                    <Button
                      leftIcon={SvgTrash}
                      secondary
                      className="shrink-0 text-danger-03"
                      onClick={() => setDeleteConfirmRole(selectedComposite)}
                    >
                      Delete
                    </Button>
                  )}
                </div>
              </div>

              <div className="space-y-4">
                {Object.entries(groupedRoles).map(([service, roles]) => (
                  <Card key={service} className="rounded-08">
                    <CardHeader className="p-4">
                      <div className="flex items-center justify-between gap-3">
                        <CardTitle className="text-sm capitalize">
                          {service}
                        </CardTitle>
                        <span className="rounded-04 bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                          {
                            roles.filter((role) =>
                              selectedRoleIds.has(role.name)
                            ).length
                          }
                          /{roles.length}
                        </span>
                      </div>
                    </CardHeader>
                    <CardContent className="p-4 pt-0">
                      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
                        {roles.map((role) => (
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
                                text-02
                                className="block truncate"
                              >
                                {role.name}
                              </Text>
                              <Text
                                secondaryBody
                                text-04
                                className="block text-xs"
                              >
                                {role.permissions.length} permissions
                              </Text>
                            </span>
                          </label>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <Modal
        open={!!deleteConfirmRole}
        onOpenChange={() => setDeleteConfirmRole(null)}
      >
        <Modal.Content>
          <Modal.Header
            title="Delete Composite Role"
            onClose={() => setDeleteConfirmRole(null)}
          />
          <Modal.Body>
            <Text secondaryBody text-02 as="span">
              Are you sure you want to delete{" "}
              <span className="font-medium text-text-01">
                {deleteConfirmRole}
              </span>
              ? This cannot be undone.
            </Text>
          </Modal.Body>
          <Modal.Footer>
            <Button secondary onClick={() => setDeleteConfirmRole(null)}>
              Cancel
            </Button>
            <Button
              danger
              onClick={async () => {
                if (!deleteConfirmRole) return;
                setIsDeleting(true);
                try {
                  await deleteRole(
                    `/api/user-service/roles/${rolePath(deleteConfirmRole)}`
                  );
                  mutateComp();
                  setDeleteConfirmRole(null);
                  toast.success("Deleted");
                } catch (err: any) {
                  toast.error(err.message);
                } finally {
                  setIsDeleting(false);
                }
              }}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete Role"}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>

      <CreateCompositeRoleModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onCreated={(name) => {
          void mutateComp().then(() => setSelectedComposite(name));
        }}
      />
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
        <SimpleTabs
          tabs={{
            roles: {
              name: "Roles",
              content: <RolesTab />,
              icon: SvgServer,
            },
            compositeRoles: {
              name: "Composite Roles",
              content: <CompositeRolesTab />,
              icon: SvgShield,
            },
          }}
          defaultValue="roles"
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
