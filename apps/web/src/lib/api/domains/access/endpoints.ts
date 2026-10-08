// Access Domain API endpoint paths
// Merged from identity-access and tenancy modules

// === Identity-access endpoints ===

// === Tenancy endpoints ===

// === Actual hook endpoints (different from identity-access module) ===
// These are the actual endpoints used by hooks

// === Endpoint builder functions ===

import { APIKey } from "@/lib/api/domains/access/api-key-types";

import { ValidSources } from "@/lib/types";

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const accessEndpoints = {
  userServiceProxy: (segments: string[], trailingSlash: boolean) => {
    let path = `/api/v1/${segments.join("/")}`;
    if (trailingSlash && !path.endsWith("/")) path += "/";
    return { backend: { service: "user", path } } as const;
  },
  getCurrentUserPermissions: {
    method: "GET",
    browserPath: "/api/user-service/users/me/permissions",
    backend: { service: "user", path: "/api/v1/users/me/permissions" },
  },
  users: { browserPath: "/api/admin/users" },
  directoryUsers: { browserPath: "/api/user-service/users" },
  directoryUsersPage: (params: URLSearchParams): { browserPath: string } => {
    return {
      browserPath: `${
        accessEndpoints.directoryUsers.browserPath
      }?${params.toString()}`,
    };
  },
  apiKeys: { browserPath: "/api/admin/api-keys" },
  tenantTeamByDomain: { browserPath: "/api/tenants/existing-team-by-domain" },
  tenantLeaveTeam: { browserPath: "/api/tenants/leave-team" },
  tenantInviteAccept: { browserPath: "/api/tenants/users/invite/accept" },
  tenantInviteApprove: { browserPath: "/api/tenants/users/invite/approve" },
  tenantInviteDeny: { browserPath: "/api/tenants/users/invite/deny" },
  tenantInviteRequest: { browserPath: "/api/tenants/users/invite/request" },
  tenantUsersPending: { browserPath: "/api/tenants/users/pending" },
  manageUsers: { browserPath: "/api/manage/users" },
  shareableUsers: { browserPath: "/api/users" },
  manageUserGroup: { browserPath: "/api/manage/admin/user-group" },
  shareableMinimalUserGroups: {
    browserPath: "/api/manage/user-groups/minimal",
  },
  userServiceRoles: { browserPath: "/api/user-service/roles" },
  organizationScope: { browserPath: "/api/user-service/organizations/scope" },
  organizationAssignableUsers: (
    organizationId: string,
    query: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/organizations/${organizationId}/assignable-users?query=${encodeURIComponent(
        query
      )}&limit=20`,
    };
  },
  scopedPermissions: (
    organizationId: string,
    targetType: "organization" | "user",
    targetId: string,
    resourceType: "agent" | "rag_collection"
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/permissions/organizations/${organizationId}/targets/${targetType}/${targetId}/resources/${resourceType}`,
    };
  },
  scopedPermissionsWorkspace: (
    organizationId: string,
    targetType: "organization" | "user",
    targetId: string,
    resourceType: "agent" | "rag_collection"
  ): { browserPath: string } => ({
    browserPath: `${
      accessEndpoints.scopedPermissions(
        organizationId,
        targetType,
        targetId,
        resourceType
      ).browserPath
    }/workspace`,
  }),
  manageUsersPage: (includeApiKeys: boolean): { browserPath: string } => {
    return {
      browserPath: `${accessEndpoints.manageUsers.browserPath}?include_api_keys=${includeApiKeys}`,
    };
  },
  shareableUsersSearch: (includeApiKeys: boolean): { browserPath: string } => {
    return {
      browserPath: `${accessEndpoints.shareableUsers.browserPath}?include_api_keys=${includeApiKeys}`,
    };
  },
  createApiKey: { browserPath: "/api/admin/api-key" },
  regenerateApiKey: (apiKey: APIKey): { browserPath: string } => {
    return {
      browserPath: `/api/admin/api-key/${apiKey.api_key_id}/regenerate`,
    };
  },
  updateApiKey: (apiKeyId: number): { browserPath: string } => {
    return { browserPath: `/api/admin/api-key/${apiKeyId}` };
  },
  deleteUserGroup: (userGroupId: number): { browserPath: string } => {
    return { browserPath: `/api/manage/admin/user-group/${userGroupId}` };
  },
  hierarchyNodesPrefix: { browserPath: "/api/hierarchy-nodes" },
  fetchHierarchyNodes: (source: ValidSources): { browserPath: string } => {
    return {
      browserPath: `${
        accessEndpoints.hierarchyNodesPrefix.browserPath
      }?source=${encodeURIComponent(source)}`,
    };
  },
  fetchHierarchyNodeDocuments: {
    browserPath: "/api/hierarchy-nodes/documents",
  },
  searchOrganizationTree: (pathValue: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/organizations/search?q=${pathValue}&max_results=100`,
    };
  },
  fetchOrganizationChildren: (orgId: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/organizations/${orgId}/children` };
  },
  fetchOrganizationMembers: (orgId: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/organizations/${orgId}/users` };
  },
  fetchOrganizationAncestors: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/organizations/${id}/ancestors` };
  },
  createOrganizationNode: { browserPath: "/api/user-service/organizations" },
  updateOrganizationNode: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/organizations/${id}` };
  },
  moveOrganizationNode: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/organizations/${id}/move` };
  },
  updateOrganizationMemberRole: (
    id: string,
    userId: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/organizations/${id}/users/${userId}`,
    };
  },
  syncKeycloakRoles: { browserPath: "/api/user-service/roles/sync-keycloak" },
  createCompositeRole: { browserPath: "/api/user-service/roles/" },
  createDirectoryUser: { browserPath: "/api/user-service/users" },
  downloadDirectoryUsers: {
    browserPath: "/api/user-service/users/download/csv",
  },
  setDirectoryUserPassword: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/users/${id}/password` };
  },
  directoryUser: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/users/${id}` };
  },
  directoryUserActive: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/users/${id}/active` };
  },
  directoryUserRole: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/users/${id}/role` };
  },
  userRoleDistribution: {
    browserPath: "/api/user-service/users/role-distribution",
  },
  compositeRoles: { browserPath: "/api/user-service/roles/" },
  coarseRoles: { browserPath: "/api/user-service/coarse-roles/" },
  deleteCoarseRole: (roleId: string): { browserPath: string } => ({
    browserPath: `/api/user-service/coarse-roles/${encodeURIComponent(roleId)}`,
  }),
  roleServiceClients: {
    browserPath: "/api/user-service/coarse-roles/service-clients/list",
  },
  permissionCatalog: { browserPath: "/api/user-service/permissions/" },
  compositeRolePermissions: (name: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/roles/${encodeURIComponent(
        name
      )}/permissions`,
    };
  },
  compositeRoleIds: (name: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/roles/${encodeURIComponent(
        name
      )}/role-ids`,
    };
  },
  coarseRolePermissions: (name: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/coarse-roles/${encodeURIComponent(
        name
      )}/permissions`,
    };
  },
  directoryUserStatusCount: (active: boolean): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/users?is_active=${active}&limit=1`,
    };
  },
  resetDirectoryUserPassword: (id: string): { browserPath: string } => {
    return { browserPath: `/api/user-service/users/${id}/reset-password` };
  },
  fetchCompleteOrganizationTree: {
    browserPath: "/api/user-service/organizations/tree",
  },
  persistOrganizationLayout: {
    browserPath: "/api/user-service/organizations/layout",
  },
  grantUserResourcePermission: (userId: string) => ({
    browserPath: `/api/user-service/permissions/users/${encodeURIComponent(
      userId
    )}/resources`,
  }),
  grantOrganizationResourcePermission: (organizationId: string) => ({
    browserPath: `/api/user-service/permissions/organizations/${encodeURIComponent(
      organizationId
    )}/resources`,
  }),
  revokeResourcePermission: (permissionId: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/permissions/permissions/${permissionId}`,
    };
  },
  updateCuratorStatus: (groupId: number): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/user-group/${groupId}/set-curator`,
    };
  },
  inviteDirectoryUsersBulk: { browserPath: "/api/user-service/users/invite" },
  uninviteDirectoryUser: (
    userId: string | undefined
  ): { browserPath: string } => {
    return { browserPath: `/api/user-service/users/${userId}` };
  },
  fetchResourcePermissions: (
    resourceType: "agent" | "agent_group" | "rag_collection" | "connector",
    resourceId: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/permissions/resources/${resourceType}/${resourceId}`,
    };
  },
  fetchPermissionOrganizations: {
    browserPath: "/api/user-service/organizations",
  },
  patchCompositeRole: (roleId: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/roles/${encodeURIComponent(roleId)}`,
    };
  },
  deleteCompositeRole: (roleName: string): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/roles/${encodeURIComponent(roleName)}`,
    };
  },
  fetchOrganizationTreeLevelTwo: (): { browserPath: string } => {
    return { browserPath: "/api/user-service/organizations/tree?max_depth=2" };
  },
  fetchAllOrganizationMembers: (): { browserPath: string } => {
    return { browserPath: "/api/user-service/organizations/members" };
  },
  fetchOrganizationManagementCapability: (
    organizationId: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/organizations/${organizationId}/management-capability`,
    };
  },
  fetchDirectoryRoleCatalog: (): { browserPath: string } => {
    return { browserPath: "/api/user-service/roles" };
  },
  fetchDirectoryAssignableUsers: (): { browserPath: string } => {
    return { browserPath: "/api/user-service/users/" };
  },
  encodedCompositeRolePermissionsKey: (
    encodedRole: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/roles/${encodedRole}/permissions`,
    };
  },
  encodedCompositeRoleIdsKey: (
    encodedRole: string
  ): { browserPath: string } => {
    return { browserPath: `/api/user-service/roles/${encodedRole}/role-ids` };
  },
  encodedCoarseRolePermissionsKey: (
    encodedRole: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user-service/coarse-roles/${encodedRole}/permissions`,
    };
  },
  shareableUsersCacheKey: (
    includeApiKeys: boolean
  ): { browserPath: string } => {
    return { browserPath: `/api/users?include_api_keys=${includeApiKeys}` };
  },
  manageUsersCacheKey: (includeApiKeys: boolean): { browserPath: string } => {
    return {
      browserPath: `/api/manage/users?include_api_keys=${includeApiKeys}`,
    };
  },
  /** User-service JSON targets; file downloads retain their transport body. */
  isUserServiceJsonPath: (path: string): boolean => {
    const pathname = path.split("?")[0] ?? "";
    const isUserTarget = [
      "/api/user-service/",
      "/api/users",
      "/api/roles",
      "/api/permissions",
    ].some(
      (prefix) =>
        pathname === prefix ||
        pathname.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`)
    );
    return (
      isUserTarget &&
      pathname !== accessEndpoints.downloadDirectoryUsers.browserPath
    );
  },
} as const;
