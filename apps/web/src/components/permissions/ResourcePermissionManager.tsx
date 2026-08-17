/**
 * ResourcePermissionManager Component
 * 
 * Comprehensive permission management UI for agents, agent groups, RAG collections, and connectors.
 * 
 * Features:
 * - Multi-resource type support
 * - Organization-level permissions
 * - User-level permissions
 * - Permission inheritance visualization
 * - Bulk operations
 * - Audit trail
 */

"use client";

import { useState, useCallback, useMemo } from "react";
import useSWR, { mutate } from "swr";
import {
  Shield,
  User,
  Users,
  Buildings,
  CaretDown,
  Plus,
  Trash,
  Warning,
  Check,
  X,
} from "@phosphor-icons/react";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

type ResourceType = "agent" | "agent_group" | "rag_collection" | "connector";
type PermissionLevel = "owner" | "admin" | "write" | "read" | "execute";

interface Permission {
  id: string;
  resource_type: ResourceType;
  resource_id: string;
  user_id?: string;
  organization_id?: string;
  permission_level: PermissionLevel;
  granted_by: string;
  granted_at: string;
  is_inherited: boolean;
  source?: string;
}

interface Organization {
  id: string;
  name: string;
  path: string;
}

interface UserInfo {
  id: string;
  email: string;
  full_name?: string;
}

interface ResourcePermissionManagerProps {
  resourceType: ResourceType;
  resourceId: string;
  resourceName?: string;
  onClose?: () => void;
  className?: string;
}

const PERMISSION_LEVELS: Array<{
  value: PermissionLevel;
  label: string;
  description: string;
  color: string;
}> = [
  {
    value: "owner",
    label: "Owner",
    description: "Full control, can delete and transfer ownership",
    color: "text-purple-600 dark:text-purple-400",
  },
  {
    value: "admin",
    label: "Admin",
    description: "Can manage permissions and settings",
    color: "text-red-600 dark:text-red-400",
  },
  {
    value: "write",
    label: "Write",
    description: "Can modify and configure",
    color: "text-orange-600 dark:text-orange-400",
  },
  {
    value: "read",
    label: "Read",
    description: "Can view but not modify",
    color: "text-blue-600 dark:text-blue-400",
  },
  {
    value: "execute",
    label: "Execute",
    description: "Can use/run but not view configuration",
    color: "text-green-600 dark:text-green-400",
  },
];

const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  agent: "Agent",
  agent_group: "Agent Group",
  rag_collection: "RAG Collection",
  connector: "Connector",
};

