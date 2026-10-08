import { userServicePayloadResponse } from "@/lib/api/userServiceResponse";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

/**
 * Access Domain API client
 * Merged from identity-access and tenancy modules.
 * Uses apiRequest from the shared browser transport.
 */

import { apiRequest, parseJsonResponse } from "@/lib/api/http/browser";
import {
  FetchError,
  parseApiErrorResponse,
  throwParsedApiError,
} from "@/lib/api/http/errors";
import type { ApiRequestOptions } from "@/lib/api/http/types";

import type {
  DirectResourcePermission,
  OrganizationLayoutPosition,
  OrganizationNode,
  ScopedPermissionResource,
  ScopedPermissionsResponse,
  SavedScopedPermissionsResponse,
  ScopedPermissionTarget,
} from "@/lib/api/domains/access/types";
import type { AllUsersResponse, User } from "@/lib/types";

// Helper to make JSON requests through apiRequest
async function requestAccessJson<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const res = await requestAccessResponse(path, options);
  if (!res.ok) {
    await throwParsedApiError(
      res,
      `Access API request failed (Status: ${res.status})`
    );
  }
  const result = await parseJsonResponse<T>(res);
  if (result === undefined) {
    throw new Error("Access API request returned empty response");
  }
  return result;
}

async function fetchAccessSWRJson<T>(path: string): Promise<T> {
  const response = await requestAccessResponse(path, {
    headers: { "X-Language": i18n.language },
  });
  if (!response.ok) {
    const parsedError = await parseApiErrorResponse(response);
    throw new FetchError(
      parsedError.userMessage,
      response.status,
      parsedError.raw,
      parsedError
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    return {} as T;
  }
}

export const fetchCompositeRoles = <T>() =>
  fetchAccessSWRJson<T>(accessEndpoints.compositeRoles.browserPath);
export const fetchCoarseRoles = <T>() =>
  fetchAccessSWRJson<T>(accessEndpoints.coarseRoles.browserPath);
export const fetchRoleServiceClients = <T>() =>
  fetchAccessSWRJson<T>(accessEndpoints.roleServiceClients.browserPath);
export const fetchPermissionCatalog = <T>() =>
  fetchAccessSWRJson<T>(accessEndpoints.permissionCatalog.browserPath);
export const fetchCompositeRolePermissions = <T>(name: string) =>
  fetchAccessSWRJson<T>(
    accessEndpoints.compositeRolePermissions(name).browserPath
  );
export const fetchCompositeRoleIds = <T>(name: string) =>
  fetchAccessSWRJson<T>(accessEndpoints.compositeRoleIds(name).browserPath);
export const fetchCoarseRolePermissionsByName = <T>(name: string) =>
  fetchAccessSWRJson<T>(
    accessEndpoints.coarseRolePermissions(name).browserPath
  );
export const fetchRoleDistribution = <T>() =>
  fetchAccessSWRJson<T>(accessEndpoints.userRoleDistribution.browserPath);
export const fetchDirectoryUsersPage = <T>(params: URLSearchParams) =>
  fetchAccessSWRJson<T>(accessEndpoints.directoryUsersPage(params).browserPath);
export const fetchUserGroupsForSWR = <T>() =>
  fetchAccessSWRJson<T>(accessEndpoints.manageUserGroup.browserPath);

// ============================================================================
// Identity-access operations (users, groups, organizations, api keys)
// ============================================================================

export function fetchApiKeys<T = unknown[]>() {
  return requestAccessJson<T>(accessEndpoints.apiKeys.browserPath);
}

// ============================================================================
// Tenancy operations (tenant, billing, teams, invites)
// ============================================================================

// ============================================================================
// Manage user operations (used by hooks)
// ============================================================================

export function fetchManageUsers(includeApiKeys: boolean) {
  return requestAccessJson<AllUsersResponse>(
    accessEndpoints.manageUsersPage(includeApiKeys).browserPath
  );
}

export function fetchManageUserGroups<T = unknown[]>(): Promise<T> {
  return requestAccessJson<T>(accessEndpoints.manageUserGroup.browserPath);
}

// ============================================================================
// Shareable user and group operations (used by sharing dialogs)
// ============================================================================

export function fetchShareableUsers<T = unknown[]>(
  includeApiKeys: boolean
): Promise<T> {
  return requestAccessJson<T>(
    accessEndpoints.shareableUsersSearch(includeApiKeys).browserPath
  );
}

export function fetchShareableMinimalUserGroups<T = unknown[]>(): Promise<T> {
  return requestAccessJson<T>(
    accessEndpoints.shareableMinimalUserGroups.browserPath
  );
}

export function fetchRoles<T = unknown[]>(): Promise<T> {
  return requestAccessJson<T>(accessEndpoints.userServiceRoles.browserPath);
}

import { APIKeyArgs, APIKey } from "@/lib/api/domains/access/api-key-types";

export const createApiKey = async (apiKeyArgs: APIKeyArgs) => {
  return requestAccessResponse(accessEndpoints.createApiKey.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(apiKeyArgs),
  });
};

