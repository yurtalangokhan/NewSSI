"use client";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

import { useContext } from "react";
import useSWR from "swr";
import { mutate } from "swr";
import { SettingsContext } from "@/providers/SettingsProvider";
import { UserGroup } from "@/lib/types";
import { fetchDirectoryRoleDistribution } from "@/lib/api/domains/access/api";
import { fetchDirectoryUserStatusCount } from "@/lib/api/domains/access/api";
import { fetchPendingDirectoryUsers } from "@/lib/api/domains/access/api";
import { fetchRoles } from "@/lib/api/domains/access/api";
import { fetchScopedPermissions } from "@/lib/api/domains/access/api";
import { fetchUserGroupsForSWR } from "@/lib/api/domains/access/api";

import type { DirectoryRole } from "@/lib/api/domains/access/types";
import type { ScopedPermissionResource } from "@/lib/api/domains/access/types";
import type { ScopedPermissionsResponse } from "@/lib/api/domains/access/types";
import type { ScopedPermissionTarget } from "@/lib/api/domains/access/types";
import { fetchManageUserGroups } from "@/lib/api/domains/access/api";

import { useMemo } from "react";
import { fetchShareableMinimalUserGroups } from "@/lib/api/domains/access/api";

import { fetchShareableUsers } from "@/lib/api/domains/access/api";
import { MinimalUserSnapshot } from "@/lib/types";

import { AllUsersResponse } from "@/lib/types";
import { fetchManageUsers } from "@/lib/api/domains/access/api";

export function useUserGroups(): {
  data: UserGroup[] | undefined;
  isLoading: boolean;
  error: any;
  refreshUserGroups: () => void;
} {
  const settings = useContext(SettingsContext);
  const enabled = Boolean(settings && settings.enterpriseSettings !== null);
  const swrResponse = useSWR<UserGroup[]>(
    enabled ? accessEndpoints.manageUserGroup.browserPath : null,
    () => fetchUserGroupsForSWR<UserGroup[]>()
  );
  if (!enabled)
    return {
      data: [],
      isLoading: false,
      error: "",
      refreshUserGroups: () => {},
    };
  return {
    ...swrResponse,
    refreshUserGroups: () =>
      mutate(accessEndpoints.manageUserGroup.browserPath),
  };
}

export function useScopedPermissions(
  organizationId: string,
  targetType: ScopedPermissionTarget,
  targetId: string,
  resourceType: ScopedPermissionResource,
  fallback: string
) {
  return useSWR<ScopedPermissionsResponse>(
    accessEndpoints.scopedPermissions(
      organizationId,
      targetType,
      targetId,
      resourceType
    ).browserPath,
    () =>
      fetchScopedPermissions(
        organizationId,
        targetType,
        targetId,
        resourceType,
        fallback
      )
  );
}

export function useDirectoryRoles() {
  return useSWR<{ roles: DirectoryRole[] }>(
    accessEndpoints.userServiceRoles.browserPath,
    () => fetchRoles<{ roles: DirectoryRole[] }>()
  );
}

export function usePendingDirectoryUsers<T>(enabled: boolean) {
  return useSWR<T[]>(enabled ? "pending-directory-users" : null, () =>
    fetchPendingDirectoryUsers<T[]>()
  );
}

export function useDirectoryRoleDistribution() {
  return useSWR("directory-role-distribution", fetchDirectoryRoleDistribution);
}

export function useDirectoryUserStatusCount(active: boolean) {
  return useSWR(["directory-user-status-count", active], () =>
    fetchDirectoryUserStatusCount(active)
  );
}

/**
 * Fetches all user groups in the organization.
 *
 * Returns group information including group members, curators, and associated resources.
 * Use this for displaying group lists in sharing dialogs, admin panels, or permission
 * management interfaces.
 *
 * Note: This hook only returns data if enterprise features are enabled. In non-enterprise
 * environments, it returns an empty array.
 *
 * @returns Object containing:
 *   - data: Array of UserGroup objects, or undefined while loading
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Any error that occurred during fetch
 *   - refreshGroups: Function to manually revalidate the data
 *
 * @example
 * // Fetch groups for sharing dialogs
 * const { data: groupsData, isLoading } = useGroups();
 * if (isLoading) return <Spinner />;
 * return <GroupList groups={groupsData ?? []} />;
 *
 * @example
 * // Fetch groups with manual refresh
 * const { data: groupsData, refreshGroups } = useGroups();
 * // Later...
 * await createNewGroup(...);
 * refreshGroups(); // Refresh the group list
 */
export function useGroups() {
  const combinedSettings = useContext(SettingsContext);
  const isPaidEnterpriseFeaturesEnabled =
    combinedSettings && combinedSettings.enterpriseSettings !== null;

  const { data, error, mutate, isLoading } = useSWR<UserGroup[]>(
    isPaidEnterpriseFeaturesEnabled
      ? accessEndpoints.manageUserGroup.browserPath
      : null,
    () => fetchManageUserGroups<UserGroup[]>()
  );

  // If enterprise features are not enabled, return empty array
  if (!isPaidEnterpriseFeaturesEnabled) {
    return {
      data: [],
      isLoading: false,
      error: undefined,
      refreshGroups: () => {},
    };
  }

  return {
    data,
    isLoading,
    error,
    refreshGroups: mutate,
  };
}