export function ResourcePermissionManager({
  resourceType,
  resourceId,
  resourceName,
  onClose,
  className,
}: ResourcePermissionManagerProps) {
  const [showAddUser, setShowAddUser] = useState(false);
  const [showAddOrg, setShowAddOrg] = useState(false);
  const [selectedPermissionLevel, setSelectedPermissionLevel] =
    useState<PermissionLevel>("read");

  // Fetch current permissions
  const { data: permissions, isLoading } = useSWR<Permission[]>(
    `/api/permissions/resources/${resourceType}/${resourceId}`,
    async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch permissions");
      return res.json();
    }
  );

  // Fetch organizations
  const { data: organizations } = useSWR<Organization[]>(
    "/api/organizations",
    async (url: string) => {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch organizations");
      return res.json();
    }
  );

  // Fetch users for search
  const { data: users } = useSWR<UserInfo[]>("/api/users", async (url: string) => {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch users");
    return res.json();
  });

  const handleAddUserPermission = useCallback(
    async (userId: string, level: PermissionLevel) => {
      try {
        const res = await fetch("/api/permissions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resource_type: resourceType,
            resource_id: resourceId,
            user_id: userId,
            permission_level: level,
          }),
        });

        if (!res.ok) {
          throw new Error("Failed to grant permission");
        }

        // Refresh permissions
        mutate(`/api/permissions/resources/${resourceType}/${resourceId}`);
        setShowAddUser(false);
      } catch (error) {
        console.error("Error granting permission:", error);
        alert("Failed to grant permission");
      }
    },
    [resourceType, resourceId]
  );

  const handleAddOrgPermission = useCallback(
    async (orgId: string, level: PermissionLevel) => {
      try {
        const res = await fetch("/api/permissions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resource_type: resourceType,
            resource_id: resourceId,
            organization_id: orgId,
            permission_level: level,
          }),
        });

        if (!res.ok) {
          throw new Error("Failed to grant permission");
        }

        mutate(`/api/permissions/resources/${resourceType}/${resourceId}`);
        setShowAddOrg(false);
      } catch (error) {
        console.error("Error granting permission:", error);
        alert("Failed to grant permission");
      }
    },
    [resourceType, resourceId]
  );

  const handleRemovePermission = useCallback(
    async (permissionId: string) => {
      if (!confirm("Remove this permission?")) return;

      try {
        const res = await fetch(`/api/permissions/${permissionId}`, {
          method: "DELETE",
        });

        if (!res.ok) {
          throw new Error("Failed to remove permission");
        }

        mutate(`/api/permissions/resources/${resourceType}/${resourceId}`);
      } catch (error) {
        console.error("Error removing permission:", error);
        alert("Failed to remove permission");
      }
    },
    [resourceType, resourceId]
  );

  const groupedPermissions = useMemo(() => {
    if (!permissions) return { user: [], organization: [], inherited: [] };

    return {
      user: permissions.filter((p) => p.user_id && !p.is_inherited),
      organization: permissions.filter((p) => p.organization_id && !p.is_inherited),
      inherited: permissions.filter((p) => p.is_inherited),
    };
  }, [permissions]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Text className="text-text-03">Loading permissions...</Text>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col bg-background-neutral-01 rounded-lg", className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-border-02">
        <div className="flex items-center gap-3">
          <Shield size={24} className="text-text-02" />
          <div>
            <Text className="text-lg font-semibold text-text-05">
              Manage Permissions
            </Text>
            <Text className="text-sm text-text-03">
              {RESOURCE_TYPE_LABELS[resourceType]}: {resourceName || resourceId}
            </Text>
          </div>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="p-2 rounded-md hover:bg-background-neutral-02 text-text-03 hover:text-text-05"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* User Permissions */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <User size={18} className="text-text-02" />
              <Text className="font-medium text-text-05">User Permissions</Text>
              <span className="px-2 py-1 rounded bg-background-neutral-02 text-xs text-text-03">
                {groupedPermissions.user.length}
              </span>
            </div>

            <button
              onClick={() => setShowAddUser(true)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md",
                "bg-background-primary-01 hover:bg-background-primary-02",
                "text-text-primary-01 text-sm font-medium"
              )}
            >
              <Plus size={16} />
              <span>Add User</span>
            </button>
          </div>

          <div className="space-y-2">
            {groupedPermissions.user.length === 0 ? (
              <div className="text-center py-8 text-text-03 text-sm">
                No user-specific permissions
              </div>
            ) : (
              groupedPermissions.user.map((perm) => (
                <PermissionRow
                  key={perm.id}
                  permission={perm}
                  users={users}
                  organizations={organizations}
                  onRemove={() => handleRemovePermission(perm.id)}
                />
              ))
            )}
          </div>
        </section>

        {/* Organization Permissions */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Buildings size={18} className="text-text-02" />
              <Text className="font-medium text-text-05">
                Organization Permissions
              </Text>
              <span className="px-2 py-1 rounded bg-background-neutral-02 text-xs text-text-03">
                {groupedPermissions.organization.length}
              </span>
            </div>

            <button
              onClick={() => setShowAddOrg(true)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md",
                "bg-background-primary-01 hover:bg-background-primary-02",
                "text-text-primary-01 text-sm font-medium"
              )}
            >
              <Plus size={16} />
              <span>Add Organization</span>
            </button>
          </div>

          <div className="space-y-2">
            {groupedPermissions.organization.length === 0 ? (
              <div className="text-center py-8 text-text-03 text-sm">
                No organization permissions
              </div>
            ) : (
              groupedPermissions.organization.map((perm) => (
                <PermissionRow
                  key={perm.id}
                  permission={perm}
                  users={users}
                  organizations={organizations}
                  onRemove={() => handleRemovePermission(perm.id)}
                />
              ))
            )}
          </div>
        </section>

        {/* Inherited Permissions */}
        {groupedPermissions.inherited.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Users size={18} className="text-text-02" />
              <Text className="font-medium text-text-05">Inherited Permissions</Text>
              <span className="px-2 py-1 rounded bg-background-neutral-02 text-xs text-text-03">
                {groupedPermissions.inherited.length}
              </span>
            </div>

            <div className="space-y-2">
              {groupedPermissions.inherited.map((perm) => (
                <PermissionRow
                  key={perm.id}
                  permission={perm}
                  users={users}
                  organizations={organizations}
                  isReadOnly
                />
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Add User Modal */}
      {showAddUser && users && (
        <AddPermissionModal
          title="Add User Permission"
          items={users.map((u) => ({
            id: u.id,
            label: u.full_name || u.email,
            sublabel: u.email,
          }))}
          onAdd={(userId) => handleAddUserPermission(userId, selectedPermissionLevel)}
          onClose={() => setShowAddUser(false)}
          selectedLevel={selectedPermissionLevel}
          onLevelChange={setSelectedPermissionLevel}
        />
      )}

      {/* Add Organization Modal */}
      {showAddOrg && organizations && (
        <AddPermissionModal
          title="Add Organization Permission"
          items={organizations.map((org) => ({
            id: org.id,
            label: org.name,
            sublabel: org.path,
          }))}
          onAdd={(orgId) => handleAddOrgPermission(orgId, selectedPermissionLevel)}
          onClose={() => setShowAddOrg(false)}
          selectedLevel={selectedPermissionLevel}
          onLevelChange={setSelectedPermissionLevel}
        />
      )}
    </div>
  );
}

function PermissionRow({
  permission,
  users,
  organizations,
  onRemove,
  isReadOnly,
}: {
  permission: Permission;
  users?: UserInfo[];
  organizations?: Organization[];
  onRemove?: () => void;
  isReadOnly?: boolean;
}) {
  const levelInfo = PERMISSION_LEVELS.find(
    (l) => l.value === permission.permission_level
  );

  const displayName = permission.user_id
    ? users?.find((u) => u.id === permission.user_id)?.email || "Unknown User"
    : organizations?.find((o) => o.id === permission.organization_id)?.name ||
      "Unknown Organization";

  const icon = permission.user_id ? (
    <User size={16} className="text-text-03" />
  ) : (
    <Buildings size={16} className="text-text-03" />
  );

  return (
    <div
      className={cn(
        "flex items-center justify-between p-3 rounded-md border",
        "bg-background-neutral-01 border-border-02",
        isReadOnly && "opacity-60"
      )}
    >
      <div className="flex items-center gap-3 flex-1">
        {icon}
        <div className="flex-1">
          <Text className="text-sm font-medium text-text-05">{displayName}</Text>
          {permission.is_inherited && permission.source && (
            <Text className="text-xs text-text-03">
              Inherited from {permission.source}
            </Text>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className={cn("text-sm font-medium", levelInfo?.color)}>
          {levelInfo?.label}
        </span>

        {!isReadOnly && onRemove && (
          <button
            onClick={onRemove}
            className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600"
          >
            <Trash size={16} />
          </button>
        )}
      </div>
    </div>
  );
}

function AddPermissionModal({
  title,
  items,
  onAdd,
  onClose,
  selectedLevel,
  onLevelChange,
}: {
  title: string;
  items: Array<{ id: string; label: string; sublabel?: string }>;
  onAdd: (id: string) => void;
  onClose: () => void;
  selectedLevel: PermissionLevel;
  onLevelChange: (level: PermissionLevel) => void;
}) {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filtered = useMemo(
    () =>
      items.filter(
        (item) =>
          item.label.toLowerCase().includes(search.toLowerCase()) ||
          item.sublabel?.toLowerCase().includes(search.toLowerCase())
      ),
    [items, search]
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background-neutral-01 rounded-lg shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b border-border-02">
          <Text className="text-lg font-semibold text-text-05">{title}</Text>
          <button
            onClick={onClose}
            className="p-2 rounded-md hover:bg-background-neutral-02 text-text-03"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Search */}
          <input
            type="text"
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={cn(
              "w-full px-3 py-2 rounded-md border",
              "bg-background-neutral-01 border-border-02",
              "text-text-05 placeholder:text-text-03",
              "focus:outline-none focus:ring-2 focus:ring-border-primary"
            )}
          />

          {/* Permission Level */}
          <div>
            <Text className="text-sm font-medium text-text-02 mb-2">
              Permission Level
            </Text>
            <div className="space-y-1">
              {PERMISSION_LEVELS.map((level) => (
                <label
                  key={level.value}
                  className={cn(
                    "flex items-center gap-3 p-3 rounded-md cursor-pointer",
                    "border transition-colors",
                    selectedLevel === level.value
                      ? "bg-background-primary-01 border-border-primary"
                      : "bg-background-neutral-01 border-border-02 hover:bg-background-neutral-02"
                  )}
                >
                  <input
                    type="radio"
                    name="permission"
                    value={level.value}
                    checked={selectedLevel === level.value}
                    onChange={() => onLevelChange(level.value)}
                    className="sr-only"
                  />
                  <div className="flex-1">
                    <div className={cn("font-medium text-sm", level.color)}>
                      {level.label}
                    </div>
                    <div className="text-xs text-text-03">{level.description}</div>
                  </div>
                  {selectedLevel === level.value && (
                    <Check size={18} className="text-text-primary-01" />
                  )}
                </label>
              ))}
            </div>
          </div>

          {/* Item List */}
          <div>
            <Text className="text-sm font-medium text-text-02 mb-2">Select</Text>
            <div className="max-h-64 overflow-y-auto space-y-1 border border-border-02 rounded-md p-2">
              {filtered.map((item) => (
                <label
                  key={item.id}
                  className={cn(
                    "flex items-center gap-3 p-2 rounded-md cursor-pointer",
                    "transition-colors",
                    selectedId === item.id
                      ? "bg-background-primary-01"
                      : "hover:bg-background-neutral-02"
                  )}
                >
                  <input
                    type="radio"
                    name="item"
                    value={item.id}
                    checked={selectedId === item.id}
                    onChange={() => setSelectedId(item.id)}
                    className="sr-only"
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-text-05">
                      {item.label}
                    </div>
                    {item.sublabel && (
                      <div className="text-xs text-text-03">{item.sublabel}</div>
                    )}
                  </div>
                  {selectedId === item.id && (
                    <Check size={16} className="text-text-primary-01" />
                  )}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 p-6 border-t border-border-02">
          <button
            onClick={onClose}
            className={cn(
              "px-4 py-2 rounded-md",
              "bg-background-neutral-02 hover:bg-background-neutral-03",
              "text-text-02 text-sm font-medium"
            )}
          >
            Cancel
          </button>
          <button
            onClick={() => selectedId && onAdd(selectedId)}
            disabled={!selectedId}
            className={cn(
              "px-4 py-2 rounded-md",
              "bg-background-primary-01 hover:bg-background-primary-02",
              "text-text-primary-01 text-sm font-medium",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            Add Permission
          </button>
        </div>
      </div>
    </div>
  );
}