export const regenerateApiKey = async (apiKey: APIKey) => {
  return requestAccessResponse(
    accessEndpoints.regenerateApiKey(apiKey).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
};

export const updateApiKey = async (
  apiKeyId: number,
  apiKeyArgs: APIKeyArgs
) => {
  return requestAccessResponse(
    accessEndpoints.updateApiKey(apiKeyId).browserPath,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(apiKeyArgs),
    }
  );
};

export const deleteApiKey = async (apiKeyId: number) => {
  return requestAccessResponse(
    accessEndpoints.updateApiKey(apiKeyId).browserPath,
    {
      method: "DELETE",
    }
  );
};

import { UserGroupCreation } from "@/lib/api/domains/access/group-types";

export const createUserGroup = async (userGroup: UserGroupCreation) => {
  return requestAccessResponse(accessEndpoints.manageUserGroup.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(userGroup),
  });
};

export const deleteUserGroup = async (userGroupId: number) => {
  return requestAccessResponse(
    accessEndpoints.deleteUserGroup(userGroupId).browserPath,
    {
      method: "DELETE",
    }
  );
};

import { ValidSources } from "@/lib/types";
import {
  HierarchyNodesResponse,
  HierarchyNodeDocumentsRequest,
  HierarchyNodeDocumentsResponse,
} from "@/lib/hierarchy/interfaces";
import i18n from "@/i18n/config";

async function extractErrorDetail(
  response: Response,
  fallback: string
): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export async function fetchHierarchyNodes(
  source: ValidSources
): Promise<HierarchyNodesResponse> {
  const response = await requestAccessResponse(
    accessEndpoints.fetchHierarchyNodes(source).browserPath
  );

  if (!response.ok) {
    const detail = await extractErrorDetail(
      response,
      `Failed to fetch hierarchy nodes: ${response.statusText}`
    );
    throw new Error(detail);
  }

  const data = await parseJsonResponse<HierarchyNodesResponse>(response);
  return data as HierarchyNodesResponse;
}

export async function fetchHierarchyNodeDocuments(
  request: HierarchyNodeDocumentsRequest
): Promise<HierarchyNodeDocumentsResponse> {
  const response = await requestAccessResponse(
    accessEndpoints.fetchHierarchyNodeDocuments.browserPath,
    {
      method: "POST",
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    const detail = await extractErrorDetail(
      response,
      `Failed to fetch hierarchy node documents: ${response.statusText}`
    );
    throw new Error(detail);
  }

  const data =
    await parseJsonResponse<HierarchyNodeDocumentsResponse>(response);
  return data as HierarchyNodeDocumentsResponse;
}

export function searchOrganizationTree(
  pathValue: string,
  signal: AbortSignal,
  redirectOnAuthError = true
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.searchOrganizationTree(pathValue).browserPath,
    {
      signal: signal,
      redirectOnAuthError,
    }
  );
}

export function fetchOrganizationChildren(
  orgId: string,
  redirectOnAuthError = true
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchOrganizationChildren(orgId).browserPath,
    {
      redirectOnAuthError,
    }
  );
}

