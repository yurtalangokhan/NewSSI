"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import Modal from "@/refresh-components/Modal";
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
  SvgTrash,
  SvgX,
} from "@opal/icons";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.ROLES]!;

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
  permissions: string[];
  is_builtin: boolean;
}

const ROLE_DISPLAY: Record<string, string> = {
  "system-admin": "System Admin",
  "enterprise-admin": "Enterprise Admin",
  enduser: "End User",
};

const UNEDITABLE_ROLES = new Set(["system-admin"]);

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
  { arg }: { arg: { name: string; description: string } }
) {
  const params = new URLSearchParams({ name: arg.name });
  if (arg.description) params.set("description", arg.description);
  const res = await fetch(`/api/user-service/roles/?${params}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail || "Failed to create role");
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

function RolePill({
  label,
  selected,
  onSelect,
}: {
  label: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "px-3 py-1.5 rounded-06 text-sm font-medium transition-colors",
        selected
          ? "bg-action-link-05 text-text-light-05"
          : "bg-background-neutral-02 text-02 hover:bg-background-neutral-03"
      )}
    >
      {label}
    </button>
  );
}

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
        arg: { name: name.trim(), description: description.trim() },
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
        <Modal.Header
          title="Create Role"
          onClose={onClose}
        />
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

function RolePermissionEditor() {
  const [selectedRole, setSelectedRole] = useState<string>("enterprise-admin");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [deleteConfirmRole, setDeleteConfirmRole] = useState<string | null>(
    null
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const rolesFetcher = useCallback(
    () =>
      fetch("/api/user-service/roles/").then((r) => {
        if (!r.ok) throw new Error("Failed to fetch roles");
        return r.json() as Promise<{ roles: Role[] }>;
      }),
    []
  );

  const {
    data: rolesData,
    isLoading: rolesLoading,
    mutate: mutateRoles,
  } = useSWR("/api/user-service/roles/", rolesFetcher, {
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
      ? `/api/user-service/roles/${selectedRole}/permissions`
      : null,
    errorHandlingFetcher,
    { dedupingInterval: 5000 }
  );

  const { trigger: savePermissions, isMutating: isSaving } = useSWRMutation(
    selectedRole ? `/api/user-service/roles/${selectedRole}/permissions` : null,
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
      onSuccess: (data) =>
        toast.success(
          `Synced to Keycloak: ${data.permission_roles_created} permission roles, ${data.composite_roles_updated} composite roles`
        ),
      onError: (err) => toast.error(err.message),
    }
  );

  const handleUpdateDescription = useCallback(
    async (description: string) => {
      try {
        await patchRole(`/api/user-service/roles/${selectedRole}`, {
          arg: { description },
        });
        mutateRoles();
        toast.success("Role updated");
      } catch (err: any) {
        toast.error(err.message);
      }
    },
    [selectedRole, mutateRoles]
  );

  const handleDeleteRoleAction = useCallback(
    async (roleName: string) => {
      setIsDeleting(true);
      try {
        await deleteRole(`/api/user-service/roles/${roleName}`);
        mutateRoles();
        if (roleName === selectedRole) {
          const remainingList = (rolesData?.roles ?? []).filter(
            (r) => r.name !== roleName
          );
          const nextRole = remainingList[0];
          if (nextRole) setSelectedRole(nextRole.name);
        }
        setDeleteConfirmRole(null);
        toast.success("Role deleted");
      } catch (err: any) {
        toast.error(err.message);
      } finally {
        setIsDeleting(false);
      }
    },
    [selectedRole, mutateRoles, rolesData]
  );

  const selectedRoleData = useMemo(() => {
    return rolesData?.roles.find((r) => r.name === selectedRole) ?? null;
  }, [rolesData, selectedRole]);

  const isRoleLocked = selectedRole
    ? UNEDITABLE_ROLES.has(selectedRole)
    : false;

  const groupedPermissions = useMemo(() => {
    if (!permsData?.permissions) return {};
    const grouped: Record<string, Record<string, Permission[]>> = {};
    for (const perm of permsData.permissions) {
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
  }, [permsData]);

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

  const handleToggle = useCallback(
    (name: string) => {
      if (isRoleLocked) return;
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
    [mutateRolePerms, selectedRole, isRoleLocked]
  );

  const handleSelectAll = useCallback(
    (entityPerms: Permission[], checked: boolean) => {
      if (isRoleLocked) return;
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
    [mutateRolePerms, selectedRole, isRoleLocked]
  );

  const handleSave = useCallback(() => {
    savePermissions({ permissions: Array.from(selectedPermsSet) });
  }, [selectedPermsSet, savePermissions]);

  const handleStartEditDescription = useCallback(() => {
    setDescriptionDraft(selectedRoleData?.description ?? "");
    setEditingDescription(true);
  }, [selectedRoleData]);

  const handleSaveDescription = useCallback(() => {
    handleUpdateDescription(descriptionDraft);
    setEditingDescription(false);
  }, [descriptionDraft, handleUpdateDescription]);

  const handleDeleteConfirm = useCallback(() => {
    if (deleteConfirmRole) handleDeleteRoleAction(deleteConfirmRole);
  }, [deleteConfirmRole, handleDeleteRoleAction]);

  const allLoading = rolesLoading || permsLoading || rolePermsLoading;

  if (allLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {(rolesData?.roles ?? []).map((role) => (
            <RolePill
              key={role.name}
              label={ROLE_DISPLAY[role.name] || role.name}
              selected={selectedRole === role.name}
              onSelect={() => setSelectedRole(role.name)}
            />
          ))}
          <Button
            leftIcon={SvgPlus}
            secondary
            onClick={() => setCreateModalOpen(true)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Button
            leftIcon={SvgCheck}
            disabled={isSaving || isRoleLocked}
            onClick={handleSave}
          >
            {isSaving ? "Saving..." : "Save"}
          </Button>
          <Button
            leftIcon={SvgRefreshCw}
            disabled={isSyncing}
            onClick={() => syncToKeycloak()}
          >
            {isSyncing ? "Syncing..." : "Sync"}
          </Button>
        </div>
      </div>

      {selectedRoleData && (
        <div className="mb-4 p-3 rounded-06 bg-background-neutral-02 flex items-center justify-between gap-2">
          <div className="flex-1 min-w-0">
            <Text secondaryBody text-02>
              {ROLE_DISPLAY[selectedRoleData.name] || selectedRoleData.name}
            </Text>
            {editingDescription ? (
              <div className="flex items-center gap-2 mt-1">
                <input
                  className="flex-1 px-2 py-1 rounded-04 border-01 bg-background-neutral-01 text-01 text-sm outline-none focus:border-action-link-05"
                  value={descriptionDraft}
                  onChange={(e) => setDescriptionDraft(e.target.value)}
                  autoFocus
                />
                <button
                  className="text-action-link-05 text-sm font-medium hover:underline"
                  onClick={handleSaveDescription}
                >
                  Save
                </button>
                <button
                  className="text-03 text-sm hover:underline"
                  onClick={() => setEditingDescription(false)}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 mt-1">
                <Text secondaryBody text-04 className="truncate italic">
                  {selectedRoleData.description || "No description"}
                </Text>
                {!isRoleLocked && (
                  <button
                    onClick={handleStartEditDescription}
                    className="text-03 hover:text-01 shrink-0"
                  >
                    <SvgEdit size={14} />
                  </button>
                )}
              </div>
            )}
          </div>
          {!isRoleLocked && (
            <Button
              leftIcon={SvgTrash}
              secondary
              className="text-danger-03 shrink-0"
              onClick={() => setDeleteConfirmRole(selectedRole)}
            >
              Delete
            </Button>
          )}
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
                    {!isRoleLocked && (
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
                          isRoleLocked ? "" : "cursor-pointer"
                        )}
                      >
                        {!isRoleLocked && (
                          <Checkbox
                            checked={selectedPermsSet.has(perm.name)}
                            onCheckedChange={() => handleToggle(perm.name)}
                          />
                        )}
                        <div className="flex flex-col min-w-0">
                          <Text secondaryBody text-02 className="truncate">
                            {perm.label}
                          </Text>
                          {perm.description && (
                            <Text secondaryBody text-04 className="truncate">
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
            <Text secondaryBody text-02>
              Are you sure you want to delete the role{" "}
              <Text secondaryBody text-01>
                {deleteConfirmRole}
              </Text>
              ? This action cannot be undone.
            </Text>
          </Modal.Body>
          <Modal.Footer>
            <Button secondary onClick={() => setDeleteConfirmRole(null)}>
              Cancel
            </Button>
            <Button
              danger
              onClick={handleDeleteConfirm}
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
        <RolePermissionEditor />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
