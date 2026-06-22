"use client";

import { useCallback, useMemo, useState } from "react";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import Text from "@/refresh-components/texts/Text";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/Spinner";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { toast } from "@/hooks/useToast";
import { SvgRefresh, SvgSave } from "@opal/icons";
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

function PermissionToggle({
  permission,
  checked,
  onToggle,
}: {
  permission: Permission;
  checked: boolean;
  onToggle: (name: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 py-1 px-2 rounded-06 hover:bg-background-neutral-02 cursor-pointer">
      <Checkbox checked={checked} onCheckedChange={() => onToggle(permission.name)} />
      <div className="flex flex-col">
        <Text as="span" mainUiSmall text-02>
          {permission.label}
        </Text>
        {permission.description && (
          <Text as="span" secondaryBody text-04>
            {permission.description}
          </Text>
        )}
      </div>
    </label>
  );
}

function ServiceSection({
  service,
  entities,
  selectedPermissions,
  onToggle,
}: {
  service: string;
  entities: Record<string, Permission[]>;
  selectedPermissions: Set<string>;
  onToggle: (name: string) => void;
}) {
  return (
    <div className="mb-4">
      <Text as="h3" headingH4 text-01 className="mb-2 capitalize">
        {service}
      </Text>
      {Object.entries(entities).map(([entity, perms]) => (
        <Card key={entity} className="mb-2">
          <CardHeader>
            <CardTitle className="capitalize">
              {entity.replace(/_/g, " ")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-1">
              {perms.map((perm) => (
                <PermissionToggle
                  key={perm.name}
                  permission={perm}
                  checked={selectedPermissions.has(perm.name)}
                  onToggle={onToggle}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function RoleSelector({
  roles,
  selected,
  onSelect,
}: {
  roles: Role[];
  selected: string;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="flex gap-2 mb-4 flex-wrap">
      {roles.map((role) => (
        <Button
          key={role.name}
          onClick={() => onSelect(role.name)}
          className={
            selected === role.name
              ? "bg-action-link-05 text-text-light-05"
              : ""
          }
        >
          {ROLE_DISPLAY[role.name] || role.name}
        </Button>
      ))}
    </div>
  );
}

function RolePermissionEditor() {
  const [selectedRole, setSelectedRole] = useState<string>("enterprise-admin");

  const { data: rolesData, isLoading: rolesLoading } = useSWR<{ roles: Role[] }>(
    "/api/user-service/roles/",
    errorHandlingFetcher,
    { dedupingInterval: 30000 }
  );

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
    selectedRole
      ? `/api/user-service/roles/${selectedRole}/permissions`
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
      onSuccess: (data) =>
        toast.success(
          `Synced to Keycloak: ${data.permission_roles_created} permission roles, ${data.composite_roles_updated} composite roles`
        ),
      onError: (err) => toast.error(err.message),
    }
  );

  const groupedPermissions = useMemo(() => {
    if (!permsData?.permissions) return {};
    const grouped: Record<string, Record<string, Permission[]>> = {};
    for (const perm of permsData.permissions) {
      if (!grouped[perm.service]) grouped[perm.service] = {};
      if (!grouped[perm.service][perm.entity])
        grouped[perm.service][perm.entity] = [];
      grouped[perm.service][perm.entity].push(perm);
    }
    return grouped;
  }, [permsData]);

  const selectedPermsSet = useMemo(() => {
    return new Set(rolePermsData?.permissions ?? []);
  }, [rolePermsData]);

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

  const handleSave = useCallback(() => {
    savePermissions({ permissions: Array.from(selectedPermsSet) });
  }, [selectedPermsSet, savePermissions]);

  const compositeRoles =
    rolesData?.roles.filter((r) =>
      ["system-admin", "enterprise-admin", "enduser"].includes(r.name)
    ) ?? [];

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
        <RoleSelector
          roles={compositeRoles}
          selected={selectedRole}
          onSelect={setSelectedRole}
        />
        <div className="flex items-center gap-2">
          <Button
            leftIcon={SvgSave}
            disabled={isSaving}
            onClick={handleSave}
          >
            {isSaving ? "Saving..." : "Save Permissions"}
          </Button>
          <Button
            leftIcon={SvgRefresh}
            disabled={isSyncing}
            onClick={() => syncToKeycloak()}
          >
            {isSyncing ? "Syncing..." : "Sync to Keycloak"}
          </Button>
        </div>
      </div>

      {Object.entries(groupedPermissions).map(([service, entities]) => (
        <ServiceSection
          key={service}
          service={service}
          entities={entities}
          selectedPermissions={selectedPermsSet}
          onToggle={handleToggle}
        />
      ))}
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