export function fetchOrganizationMembers(orgId: string): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchOrganizationMembers(orgId).browserPath
  );
}

export function fetchOrganizationAncestors(
  id: string,
  redirectOnAuthError = true
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchOrganizationAncestors(id).browserPath,
    {
      redirectOnAuthError,
    }
  );
}

export function createOrganizationNode(payload: {
  name: string;
  code: string;
  parent_id: string | null;
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.createOrganizationNode.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function updateOrganizationNode(
  id: string,
  payload: Partial<OrganizationNode>
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.updateOrganizationNode(id).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function deleteOrganizationNode(id: string): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.updateOrganizationNode(id).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function moveOrganizationNode(
  id: string,
  payload: { new_parent_id: string | null }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.moveOrganizationNode(id).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function addOrganizationMember(
  id: string,
  payload: { user_id: string; role_in_org: string }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchOrganizationMembers(id).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function updateOrganizationMemberRole(
  id: string,
  userId: string,
  payload: { role_in_org: string }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.updateOrganizationMemberRole(id, userId).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function removeOrganizationMember(
  id: string,
  userId: string
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.updateOrganizationMemberRole(id, userId).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function syncKeycloakRoles(): Promise<Response> {
  return requestAccessResponse(accessEndpoints.syncKeycloakRoles.browserPath, {
    method: "POST",
  });
}

export function createCompositeRole(payload: {
  name: string;
  description?: string;
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.createCompositeRole.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function createCoarseRole(payload: {
  name: string;
  service_client: string;
  description?: string;
  permissions: string[];
}): Promise<Response> {
  return apiRequest(accessEndpoints.coarseRoles.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteCoarseRoleResponse(roleId: string): Promise<Response> {
  return apiRequest(accessEndpoints.deleteCoarseRole(roleId).browserPath, {
    method: "DELETE",
  });
}

export function fetchRateLimitUserGroups(): Promise<Response> {
  return requestAccessResponse(accessEndpoints.manageUserGroup.browserPath);
}

export function createDirectoryUser(payload: {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role_id: string | undefined;
  password: string | undefined;
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.createDirectoryUser.browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function downloadDirectoryUsers(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.downloadDirectoryUsers.browserPath
  );
}

export function updateDirectoryUser(
  id: string,
  payload: { first_name: string | null; last_name: string | null }
): Promise<Response> {
  return requestAccessResponse(accessEndpoints.directoryUser(id).browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function setDirectoryUserPassword(
  id: string,
  payload: { password: string }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.setDirectoryUserPassword(id).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function approveTenantJoinRequest(payload: {
  email: string;
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.tenantInviteApprove.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function resetDirectoryUserPassword(id: string): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.resetDirectoryUserPassword(id).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
}

export function fetchExistingTenantTeam(): Promise<Response> {
  return requestAccessResponse(accessEndpoints.tenantTeamByDomain.browserPath);
}

export function requestTenantTeamInvite(payload: {
  tenant_id: string;
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.tenantInviteRequest.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function fetchCompleteOrganizationTreeResponse(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchCompleteOrganizationTree.browserPath
  );
}

export function persistOrganizationLayout(payload: {
  positions: OrganizationLayoutPosition[];
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.persistOrganizationLayout.browserPath,
    {
      redirectOnAuthError: false,
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function grantUserResourcePermission(payload: {
  resource_type: "agent" | "agent_group" | "rag_collection" | "connector";
  resource_id: string;
  user_id: string;
  permission_level: "owner" | "admin" | "write" | "read" | "execute";
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.grantUserResourcePermission(payload.user_id).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function grantOrganizationResourcePermission(payload: {
  resource_type: "agent" | "agent_group" | "rag_collection" | "connector";
  resource_id: string;
  organization_id: string;
  permission_level: "owner" | "admin" | "write" | "read" | "execute";
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.grantOrganizationResourcePermission(payload.organization_id)
      .browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function revokeResourcePermission(
  permissionId: string
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.revokeResourcePermission(permissionId).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function fetchCurrentUserPermissionsResponse(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.getCurrentUserPermissions.browserPath,
    {
      redirectOnAuthError: false,
    }
  );
}

export function acceptTenantInviteResponse(payload: {
  tenant_id: string;
}): Promise<Response> {
  return requestAccessResponse(accessEndpoints.tenantInviteAccept.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function denyTenantInviteResponse(payload: {
  tenant_id: string;
}): Promise<Response> {
  return requestAccessResponse(accessEndpoints.tenantInviteDeny.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function updateUserGroupResponse(
  groupId: number,
  payload: import("@/lib/api/domains/access/group-types").UserGroupUpdate
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.deleteUserGroup(groupId).browserPath,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function updateCuratorStatusResponse(
  groupId: number,
  payload: import("@/lib/api/domains/access/group-types").SetCuratorRequest
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.updateCuratorStatus(groupId).browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function inviteDirectoryUsersBulk(payload: {
  emails: string[];
}): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.inviteDirectoryUsersBulk.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function uninviteDirectoryUser(
  userId: string | undefined
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.uninviteDirectoryUser(userId).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function fetchOrganizationLayoutResponse(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.persistOrganizationLayout.browserPath,
    {
      redirectOnAuthError: false,
    }
  );
}

export function fetchResourcePermissionsResponse(
  resourceType: "agent" | "agent_group" | "rag_collection" | "connector",
  resourceId: string
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchResourcePermissions(resourceType, resourceId)
      .browserPath
  );
}

export function fetchPermissionOrganizationsResponse(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchPermissionOrganizations.browserPath
  );
}

export function fetchPermissionUsersResponse(): Promise<Response> {
  return requestAccessResponse(accessEndpoints.shareableUsers.browserPath);
}

export function updateCoarseRolePermissions(
  roleName: string,
  payload: { permissions: string[] }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.coarseRolePermissions(roleName).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function updateCompositeRoleIds(
  roleName: string,
  payload: { role_ids: string[] }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.compositeRoleIds(roleName).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function patchCompositeRole(
  roleId: string,
  payload: { description?: string }
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.patchCompositeRole(roleId).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

export function deleteCompositeRoleResponse(
  roleName: string
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.deleteCompositeRole(roleName).browserPath,
    {
      method: "DELETE",
    }
  );
}

export function fetchOrganizationTreeLevelTwo(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchOrganizationTreeLevelTwo().browserPath
  );
}

export function fetchAllOrganizationMembers(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchAllOrganizationMembers().browserPath
  );
}

export function fetchOrganizationManagementCapability(
  organizationId: string
): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchOrganizationManagementCapability(organizationId)
      .browserPath
  );
}

export function fetchDirectoryRoleCatalog(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchDirectoryRoleCatalog().browserPath
  );
}

export function fetchDirectoryAssignableUsers(): Promise<Response> {
  return requestAccessResponse(
    accessEndpoints.fetchDirectoryAssignableUsers().browserPath
  );
}

export async function fetchOrganizationScope(): Promise<{
  global_access: boolean;
  root_ids: string[];
}> {
  const response = await requestAccessResponse(
    accessEndpoints.organizationScope.browserPath,
    {
      auth: "public",
    }
  );
  if (!response.ok)
    throw new Error(
      await readScopedPermissionError(response, "Request failed")
    );
  return response.json();
}

export async function fetchOrganizationAssignableUsers(
  organizationId: string,
  query: string
): Promise<{
  users: Array<{
    id: string;
    email: string;
    first_name?: string;
    last_name?: string;
    username?: string;
  }>;
  total: number;
}> {
  const response = await requestAccessResponse(
    accessEndpoints.organizationAssignableUsers(organizationId, query)
      .browserPath,
    { auth: "public" }
  );
  if (!response.ok) await throwParsedApiError(response, "Request failed");
  return response.json();
}

export async function fetchOrganizationPermissionCounts(
  organizationId: string,
  resourceType: "agent" | "rag_collection"
): Promise<{ permissions: Array<{ resource_id: string }> }> {
  // The summary cards share their SWR key with the access editor
  // (`scopedPermissions`), so a successful save mutates exactly the key this
  // fetcher reads. Fetching the `/workspace` composition instead left the
  // counts keyed to an endpoint nothing ever revalidated.
  const response = await requestAccessResponse(
    accessEndpoints.scopedPermissions(
      organizationId,
      "organization",
      organizationId,
      resourceType
    ).browserPath,
    { auth: "public" }
  );
  if (!response.ok)
    await throwParsedApiError(response, "Could not load organization counts");
  return response.json();
}

async function readScopedPermissionError(
  response: Response,
  fallback: string
): Promise<string> {
  const data = (await response.json().catch(() => null)) as {
    detail?: string;
    message?: string;
  } | null;
  return data?.detail || data?.message || fallback;
}

export async function fetchScopedPermissions(
  organizationId: string,
  targetType: ScopedPermissionTarget,
  targetId: string,
  resourceType: ScopedPermissionResource,
  fallback: string
): Promise<ScopedPermissionsResponse> {
  const response = await requestAccessResponse(
    accessEndpoints.scopedPermissionsWorkspace(
      organizationId,
      targetType,
      targetId,
      resourceType
    ).browserPath
  );
  if (!response.ok) {
    throw new Error(await readScopedPermissionError(response, fallback));
  }
  return response.json() as Promise<ScopedPermissionsResponse>;
}

export async function saveScopedPermissions(
  organizationId: string,
  targetType: ScopedPermissionTarget,
  targetId: string,
  resourceType: ScopedPermissionResource,
  permissions: DirectResourcePermission[],
  fallback: string
): Promise<SavedScopedPermissionsResponse> {
  const response = await requestAccessResponse(
    accessEndpoints.scopedPermissions(
      organizationId,
      targetType,
      targetId,
      resourceType
    ).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permissions }),
    }
  );
  if (!response.ok) {
    throw new Error(await readScopedPermissionError(response, fallback));
  }
  return response.json() as Promise<SavedScopedPermissionsResponse>;
}

async function requestAccessMutation<T>(
  path: string,
  method: "PATCH" | "POST" | "DELETE",
  body: Record<string, unknown>
): Promise<T> {
  const response = await requestAccessResponse(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = (await response.json()) as { detail?: string };
    throw new Error(error.detail);
  }
  return response.json() as Promise<T>;
}

export function deleteDirectoryUser(userId: string): Promise<unknown> {
  return requestAccessMutation(
    accessEndpoints.directoryUser(userId).browserPath,
    "DELETE",
    {}
  );
}

export function leaveOrganization(userEmail: string): Promise<unknown> {
  return requestAccessMutation(
    accessEndpoints.tenantLeaveTeam.browserPath,
    "POST",
    {
      user_email: userEmail,
    }
  );
}

export function setDirectoryUserActive(
  userId: string,
  isActive: boolean
): Promise<User> {
  return requestAccessMutation<User>(
    accessEndpoints.directoryUserActive(userId).browserPath,
    "PATCH",
    {
      is_active: isActive,
    }
  );
}

export function setDirectoryUserRole(
  userId: string,
  roleId: string
): Promise<User> {
  return requestAccessMutation<User>(
    accessEndpoints.directoryUserRole(userId).browserPath,
    "POST",
    {
      role_id: roleId,
    }
  );
}

export function fetchPendingDirectoryUsers<T>(): Promise<T> {
  return requestAccessJson<T>(accessEndpoints.tenantUsersPending.browserPath);
}
export function fetchDirectoryRoleDistribution(): Promise<{
  distribution: { role: string; count: number }[];
}> {
  return requestAccessJson(accessEndpoints.userRoleDistribution.browserPath);
}
export function fetchDirectoryUserStatusCount(
  active: boolean
): Promise<{ total_items: number }> {
  return requestAccessJson(
    accessEndpoints.directoryUserStatusCount(active).browserPath
  );
}

async function requestAccessResponse(
  path: string,
  options: ApiRequestOptions = {}
): Promise<Response> {
  const response = await apiRequest(path, options);
  return accessEndpoints.isUserServiceJsonPath(path)
    ? userServicePayloadResponse(response)
    : response;
}