export interface MinimalUserGroupSnapshot {
  id: number;
  name: string;
}

// TODO (@raunakab):
// Refactor this hook to live inside of a special `ee` directory.

interface RawGroupsResponse {
  groups?: MinimalUserGroupSnapshot[];
  items?: MinimalUserGroupSnapshot[];
}

export function useShareableGroups() {
  const combinedSettings = useContext(SettingsContext);
  const isPaidEnterpriseFeaturesEnabled =
    combinedSettings && combinedSettings.enterpriseSettings !== null;

  const {
    data: rawData,
    error,
    mutate,
    isLoading,
  } = useSWR<MinimalUserGroupSnapshot[] | RawGroupsResponse>(
    isPaidEnterpriseFeaturesEnabled
      ? accessEndpoints.shareableMinimalUserGroups.browserPath
      : null,
    () => fetchShareableMinimalUserGroups<MinimalUserGroupSnapshot[]>()
  );

  const data = useMemo<MinimalUserGroupSnapshot[] | undefined>(() => {
    if (!isPaidEnterpriseFeaturesEnabled) return [];
    if (!rawData) return undefined;
    if (Array.isArray(rawData)) return rawData;
    if (Array.isArray(rawData.groups)) return rawData.groups;
    if (Array.isArray(rawData.items)) return rawData.items;
    return [];
  }, [isPaidEnterpriseFeaturesEnabled, rawData]);

  if (!isPaidEnterpriseFeaturesEnabled) {
    return {
      data: [],
      isLoading: false,
      error: undefined,
      refreshShareableGroups: () => {},
    };
  }

  return {
    data,
    isLoading,
    error,
    refreshShareableGroups: mutate,
  };
}

export interface UseShareableUsersParams {
  includeApiKeys: boolean;
}

interface RawUsersResponse {
  users?: MinimalUserSnapshot[];
  items?: MinimalUserSnapshot[];
  accepted?: MinimalUserSnapshot[];
}

export function useShareableUsers({ includeApiKeys }: UseShareableUsersParams) {
  const {
    data: rawData,
    error,
    mutate,
    isLoading,
  } = useSWR<MinimalUserSnapshot[] | RawUsersResponse>(
    accessEndpoints.shareableUsersCacheKey(includeApiKeys).browserPath,
    () =>
      fetchShareableUsers(includeApiKeys) as Promise<
        MinimalUserSnapshot[] | RawUsersResponse
      >
  );

  const data = useMemo<MinimalUserSnapshot[] | undefined>(() => {
    if (!rawData) return undefined;
    if (Array.isArray(rawData)) return rawData;
    if (Array.isArray((rawData as RawUsersResponse).users))
      return (rawData as RawUsersResponse).users;
    if (Array.isArray((rawData as RawUsersResponse).items))
      return (rawData as RawUsersResponse).items;
    if (Array.isArray((rawData as RawUsersResponse).accepted))
      return (rawData as RawUsersResponse).accepted;
    return [];
  }, [rawData]);

  return {
    data,
    isLoading,
    error,
    refreshShareableUsers: mutate,
  };
}

export interface UseUsersParams {
  includeApiKeys: boolean;
}

/**
 * Fetches all users in the organization.
 *
 * Returns user information including accepted users, invited users, and optionally
 * API key users. Use this for displaying user lists in sharing dialogs, admin panels,
 * or permission management interfaces.
 *
 * @param params - Configuration object
 * @param params.includeApiKeys - Whether to include API key users in the response
 *
 * @returns Object containing:
 *   - data: AllUsersResponse containing accepted, invited, and API key users, or undefined while loading
 *   - isLoading: Boolean indicating if data is being fetched
 *   - error: Any error that occurred during fetch
 *   - refreshUsers: Function to manually revalidate the data
 *
 * @example
 * // Fetch users without API keys (for sharing dialogs)
 * const { data: usersData, isLoading } = useUsers({ includeApiKeys: false });
 * if (isLoading) return <Spinner />;
 * return <UserList users={usersData?.accepted ?? []} />;
 *
 * @example
 * // Fetch all users including API keys (for admin panel)
 * const { data: usersData, refreshUsers } = useUsers({ includeApiKeys: true });
 * // Later...
 * await createNewUser(...);
 * refreshUsers(); // Refresh the user list
 */
export function useUsers({ includeApiKeys }: UseUsersParams) {
  const { data, error, mutate, isLoading } = useSWR<AllUsersResponse>(
    accessEndpoints.manageUsersCacheKey(includeApiKeys).browserPath,
    () => fetchManageUsers(includeApiKeys) as Promise<AllUsersResponse>
  );

  return {
    data,
    isLoading,
    error,
    refreshUsers: mutate,
  };
}
